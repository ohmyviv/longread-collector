"""Collector v0.5.5 entrypoint with v0.5.6 native-route hardening."""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import classification as _classification
from . import operational_hotfix as _operational_hotfix
from . import quality as _quality
from .classification_v055 import CLASSIFICATION_VERSION, classify_candidate_v055

_classification.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_classification.classify_candidate = classify_candidate_v055
_quality.classify_candidate = classify_candidate_v055
_operational_hotfix._DEFAULT_SCHEDULES.update(
    {
        "intl_early": "22:30",
        "pre_report": "03:57",
        "zh_midday": "11:50",
        "zh_evening": "17:50",
    }
)

from . import pipeline_v05 as _pipeline_v05  # noqa: E402
from .prefilter_v055 import PREFILTER_VERSION, filter_discovered  # noqa: E402
from .ranked_selection_v055 import (  # noqa: E402
    ABSOLUTE_HOST_CAP,
    NATIVE_BUCKET_TARGET,
    NATIVE_SOURCE_CAP,
    OPEN_BUCKET_TARGET,
    OPEN_DOMAIN_CAP,
    SELECTION_VERSION,
)
from .source_chase_v055 import build_source_chase_queries_v055  # noqa: E402

_pipeline_v05.filter_discovered = filter_discovered
_pipeline_v05.build_source_chase_queries = build_source_chase_queries_v055

from . import pipeline as _pipeline  # noqa: E402
from .extraction import FallbackBudget  # noqa: E402
from .operational_hotfix import allocate_fallback_budget  # noqa: E402
from .pipeline_v051 import NativeCollectorPipeline as _BasePipeline  # noqa: E402
from .native_routes_v056 import (  # noqa: E402
    NATIVE_ROUTE_VERSION,
    EffectiveNativeRouteDiscovery,
    current_native_route_audit,
    reset_native_route_audit,
    select_sources_for_run_v056,
)
from .runtime_config import load_collector_runtime_config  # noqa: E402
from .sheets import GoogleSheetStore  # noqa: E402

# pipeline_v051 installs the v0.5.1 discovery class while importing. Apply the
# v0.5.6 route layer afterwards so scheduled production shadow runs use it.
_pipeline_v05.NativeSourceDiscovery = EffectiveNativeRouteDiscovery
_pipeline_v05.select_sources_for_run = select_sources_for_run_v056


@dataclass(frozen=True, slots=True)
class _FallbackLimitContext:
    error_type: str
    error_message: str


_FALLBACK_LIMIT: ContextVar[_FallbackLimitContext | None] = ContextVar(
    "v055_fallback_limit", default=None
)
_ORIGINAL_PIPELINE_EXTRACT = _pipeline.extract_article
_ORIGINAL_APPEND_COLLECTOR_RUN = GoogleSheetStore.append_collector_run
_SELECTION_MARKER = (
    f"prefilter_version={PREFILTER_VERSION}; "
    f"selection_version={SELECTION_VERSION}; "
    f"native_route_version={NATIVE_ROUTE_VERSION}; "
    f"native_bucket_target={NATIVE_BUCKET_TARGET}; "
    f"open_bucket_target={OPEN_BUCKET_TARGET}; "
    f"native_source_cap={NATIVE_SOURCE_CAP}; "
    f"open_domain_cap={OPEN_DOMAIN_CAP}; absolute_host_cap={ABSOLUTE_HOST_CAP}; "
    "source_chase_version=deterministic-v0.5.5; "
    "classification_version=collector-v0.5.5"
)


async def _extract_article_with_precise_budget_error(
    discovered: Any,
    jina: Any,
    firecrawl: Any,
    settings: Any,
    fallback_budget: FallbackBudget | None = None,
):
    article = await _ORIGINAL_PIPELINE_EXTRACT(
        discovered,
        jina,
        firecrawl,
        settings,
        fallback_budget,
    )
    context = _FALLBACK_LIMIT.get()
    if context is not None:
        for attempt in article.extraction_attempts:
            if attempt.get("error_type") == "DailyFallbackBudgetExhausted":
                attempt["error_type"] = context.error_type
                attempt["error_message"] = context.error_message
    return article


_pipeline.extract_article = _extract_article_with_precise_budget_error


def _append_collector_run_with_v055_marker(
    self: GoogleSheetStore,
    values: dict[str, Any],
) -> None:
    notes = str(values.get("notes", "") or "")
    notes = notes.replace(
        "classification_version=collector-v0.4.0",
        "classification_version=collector-v0.5.5",
    )
    if f"selection_version={SELECTION_VERSION}" not in notes:
        notes = f"{notes}; {_SELECTION_MARKER}" if notes else _SELECTION_MARKER

    route_audit = current_native_route_audit()
    if route_audit:
        effective = sum(
            row.get("native_route_status") == "effective_native"
            for row in route_audit
        )
        partial = sum(
            row.get("native_route_status") == "partial_native"
            for row in route_audit
        )
        no_results = sum(
            row.get("native_route_status") in {"no_native_results", "fallback_only"}
            for row in route_audit
        )
        compact = [
            {
                "source_id": row.get("source_id", ""),
                "status": row.get("native_route_status", ""),
                "items_seen": row.get("items_seen", 0),
                "oldest_item_at": row.get("oldest_item_at", ""),
                "effective_lookback_hours": row.get("effective_lookback_hours"),
                "sections_covered": row.get("sections_covered", []),
                "fallback_needed": row.get("fallback_needed", False),
            }
            for row in route_audit
        ]
        notes += (
            f"; effective_native_sources={effective}; "
            f"partial_native_sources={partial}; "
            f"native_no_result_sources={no_results}; "
            "native_route_audit="
            + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        )
    values["notes"] = notes
    _ORIGINAL_APPEND_COLLECTOR_RUN(self, values)


GoogleSheetStore.append_collector_run = _append_collector_run_with_v055_marker


class NativeCollectorPipeline(_BasePipeline):
    """Run v0.5.5 with the v0.5.6 effective-native-route layer."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        runtime = load_collector_runtime_config(self.store)
        allocation = allocate_fallback_budget(self.store, runtime, group_id)
        daily_remaining = max(0, allocation.daily_limit - allocation.total_used)
        group_remaining = max(0, allocation.group_cap - allocation.group_used)
        if daily_remaining <= 0:
            limit_context = _FallbackLimitContext(
                error_type="DailyFallbackBudgetExhausted",
                error_message=(
                    "Firecrawl scrape fallback skipped because the daily "
                    "free-tier budget is exhausted"
                ),
            )
        elif group_remaining <= daily_remaining:
            limit_context = _FallbackLimitContext(
                error_type="GroupFallbackBudgetExhausted",
                error_message=(
                    "Firecrawl scrape fallback skipped because this query "
                    "group's reserved budget is exhausted"
                ),
            )
        else:
            limit_context = _FallbackLimitContext(
                error_type="DailyFallbackBudgetExhausted",
                error_message=(
                    "Firecrawl scrape fallback skipped because the daily "
                    "free-tier budget is exhausted"
                ),
            )

        reset_native_route_audit()
        token = _FALLBACK_LIMIT.set(limit_context)
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            route_audit = current_native_route_audit()
            result["prefilter_version"] = PREFILTER_VERSION
            result["selection_version"] = SELECTION_VERSION
            result["classification_version"] = CLASSIFICATION_VERSION
            result["source_chase_version"] = "deterministic-v0.5.5"
            result["native_route_version"] = NATIVE_ROUTE_VERSION
            result["native_route_audit"] = route_audit
            result["effective_native_sources"] = sum(
                row.get("native_route_status") == "effective_native"
                for row in route_audit
            )
            return result
        finally:
            _FALLBACK_LIMIT.reset(token)


__all__ = ["NativeCollectorPipeline"]
