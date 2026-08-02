"""v0.5.6 PR-E: request, schedule and recall-audit observability."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pipeline as _pipeline
from . import pipeline_v056b as _pipeline_v056b
from . import sheets as _sheets
from .extraction import FallbackBudget
from .models import DiscoveredURL, ExtractedArticle
from .operational_audit_v056 import (
    FallbackRequestCounters,
    OPERATIONAL_AUDIT_VERSION,
    annotate_discovery_schedule,
    annotate_fallback_attempts,
    count_persisted_firecrawl_requests,
)
from .operational_hotfix import allocate_fallback_budget, scheduled_run_metrics
from .pipeline_v056d import NativeCollectorPipeline as _BasePipeline
from .runtime_config import load_collector_runtime_config
from .sheets import GoogleSheetStore

for _header in (
    "requests_sent",
    "requests_succeeded",
    "requests_failed",
    "requests_skipped_group_cap",
    "requests_skipped_daily_cap",
):
    if _header not in _sheets.RUN_HEADERS:
        _sheets.RUN_HEADERS.append(_header)

_CURRENT_GROUP: ContextVar[str] = ContextVar("v056e_query_group", default="all")
_CURRENT_COUNTERS: ContextVar[FallbackRequestCounters | None] = ContextVar(
    "v056e_request_counters", default=None
)
_CURRENT_SCHEDULE: ContextVar[dict[str, Any] | None] = ContextVar(
    "v056e_schedule", default=None
)

_ORIGINAL_EXTRACT = _pipeline.extract_article
_ORIGINAL_CORE_FILTER = _pipeline_v056b._core_filter
_ORIGINAL_COUNT = GoogleSheetStore.count_firecrawl_scrapes_today


async def _extract_with_request_audit(
    discovered: DiscoveredURL,
    jina: Any,
    firecrawl: Any,
    settings: Any,
    fallback_budget: FallbackBudget | None = None,
) -> ExtractedArticle:
    article = await _ORIGINAL_EXTRACT(
        discovered,
        jina,
        firecrawl,
        settings,
        fallback_budget,
    )
    counters = annotate_fallback_attempts(
        article,
        query_group=_CURRENT_GROUP.get(),
    )
    current = _CURRENT_COUNTERS.get()
    if current is not None:
        current.update(counters)
    return article


_pipeline.extract_article = _extract_with_request_audit


def _count_true_requests(
    self: GoogleSheetStore,
    query_group: str | None = None,
) -> int:
    ws = self.book.worksheet("extraction_log")
    rows = ws.get_all_records(expected_headers=_sheets.EXTRACTION_HEADERS)
    return count_persisted_firecrawl_requests(
        rows,
        date_prefix=self._now().strftime("%Y-%m-%d"),
        query_group=query_group,
    )


GoogleSheetStore.count_firecrawl_scrapes_today = _count_true_requests


def _filter_with_schedule(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
):
    schedule = _CURRENT_SCHEDULE.get() or {}
    annotate_discovery_schedule(
        discovered,
        scheduled_at_bj=str(schedule.get("scheduled_at_bj", "")),
        started_at_bj=str(schedule.get("started_at_bj", "")),
        start_delay_seconds=schedule.get("start_delay_seconds", ""),
    )
    return _ORIGINAL_CORE_FILTER(
        discovered,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )


_pipeline_v056b._core_filter = _filter_with_schedule


class NativeCollectorPipeline(_BasePipeline):
    """Run PR-A through PR-D with auditable request and schedule semantics."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        group = str(group_id or "all")
        started = datetime.now(self.tz)
        if query_file is None:
            schedule_queries = self.store.load_queries(group_id)
        else:
            schedule_queries = _pipeline.load_queries(query_file, group_id)
        schedule = scheduled_run_metrics(started, schedule_queries, group_id)
        schedule_context = {
            **schedule,
            "started_at_bj": started.strftime("%Y-%m-%d %H:%M:%S"),
        }

        runtime = load_collector_runtime_config(self.store)
        allocation = allocate_fallback_budget(self.store, runtime, group_id)
        daily_before = allocation.total_used
        group_before = allocation.group_used
        counters = FallbackRequestCounters()

        group_token: Token = _CURRENT_GROUP.set(group)
        counter_token: Token = _CURRENT_COUNTERS.set(counters)
        schedule_token: Token = _CURRENT_SCHEDULE.set(schedule_context)
        original_append = self.store.append_collector_run

        def append_with_operational_audit(values: dict[str, object]) -> None:
            sent = counters.requests_sent
            group_after = group_before + sent
            values.update(schedule)
            values["scrape_attempts_today"] = daily_before + sent
            values["fallback_group_cap"] = allocation.group_cap
            values["fallback_group_used_before"] = group_before
            values["fallback_group_used_after"] = group_after
            values["fallback_group_remaining"] = max(
                0,
                allocation.group_cap - group_after,
            )
            for key, value in counters.as_dict().items():
                values[key] = value
            notes = str(values.get("notes", "") or "")
            marker = (
                f"operational_audit_version={OPERATIONAL_AUDIT_VERSION}; "
                f"requests_sent={counters.requests_sent}; "
                f"requests_succeeded={counters.requests_succeeded}; "
                f"requests_failed={counters.requests_failed}; "
                f"requests_skipped_group_cap={counters.requests_skipped_group_cap}; "
                f"requests_skipped_daily_cap={counters.requests_skipped_daily_cap}"
            )
            if f"operational_audit_version={OPERATIONAL_AUDIT_VERSION}" not in notes:
                values["notes"] = f"{notes}; {marker}" if notes else marker
            original_append(values)

        self.store.append_collector_run = append_with_operational_audit
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            result.update(schedule)
            result["operational_audit_version"] = OPERATIONAL_AUDIT_VERSION
            result["fallback_request_audit"] = counters.as_dict()
            result["fallback_group_used_after"] = group_before + counters.requests_sent
            return result
        finally:
            self.store.append_collector_run = original_append
            _CURRENT_SCHEDULE.reset(schedule_token)
            _CURRENT_COUNTERS.reset(counter_token)
            _CURRENT_GROUP.reset(group_token)


__all__ = ["NativeCollectorPipeline"]
