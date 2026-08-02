"""Cost and schedule audit primitives for v0.5.6 PR-E."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .models import DiscoveredURL, ExtractedArticle

OPERATIONAL_AUDIT_VERSION = "operational-audit-v0.5.6e"
SKIPPED_BUDGET_ERRORS = {
    "DailyFallbackBudgetExhausted",
    "GroupFallbackBudgetExhausted",
}


@dataclass(slots=True)
class FallbackRequestCounters:
    requests_sent: int = 0
    requests_succeeded: int = 0
    requests_failed: int = 0
    requests_skipped_group_cap: int = 0
    requests_skipped_daily_cap: int = 0

    def update(self, other: "FallbackRequestCounters") -> None:
        for key, value in asdict(other).items():
            setattr(self, key, int(getattr(self, key)) + int(value))

    def as_dict(self) -> dict[str, int]:
        return {key: int(value) for key, value in asdict(self).items()}


def classify_firecrawl_attempt(attempt: dict[str, Any]) -> str:
    if str(attempt.get("extractor", "")).strip().lower() != "firecrawl":
        return "not_firecrawl"
    error_type = str(attempt.get("error_type", "")).strip()
    explicit = attempt.get("request_sent")
    if explicit is not None:
        sent = bool(explicit)
    else:
        sent = error_type not in SKIPPED_BUDGET_ERRORS
    if not sent:
        if error_type == "GroupFallbackBudgetExhausted":
            return "skipped_group_cap"
        return "skipped_daily_cap"
    if error_type:
        return "request_failed"
    return "request_succeeded"


def annotate_fallback_attempts(
    article: ExtractedArticle,
    *,
    query_group: str,
) -> FallbackRequestCounters:
    counters = FallbackRequestCounters()
    for attempt in article.extraction_attempts:
        if str(attempt.get("extractor", "")).strip().lower() != "firecrawl":
            continue
        outcome = classify_firecrawl_attempt(attempt)
        request_sent = outcome in {"request_succeeded", "request_failed"}
        attempt["request_sent"] = request_sent
        attempt["request_outcome"] = outcome
        attempt["query_group"] = query_group
        attempt["operational_audit_version"] = OPERATIONAL_AUDIT_VERSION
        if outcome == "request_succeeded":
            counters.requests_sent += 1
            counters.requests_succeeded += 1
        elif outcome == "request_failed":
            counters.requests_sent += 1
            counters.requests_failed += 1
        elif outcome == "skipped_group_cap":
            counters.requests_skipped_group_cap += 1
        elif outcome == "skipped_daily_cap":
            counters.requests_skipped_daily_cap += 1
    article.metadata.setdefault("fallback_request_audit", {}).update(
        {
            "version": OPERATIONAL_AUDIT_VERSION,
            "query_group": query_group,
            **counters.as_dict(),
        }
    )
    return counters


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("response_meta_json", "")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def count_persisted_firecrawl_requests(
    rows: Iterable[dict[str, Any]],
    *,
    date_prefix: str,
    query_group: str | None = None,
) -> int:
    count = 0
    for row in rows:
        if not str(row.get("attempted_at_bj", "")).startswith(date_prefix):
            continue
        if str(row.get("extractor", "")).strip().lower() != "firecrawl":
            continue
        payload = _payload(row)
        if query_group and str(payload.get("query_group", "")) != str(query_group):
            continue
        attempt = {
            "extractor": "firecrawl",
            "error_type": str(row.get("error_type", "")),
        }
        if "request_sent" in payload:
            attempt["request_sent"] = payload.get("request_sent")
        if classify_firecrawl_attempt(attempt) in {"request_succeeded", "request_failed"}:
            count += 1
    return count


def annotate_discovery_schedule(
    items: Iterable[DiscoveredURL],
    *,
    scheduled_at_bj: str,
    started_at_bj: str,
    start_delay_seconds: int | str,
) -> None:
    scheduled_time = ""
    if scheduled_at_bj:
        pieces = scheduled_at_bj.split(" ", 1)
        scheduled_time = pieces[1][:5] if len(pieces) == 2 else scheduled_at_bj[-5:]
    for item in items:
        item.metadata["scheduled_time_bj"] = scheduled_time
        item.metadata["scheduled_at_bj"] = scheduled_at_bj
        item.metadata["run_started_at_bj"] = started_at_bj
        item.metadata["start_delay_seconds"] = start_delay_seconds
        item.metadata["schedule_audit_version"] = OPERATIONAL_AUDIT_VERSION


__all__ = [
    "FallbackRequestCounters",
    "OPERATIONAL_AUDIT_VERSION",
    "SKIPPED_BUDGET_ERRORS",
    "annotate_discovery_schedule",
    "annotate_fallback_attempts",
    "classify_firecrawl_attempt",
    "count_persisted_firecrawl_requests",
]
