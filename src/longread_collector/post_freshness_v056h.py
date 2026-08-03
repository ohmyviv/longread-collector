"""Post-extraction publication-date adapter for v0.5.6h.

Extraction can recover Chinese publication dates such as ``2025年8月13日``.
The general parser deliberately accepts standard date formats, so this narrow
adapter normalizes the Chinese form before the post-extraction freshness gate.
"""

from __future__ import annotations

from datetime import datetime
import re

from .freshness_policy_v056f import (
    FreshnessPolicyDecision,
    evaluate_freshness_policy as _base_evaluate_freshness_policy,
)
from .models import DiscoveredURL

POST_FRESHNESS_VERSION = "post-extraction-freshness-v0.5.6h"

_CHINESE_DATE_RE = re.compile(
    r"^\s*(20\d{2})年(1[0-2]|0?[1-9])月(3[01]|[12]\d|0?[1-9])日"
    r"(?:\s+([01]?\d|2[0-3])[:：]([0-5]\d)(?::([0-5]\d))?)?\s*$"
)


def normalize_extracted_publication_date(value: str) -> str:
    raw = str(value or "").strip()
    match = _CHINESE_DATE_RE.match(raw)
    if not match:
        return raw
    year, month, day, hour, minute, second = match.groups()
    parsed = datetime(
        int(year),
        int(month),
        int(day),
        int(hour or 0),
        int(minute or 0),
        int(second or 0),
    )
    return parsed.isoformat()


def evaluate_post_extraction_freshness(
    item: DiscoveredURL,
    *,
    now: datetime | None = None,
) -> FreshnessPolicyDecision:
    original = str(item.published_at or "")
    normalized = normalize_extracted_publication_date(original)
    item.published_at = normalized
    try:
        decision = _base_evaluate_freshness_policy(
            item,
            phase="post_extraction",
            now=now,
        )
    finally:
        item.published_at = original

    freshness = item.metadata.setdefault("freshness", {})
    freshness["post_freshness_version"] = POST_FRESHNESS_VERSION
    if normalized != original:
        freshness["extracted_date_raw"] = original
        freshness["extracted_date_normalized"] = normalized
    return decision


__all__ = [
    "POST_FRESHNESS_VERSION",
    "evaluate_post_extraction_freshness",
    "normalize_extracted_publication_date",
]
