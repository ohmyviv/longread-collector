from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url, sha256_text, source_from_domain, stable_id
from .quality import content_quality_reason

PARTIAL_MARKERS = (
    "subscribe to continue", "subscription required", "sign in to continue", "this article is for subscribers",
    "already a subscriber", "remaining content", "剩余内容", "登录后继续阅读", "订阅后阅读全文", "付费阅读", "会员专享",
)

AUTHOR_PATTERNS = (
    re.compile(r"^(?:By|Written by|Author(?:s)?[：:]?)\s+(?:\*\*)?\[?([^\]\n|]{2,120})", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^(?:作者|撰文|文|记者)[：:]\s*([^\n|]{2,80})", re.MULTILINE),
)
DATE_PATTERNS = (
    re.compile(r"\b(20\d{2}-\d{1,2}-\d{1,2}(?:[T ][0-9:+\-Z.]+)?)\b"),
    re.compile(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+20\d{2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b", re.IGNORECASE),
    re.compile(r"(20\d{2}年\d{1,2}月\d{1,2}日)"),
)


@dataclass
class FallbackBudget:
    remaining: int

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x) for x in value if x)
    return str(value).strip()


def _contains_partial_marker(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in PARTIAL_MARKERS)


def _author_from_content(content: str) -> str:
    sample = (content or "")[:7000]
    for pattern in AUTHOR_PATTERNS:
        match = pattern.search(sample)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -*_[]")
            if 2 <= len(value) <= 120:
                return value
    return ""


def _date_from_url_or_content(url: str, content: str) -> str:
    sample = f"{url}\n{(content or '')[:7000]}"
    # Common URL date forms: /2026/07/25/, /20260725/, /2026-07-25/.
    url_patterns = (
        re.compile(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)"),
        re.compile(r"/(20\d{2})[-_](\d{1,2})[-_](\d{1,2})(?:[/.]|$)"),
        re.compile(r"/(20\d{2})(\d{2})(\d{2})(?:[/.]|$)"),
    )
    path = urlsplit(url).path
    for pattern in url_patterns:
        match = pattern.search(path)
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
    for pattern in DATE_PATTERNS:
        match = pattern.search(sample)
        if match:
            return match.group(1).strip()
    return ""


def _verification(
    title: str,
    author: str,
    date: str,
    content: str,
    description: str,
    min_chars: int,
    valid_body: bool,
    quality_reason: str,
) -> tuple[str, str]:
    chars = len(content)
    partial = _contains_partial_marker(content)
    if not valid_body:
        return "D", quality_reason
    if title and author and date and chars >= min_chars and not partial:
        return "A", "full_body_and_metadata_auto"
    if title and date and chars >= min_chars and not partial:
        return "B", "full_body_date_verified_author_missing"
    if title and date and (description or chars >= 600):
        return "C", "article_metadata_or_excerpt_only"
    if title and chars >= min_chars:
        return "C", "full_body_without_reliable_date"
    return "D", "article_not_sufficiently_verified"


def _candidate(
    *, extractor: str, content: str, title: str, author: str, published_at: str,
    description: str, metadata: dict[str, Any], url: str,
) -> dict[str, Any]:
    author = author or _author_from_content(content)
    published_at = published_at or _date_from_url_or_content(url, content)
    valid_body, quality_reason, prose_chars = content_quality_reason(url, title, content)
    return {
        "extractor": extractor,
        "content": content,
        "title": title,
        "author": author,
        "published_at": published_at,
        "description": description,
        "metadata": metadata,
        "valid_body": valid_body,
        "quality_reason": quality_reason,
        "prose_chars": prose_chars,
    }


async def extract_article(
    discovered: DiscoveredURL,
    jina: JinaReaderClient,
    firecrawl: FirecrawlClient,
    settings: Settings,
    fallback_budget: FallbackBudget | None = None,
) -> ExtractedArticle:
    canonical = canonicalize_url(discovered.url)
    article_id = stable_id(canonical)
    attempts: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    started = time.perf_counter()
    try:
        data, meta = await jina.read(discovered.url)
        content = _clean_value(data.get("markdown"))
        candidates.append(_candidate(
            extractor="jina",
            content=content,
            title=_clean_value(data.get("title")) or discovered.title,
            author=_clean_value(data.get("author") or discovered.metadata.get("author") or discovered.metadata.get("authors")),
            published_at=_clean_value(data.get("published_at")) or discovered.published_at,
            description=discovered.description,
            metadata={k: v for k, v in data.items() if k not in {"raw", "markdown"}},
            url=discovered.url,
        ))
        attempts.append({"extractor": "jina", "success": bool(content), "body_chars": len(content), **meta})
    except Exception as exc:
        attempts.append({
            "extractor": "jina", "success": False, "body_chars": 0,
            "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
        })

    jina_candidates = [c for c in candidates if c["extractor"] == "jina"]
    best_jina = max(jina_candidates, key=lambda c: (bool(c["valid_body"]), c["prose_chars"]), default=None)
    should_fallback = not best_jina or not best_jina["valid_body"] or len(best_jina["content"]) < settings.min_body_chars
    fallback_allowed = False
    if should_fallback:
        fallback_allowed = fallback_budget is None or await fallback_budget.try_acquire()

    if should_fallback and fallback_allowed:
        try:
            data, meta = await firecrawl.scrape(discovered.url)
            md = data.get("markdown")
            if isinstance(md, dict):
                md = md.get("content") or md.get("markdown") or ""
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            content = _clean_value(md)
            candidates.append(_candidate(
                extractor="firecrawl",
                content=content,
                title=_clean_value(metadata.get("title")) or discovered.title,
                author=_clean_value(metadata.get("author") or metadata.get("authors") or discovered.metadata.get("author")),
                published_at=_clean_value(metadata.get("publishedTime") or metadata.get("publishedDate") or metadata.get("date")) or discovered.published_at,
                description=_clean_value(metadata.get("description")) or discovered.description,
                metadata=metadata,
                url=discovered.url,
            ))
            attempts.append({"extractor": "firecrawl", "success": bool(content), "body_chars": len(content), **meta})
        except Exception as exc:
            attempts.append({
                "extractor": "firecrawl", "success": False, "body_chars": 0,
                "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
            })
    elif should_fallback:
        attempts.append({
            "extractor": "firecrawl",
            "success": False,
            "body_chars": 0,
            "error_type": "DailyFallbackBudgetExhausted",
            "error_message": "Firecrawl scrape fallback skipped because the daily free-tier budget is exhausted",
            "credits_used": 0,
        })

    if not candidates:
        best = {
            "extractor": "none", "content": "", "title": discovered.title, "author": "",
            "published_at": discovered.published_at, "description": discovered.description, "metadata": {},
            "valid_body": False, "quality_reason": "no_extracted_content", "prose_chars": 0,
        }
    else:
        def score(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
            metadata_score = sum(bool(item.get(k)) for k in ("title", "author", "published_at"))
            not_partial = 0 if _contains_partial_marker(item.get("content", "")) else 1
            return (
                int(bool(item.get("valid_body"))),
                metadata_score,
                not_partial,
                int(item.get("prose_chars", 0)),
                len(item.get("content", "")),
            )

        best = max(candidates, key=score)

    content = best.get("content", "")
    title = best.get("title", "")
    author = best.get("author", "")
    published_at = best.get("published_at", "")
    description = best.get("description", "")
    valid_body = bool(best.get("valid_body"))
    quality_reason = str(best.get("quality_reason") or "article_not_sufficiently_verified")
    level, verification_reason = _verification(
        title, author, published_at, content, description, settings.min_body_chars, valid_body, quality_reason,
    )
    domain = domain_from_url(canonical)
    source = _clean_value(best.get("metadata", {}).get("siteName") or best.get("metadata", {}).get("publisher")) or source_from_domain(domain)
    full_chars = len(content)
    truncated = full_chars > settings.content_cell_limit
    stored_content = content[: settings.content_cell_limit]
    eligible = level in {"A", "B"} and full_chars >= settings.editor_min_body_chars and valid_body
    reject_reason = "" if eligible else verification_reason if level in {"C", "D"} else "body_below_editor_minimum"

    if not full_chars:
        extraction_status = "failed"
    elif not valid_body:
        extraction_status = "rejected"
    else:
        extraction_status = "success"

    metadata = {
        "discovery": discovered.metadata,
        "extraction": best.get("metadata", {}),
        "verification_reason": verification_reason,
        "valid_article_body": valid_body,
        "page_quality_reason": quality_reason,
        "prose_chars": best.get("prose_chars", 0),
        "fallback_requested": should_fallback,
        "fallback_allowed": fallback_allowed,
        "total_latency_ms": round((time.perf_counter() - started) * 1000),
    }
    return ExtractedArticle(
        article_id=article_id,
        url=discovered.url,
        url_canonical=canonical,
        domain=domain,
        title=title,
        author=author,
        published_at=published_at,
        language=discovered.language,
        canonical_source=source,
        hosting_source=source,
        description=description,
        extractor_used=best.get("extractor", "none"),
        extraction_status=extraction_status,
        verification_level=level,
        content_markdown=stored_content,
        content_chars=full_chars,
        content_sha256=sha256_text(content) if content else "",
        content_truncated=truncated,
        eligible_for_editor=eligible,
        reject_reason=reject_reason,
        metadata=metadata,
        extraction_attempts=attempts,
    )
