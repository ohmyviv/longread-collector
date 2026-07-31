"""Collector v0.5.3 entrypoint with source, schedule and budget hotfixes."""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pipeline as _pipeline
from . import pipeline_v05 as _pipeline_v05
from . import sheets as _sheets
from .extraction import FallbackBudget
from .known_source_fixes import (
    KnownFallbackAwareDiscovery,
    select_sources_for_run,
)
from .models import DiscoveredURL, ExtractedArticle
from .operational_hotfix import (
    allocate_fallback_budget,
    resolve_source_name,
    scheduled_run_metrics,
)
from .recall_instrumentation import (
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
    install_recall_snapshot_hooks,
)
from .runtime_config import load_collector_runtime_config
from .sheets import GoogleSheetStore

_pipeline_v05.NativeSourceDiscovery = KnownFallbackAwareDiscovery
_pipeline_v05.select_sources_for_run = select_sources_for_run
install_recall_snapshot_hooks(_pipeline_v05, GoogleSheetStore)

_RUN_AUDIT_HEADERS = [
    "scheduled_at_bj",
    "start_delay_seconds",
    "fallback_group_cap",
    "fallback_group_used_before",
    "fallback_group_used_after",
    "fallback_group_remaining",
]
for _header in _RUN_AUDIT_HEADERS:
    if _header not in _sheets.RUN_HEADERS:
        _sheets.RUN_HEADERS.append(_header)

_CURRENT_GROUP: ContextVar[str] = ContextVar("collector_query_group", default="")
_ORIGINAL_EXTRACT_ARTICLE = _pipeline.extract_article
_ORIGINAL_COUNT_SCRAPES = GoogleSheetStore.count_firecrawl_scrapes_today


async def _extract_article_with_source_identity(
    discovered: DiscoveredURL,
    jina: Any,
    firecrawl: Any,
    settings: Any,
    fallback_budget: FallbackBudget | None = None,
) -> ExtractedArticle:
    article = await _ORIGINAL_EXTRACT_ARTICLE(
        discovered,
        jina,
        firecrawl,
        settings,
        fallback_budget,
    )
    extraction_metadata = article.metadata.get("extraction", {})
    resolved = resolve_source_name(discovered, extraction_metadata, article.domain)
    previous = article.canonical_source
    if resolved:
        article.canonical_source = resolved
        article.hosting_source = resolved
    article.metadata.setdefault("source_resolution", {})
    article.metadata["source_resolution"].update(
        {
            "version": "source-resolution-v0.5.3",
            "previous": previous,
            "resolved": resolved,
            "source_id": str(discovered.metadata.get("source_id", "")),
            "source_name": str(discovered.metadata.get("source_name", "")),
        }
    )
    query_group = _CURRENT_GROUP.get()
    for attempt in article.extraction_attempts:
        attempt.setdefault("query_group", query_group)
    return article


_pipeline.extract_article = _extract_article_with_source_identity


def _count_firecrawl_scrapes_today_by_group(
    self: GoogleSheetStore,
    query_group: str | None = None,
) -> int:
    if not query_group:
        return _ORIGINAL_COUNT_SCRAPES(self)
    ws = self.book.worksheet("extraction_log")
    rows = ws.get_all_records(expected_headers=_sheets.EXTRACTION_HEADERS)
    today = self._now().strftime("%Y-%m-%d")
    count = 0
    for row in rows:
        if not str(row.get("attempted_at_bj", "")).startswith(today):
            continue
        if str(row.get("extractor", "")).strip().lower() != "firecrawl":
            continue
        if str(row.get("error_type", "")).strip() == "DailyFallbackBudgetExhausted":
            continue
        try:
            payload = json.loads(str(row.get("response_meta_json", "") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if str(payload.get("query_group", "")) == str(query_group):
            count += 1
    return count


GoogleSheetStore.count_firecrawl_scrapes_today = _count_firecrawl_scrapes_today_by_group


class NativeCollectorPipeline(_pipeline_v05.NativeCollectorPipeline):
    """Run v0.5.3 while preserving immutable discovery and operational evidence."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._source_names: dict[str, str] = {}

    async def _extract_all(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        for item in discovered:
            source_id = str(item.metadata.get("source_id", ""))
            if source_id and not item.metadata.get("source_name"):
                item.metadata["source_name"] = self._source_names.get(source_id, source_id)
        return await super()._extract_all(discovered, fallback_budget)

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        group = str(group_id or "all")
        preflight_started = datetime.now(self.tz)
        runtime = load_collector_runtime_config(self.store)

        if query_file is None:
            schedule_queries = self.store.load_queries(group_id)
            language = "zh" if group.startswith("zh_") else "en"
            registry = self.store.load_source_registry(language)
            self._source_names = {
                str(row.get("source_id", "")): str(row.get("source_name", ""))
                for row in registry
                if row.get("source_id")
            }
        else:
            schedule_queries = _pipeline.load_queries(query_file, group_id)
            self._source_names = {}

        schedule = scheduled_run_metrics(preflight_started, schedule_queries, group_id)
        allocation = allocate_fallback_budget(self.store, runtime, group_id)
        synthetic_used = max(0, allocation.daily_limit - allocation.remaining)

        original_count = self.store.count_firecrawl_scrapes_today
        original_append = self.store.append_collector_run

        def budgeted_count(query_group: str | None = None) -> int:
            if query_group:
                return original_count(query_group=query_group)
            return synthetic_used

        def audited_append(values: dict[str, object]) -> None:
            synthetic_after = int(values.get("scrape_attempts_today") or synthetic_used)
            actual_fallbacks = max(0, synthetic_after - synthetic_used)
            values.update(schedule)
            values["scrape_attempts_today"] = allocation.total_used + actual_fallbacks
            values["fallback_group_cap"] = allocation.group_cap
            values["fallback_group_used_before"] = allocation.group_used
            values["fallback_group_used_after"] = allocation.group_used + actual_fallbacks
            values["fallback_group_remaining"] = int(
                values.get("fallback_remaining") or 0
            )
            original_append(values)

        self.store.count_firecrawl_scrapes_today = budgeted_count
        self.store.append_collector_run = audited_append
        group_token = _CURRENT_GROUP.set(group)
        snapshot_token = begin_snapshot_capture(group)
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            state = current_snapshot_capture()
            if state is not None:
                result["discovery_snapshot_rows"] = len(state.discoveries)
                result["discovery_snapshot_status"] = (
                    "failed" if state.snapshot_error else "success"
                )
                if state.snapshot_error:
                    result["discovery_snapshot_error"] = state.snapshot_error
            result.update(schedule)
            result["fallback_group_cap"] = allocation.group_cap
            result["fallback_group_used_before"] = allocation.group_used
            return result
        finally:
            end_snapshot_capture(snapshot_token)
            _CURRENT_GROUP.reset(group_token)
            self.store.count_firecrawl_scrapes_today = original_count
            self.store.append_collector_run = original_append
