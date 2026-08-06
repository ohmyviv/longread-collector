"""Extraction with zero-credit direct HTML recovery before Firecrawl."""

from __future__ import annotations

import time
from typing import Any

from .direct_html_v056m import DIRECT_HTML_VERSION, read_direct_html_v056m
from .extraction import (
    FallbackBudget,
    _candidate,
    _clean_value,
    _contains_partial_marker,
    _verification,
)
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url, sha256_text, source_from_domain, stable_id

EXTRACTION_VERSION = "extraction-v0.5.6m"


def _best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
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

    return max(candidates, key=score, default=None)


async def extract_article_v056m(
    discovered: DiscoveredURL,
    jina: Any,
    firecrawl: Any,
    settings: Any,
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
        candidates.append(
            _candidate(
                extractor="jina",
                content=content,
                title=_clean_value(data.get("title")) or discovered.title,
                author=_clean_value(
                    data.get("author")
                    or discovered.metadata.get("author")
                    or discovered.metadata.get("authors")
                ),
                published_at=_clean_value(data.get("published_at")) or discovered.published_at,
                description=discovered.description,
                metadata={k: v for k, v in data.items() if k not in {"raw", "markdown"}},
                url=discovered.url,
            )
        )
        attempts.append(
            {
                "extractor": "jina",
                "success": bool(content),
                "body_chars": len(content),
                **meta,
            }
        )
    except Exception as exc:
        attempts.append(
            {
                "extractor": "jina",
                "success": False,
                "body_chars": 0,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            }
        )

    best_zero = _best(candidates)
    direct_needed = (
        not best_zero
        or not best_zero["valid_body"]
        or len(best_zero["content"]) < settings.min_body_chars
    )
    if direct_needed:
        try:
            data, meta = await read_direct_html_v056m(discovered.url)
            content = _clean_value(data.get("markdown"))
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            candidates.append(
                _candidate(
                    extractor="direct_html",
                    content=content,
                    title=_clean_value(data.get("title")) or discovered.title,
                    author=_clean_value(
                        data.get("author")
                        or discovered.metadata.get("author")
                        or discovered.metadata.get("authors")
                    ),
                    published_at=_clean_value(data.get("published_at")) or discovered.published_at,
                    description=_clean_value(data.get("description")) or discovered.description,
                    metadata=metadata,
                    url=discovered.url,
                )
            )
            attempts.append(
                {
                    "extractor": "direct_html",
                    "success": bool(content),
                    "body_chars": len(content),
                    **meta,
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "extractor": "direct_html",
                    "success": False,
                    "body_chars": 0,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                    "request_sent": True,
                    "direct_html_version": DIRECT_HTML_VERSION,
                }
            )

    zero_cost_candidates = [
        item for item in candidates if item.get("extractor") in {"jina", "direct_html"}
    ]
    best_zero = _best(zero_cost_candidates)
    should_fallback = (
        not best_zero
        or not best_zero["valid_body"]
        or len(best_zero["content"]) < settings.min_body_chars
    )
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
            candidates.append(
                _candidate(
                    extractor="firecrawl",
                    content=content,
                    title=_clean_value(metadata.get("title")) or discovered.title,
                    author=_clean_value(
                        metadata.get("author")
                        or metadata.get("authors")
                        or discovered.metadata.get("author")
                    ),
                    published_at=_clean_value(
                        metadata.get("publishedTime")
                        or metadata.get("publishedDate")
                        or metadata.get("date")
                    )
                    or discovered.published_at,
                    description=_clean_value(metadata.get("description"))
                    or discovered.description,
                    metadata=metadata,
                    url=discovered.url,
                )
            )
            attempts.append(
                {
                    "extractor": "firecrawl",
                    "success": bool(content),
                    "body_chars": len(content),
                    **meta,
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "extractor": "firecrawl",
                    "success": False,
                    "body_chars": 0,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                }
            )
    elif should_fallback:
        attempts.append(
            {
                "extractor": "firecrawl",
                "success": False,
                "body_chars": 0,
                "error_type": "DailyFallbackBudgetExhausted",
                "error_message": (
                    "Firecrawl scrape fallback skipped because the daily "
                    "free-tier budget is exhausted"
                ),
                "credits_used": 0,
            }
        )

    best = _best(candidates) or {
        "extractor": "none",
        "content": "",
        "title": discovered.title,
        "author": "",
        "published_at": discovered.published_at,
        "description": discovered.description,
        "metadata": {},
        "valid_body": False,
        "quality_reason": "no_extracted_content",
        "prose_chars": 0,
    }

    content = best.get("content", "")
    title = best.get("title", "")
    author = best.get("author", "")
    published_at = best.get("published_at", "")
    description = best.get("description", "")
    valid_body = bool(best.get("valid_body"))
    quality_reason = str(
        best.get("quality_reason") or "article_not_sufficiently_verified"
    )
    level, verification_reason = _verification(
        title,
        author,
        published_at,
        content,
        description,
        settings.min_body_chars,
        valid_body,
        quality_reason,
    )
    domain = domain_from_url(canonical)
    source = _clean_value(
        best.get("metadata", {}).get("siteName")
        or best.get("metadata", {}).get("publisher")
    ) or source_from_domain(domain)
    full_chars = len(content)
    truncated = full_chars > settings.content_cell_limit
    stored_content = content[: settings.content_cell_limit]
    eligible = (
        level in {"A", "B"}
        and full_chars >= settings.editor_min_body_chars
        and valid_body
    )
    reject_reason = (
        ""
        if eligible
        else verification_reason
        if level in {"C", "D"}
        else "body_below_editor_minimum"
    )

    if not full_chars:
        extraction_status = "failed"
    elif not valid_body:
        extraction_status = "rejected"
    else:
        extraction_status = "success"

    direct_attempts = [
        attempt for attempt in attempts if attempt.get("extractor") == "direct_html"
    ]
    metadata = {
        "discovery": discovered.metadata,
        "extraction": best.get("metadata", {}),
        "extraction_version": EXTRACTION_VERSION,
        "verification_reason": verification_reason,
        "valid_article_body": valid_body,
        "page_quality_reason": quality_reason,
        "prose_chars": best.get("prose_chars", 0),
        "direct_html_version": DIRECT_HTML_VERSION,
        "direct_html_attempted": bool(direct_attempts),
        "direct_html_succeeded": any(
            bool(attempt.get("success")) for attempt in direct_attempts
        ),
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


__all__ = ["EXTRACTION_VERSION", "extract_article_v056m"]
