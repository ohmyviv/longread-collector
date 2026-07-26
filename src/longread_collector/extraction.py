from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url, sha256_text, source_from_domain, stable_id

PARTIAL_MARKERS = (
    "subscribe to continue", "subscription required", "sign in to continue", "this article is for subscribers",
    "already a subscriber", "remaining content", "剩余内容", "登录后继续阅读", "订阅后阅读全文", "付费阅读", "会员专享",
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


def _verification(title: str, author: str, date: str, content: str, description: str, min_chars: int) -> tuple[str, str]:
    chars = len(content)
    partial = _contains_partial_marker(content)
    if title and author and date and chars >= min_chars and not partial:
        return "A", "full_body_and_metadata_auto"
    if title and author and date and chars >= 600:
        return "B", "partial_body_and_metadata_auto"
    if title and date and (description or chars >= 200):
        return "C", "article_metadata_or_excerpt_only"
    return "D", "article_not_sufficiently_verified"


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
        candidates.append({
            "extractor": "jina",
            "content": content,
            "title": _clean_value(data.get("title")) or discovered.title,
            "author": _clean_value(data.get("author")),
            "published_at": _clean_value(data.get("published_at")) or discovered.published_at,
            "description": discovered.description,
            "metadata": {k: v for k, v in data.items() if k not in {"raw", "markdown"}},
        })
        attempts.append({"extractor": "jina", "success": bool(content), "body_chars": len(content), **meta})
    except Exception as exc:
        attempts.append({
            "extractor": "jina", "success": False, "body_chars": 0,
            "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
        })

    best_jina_chars = max((len(c["content"]) for c in candidates if c["extractor"] == "jina"), default=0)
    should_fallback = best_jina_chars < settings.min_body_chars
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
            candidates.append({
                "extractor": "firecrawl",
                "content": content,
                "title": _clean_value(metadata.get("title")) or discovered.title,
                "author": _clean_value(metadata.get("author") or metadata.get("authors")),
                "published_at": _clean_value(metadata.get("publishedTime") or metadata.get("publishedDate") or metadata.get("date")) or discovered.published_at,
                "description": _clean_value(metadata.get("description")) or discovered.description,
                "metadata": metadata,
            })
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
        }
    else:
        def score(item: dict[str, Any]) -> tuple[int, int, int]:
            metadata_score = sum(bool(item.get(k)) for k in ("title", "author", "published_at"))
            partial_penalty = -1 if _contains_partial_marker(item.get("content", "")) else 0
            return metadata_score, partial_penalty, len(item.get("content", ""))

        best = max(candidates, key=score)

    content = best.get("content", "")
    title = best.get("title", "")
    author = best.get("author", "")
    published_at = best.get("published_at", "")
    description = best.get("description", "")
    level, verification_reason = _verification(title, author, published_at, content, description, settings.min_body_chars)
    domain = domain_from_url(canonical)
    source = _clean_value(best.get("metadata", {}).get("siteName") or best.get("metadata", {}).get("publisher")) or source_from_domain(domain)
    full_chars = len(content)
    truncated = full_chars > settings.content_cell_limit
    stored_content = content[: settings.content_cell_limit]
    eligible = level in {"A", "B"} and full_chars >= settings.editor_min_body_chars
    reject_reason = "" if eligible else verification_reason if level in {"C", "D"} else "body_below_editor_minimum"

    metadata = {
        "discovery": discovered.metadata,
        "extraction": best.get("metadata", {}),
        "verification_reason": verification_reason,
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
        extraction_status="success" if full_chars else "failed",
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
