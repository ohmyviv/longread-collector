"""Cross-run duplicate handling for official primary documents.

Batch duplicate clustering only sees the current extraction batch. Official
statements are frequently copied across ministry, embassy and consulate sites
on different days, so an exact normalized document title must also be checked
against the historical cache before the current batch is persisted.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable
from urllib.parse import urlsplit

from .classification import normalize_title
from .models import DiscoveredURL, ExtractedArticle

HISTORICAL_DEDUPE_VERSION = "historical-primary-document-dedupe-v0.5.6l"
_OFFICIAL_HOST_SUFFIX_RE = re.compile(
    r"(?:中华人民共和国)?(?:驻[^\s]{1,40}(?:大使馆|总领事馆)|"
    r"[^\s]{1,30}(?:人民政府网|政府网|政府网站))$",
)
_CARRIER_DOMAIN_RE = re.compile(r"(?:embassy|consulate|china-embassy|fmprc)", re.I)


def _domain(url: str) -> str:
    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


def _document_key(title: str) -> str:
    value = normalize_title(str(title or "")).replace(" ", "")
    value = _OFFICIAL_HOST_SUFFIX_RE.sub("", value)
    return value.strip()


def _is_primary_document(article: ExtractedArticle) -> bool:
    return (
        article.page_type in {"document", "primary_document"}
        or article.content_type == "government_primary_document"
        or article.special_candidate_type == "primary_document"
    )


def _preference(domain: str, relationship: str) -> tuple[int, int]:
    central = int(not _CARRIER_DOMAIN_RE.search(domain))
    original = int(relationship == "original")
    return central, original


def _historical_preference(row: dict[str, Any]) -> tuple[int, int]:
    domain = _domain(str(row.get("url_canonical") or row.get("url") or ""))
    relationship = str(row.get("source_relationship", ""))
    return _preference(domain, relationship)


def apply_historical_primary_document_dedupe(
    pairs: Iterable[tuple[DiscoveredURL, ExtractedArticle]],
    historical_rows: Iterable[dict[str, Any]],
) -> int:
    """Reject a later carrier copy, but never prefer it over a central original."""

    pair_list = list(pairs)
    index: dict[str, list[dict[str, Any]]] = {}
    for row in historical_rows:
        key = _document_key(str(row.get("title", "")))
        if len(key) < 12:
            continue
        page_type = str(row.get("page_type", ""))
        content_type = str(row.get("content_type", ""))
        special_type = str(row.get("special_candidate_type", ""))
        if not (
            page_type in {"document", "primary_document"}
            or content_type == "government_primary_document"
            or special_type == "primary_document"
        ):
            continue
        index.setdefault(key, []).append(dict(row))

    changed = 0
    for _, article in pair_list:
        if not _is_primary_document(article):
            continue
        key = _document_key(article.title)
        if len(key) < 12:
            continue
        current_domain = _domain(article.url_canonical or article.url)
        matches = [
            row for row in index.get(key, [])
            if str(row.get("article_id", "")) != article.article_id
            and _domain(str(row.get("url_canonical") or row.get("url") or ""))
            != current_domain
        ]
        if not matches:
            continue

        best_preference = max(_historical_preference(row) for row in matches)
        current_preference = _preference(current_domain, article.source_relationship)
        if current_preference > best_preference:
            # The current page is a stronger original than every historical
            # carrier. Keep it and let future carriers point back to it.
            continue
        preferred = [row for row in matches if _historical_preference(row) == best_preference]
        original = sorted(
            preferred,
            key=lambda row: str(row.get("first_seen_at_bj", "")) or "9999",
        )[0]
        original_url = str(
            original.get("original_url")
            or original.get("url_canonical")
            or original.get("url")
            or ""
        )
        original_source = str(
            original.get("original_publisher")
            or original.get("canonical_source")
            or ""
        )
        cluster_id = "historical-doc-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

        article.candidate_disposition = "reject"
        article.eligible_for_editor = False
        article.reject_reason = "historical_primary_document_duplicate"
        article.classification_reason = "historical_primary_document_duplicate_v056l"
        article.source_relationship = "secondary_republish"
        article.source_action = "replace_with_original_source"
        article.duplicate_type = "same_content_cross_host"
        article.content_cluster_id = cluster_id
        article.original_url = original_url
        if original_source:
            article.original_publisher = original_source
            article.canonical_source = original_source
        article.metadata.setdefault("historical_dedupe", {}).update(
            {
                "version": HISTORICAL_DEDUPE_VERSION,
                "matched_article_id": str(original.get("article_id", "")),
                "matched_url": original_url,
                "document_key": key,
                "cluster_id": cluster_id,
                "current_preference": list(current_preference),
                "historical_preference": list(best_preference),
            }
        )
        changed += 1
    return changed


def apply_historical_primary_document_dedupe_from_store(
    store: Any,
    pairs: Iterable[tuple[DiscoveredURL, ExtractedArticle]],
) -> int:
    pair_list = list(pairs)
    try:
        worksheet = store.book.worksheet("article_cache")
        rows = worksheet.get_all_records()
    except Exception as exc:  # provider failures must not corrupt a run
        for _, article in pair_list:
            article.metadata.setdefault("historical_dedupe", {}).update(
                {
                    "version": HISTORICAL_DEDUPE_VERSION,
                    "status": "unavailable",
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
        return 0
    return apply_historical_primary_document_dedupe(pair_list, rows)


__all__ = [
    "HISTORICAL_DEDUPE_VERSION",
    "apply_historical_primary_document_dedupe",
    "apply_historical_primary_document_dedupe_from_store",
]
