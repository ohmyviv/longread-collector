from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

import tldextract

from .models import DiscoveredURL

_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())
_GENERIC_SOURCE_NAMES = {
    "com", "org", "net", "gov", "edu", "co", "cn", "uk", "us", "io",
    "news", "website", "site", "publisher", "unknown",
}
_DEFAULT_SCHEDULES = {
    "intl_early": "23:20",
    "pre_report": "05:20",
    "zh_midday": "11:50",
    "zh_evening": "17:50",
}


def _clean_source(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text or text.lower() in _GENERIC_SOURCE_NAMES:
        return ""
    return text


def registered_domain_label(domain: str) -> str:
    """Return the registrable-domain label using the bundled Public Suffix List."""
    normalized = str(domain or "").lower().removeprefix("www.").split(":", 1)[0]
    extracted = _TLD_EXTRACT(normalized)
    return extracted.domain or normalized


def resolve_source_name(
    discovered: DiscoveredURL,
    extraction_metadata: dict[str, Any] | None,
    domain: str,
) -> str:
    """Prefer registry identity, then publisher metadata, then a PSL-safe label."""
    discovery_meta = discovered.metadata or {}
    for candidate in (
        discovery_meta.get("source_name"),
        (extraction_metadata or {}).get("siteName"),
        (extraction_metadata or {}).get("publisher"),
        discovery_meta.get("source_id"),
    ):
        cleaned = _clean_source(candidate)
        if cleaned:
            return cleaned
    return registered_domain_label(domain)


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour_text, minute_text = text.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def scheduled_run_metrics(
    started: datetime,
    queries: Iterable[dict[str, Any]],
    group_id: str | None,
) -> dict[str, Any]:
    """Resolve the nearest intended schedule at or before the actual start."""
    schedule_text = ""
    for query in queries:
        candidate = str(query.get("scheduled_time_bj", "")).strip()
        if _parse_hhmm(candidate):
            schedule_text = candidate
            break
    if not schedule_text:
        schedule_text = _DEFAULT_SCHEDULES.get(str(group_id or ""), "")
    parsed = _parse_hhmm(schedule_text)
    if parsed is None:
        return {"scheduled_at_bj": "", "start_delay_seconds": ""}

    hour, minute = parsed
    scheduled = started.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # A run that starts shortly after midnight may belong to the prior day's
    # 23:20 slot. Never record a materially future scheduled time.
    if scheduled > started + timedelta(minutes=5):
        scheduled -= timedelta(days=1)
    delay = max(0, int((started - scheduled).total_seconds()))
    return {
        "scheduled_at_bj": scheduled.strftime("%Y-%m-%d %H:%M:%S"),
        "start_delay_seconds": delay,
    }


@dataclass(slots=True)
class FallbackAllocation:
    daily_limit: int
    total_used: int
    group_cap: int
    group_used: int
    remaining: int


def _group_cap(runtime: Any, group_id: str | None) -> int:
    key = str(group_id or "all")
    mapping = {
        "intl_early": int(getattr(runtime, "firecrawl_fallback_intl_early_limit", 0)),
        "pre_report": int(getattr(runtime, "firecrawl_fallback_pre_report_limit", 1)),
        "zh_midday": int(getattr(runtime, "firecrawl_fallback_zh_midday_limit", 1)),
        "zh_evening": int(getattr(runtime, "firecrawl_fallback_zh_evening_limit", 1)),
    }
    return max(0, mapping.get(key, int(getattr(runtime, "firecrawl_fallback_daily_limit", 3))))


def allocate_fallback_budget(store: Any, runtime: Any, group_id: str | None) -> FallbackAllocation:
    """Reserve scrape fallback capacity per scheduled group within the daily cap."""
    daily_limit = max(0, int(getattr(runtime, "firecrawl_fallback_daily_limit", 3)))
    total_used = int(store.count_firecrawl_scrapes_today())
    group_used = int(store.count_firecrawl_scrapes_today(query_group=str(group_id or "all")))
    group_cap = _group_cap(runtime, group_id)
    remaining = min(
        max(0, daily_limit - total_used),
        max(0, group_cap - group_used),
    )
    return FallbackAllocation(
        daily_limit=daily_limit,
        total_used=total_used,
        group_cap=group_cap,
        group_used=group_used,
        remaining=remaining,
    )
