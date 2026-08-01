"""Collector v0.5.5 entrypoint with editorial hard gates and bucketed recall."""

from __future__ import annotations

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
from .runtime_config import load_collector_runtime_config  # noqa: E402
from .sheets import GoogleSheetStore  # noqa: E402


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
    values["notes"] = notes
    _ORIGINAL_APPEND_COLLECTOR_RUN(self, values)


GoogleSheetStore.append_collector_run = _append_collector_run_with_v055_marker


class NativeCollectorPipeline(_BasePipeline):
    """Run v0.5.5 while preserving all v0.5.3 operational evidence."""

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

        token = _FALLBACK_LIMIT.set(limit_context)
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            result["prefilter_version"] = PREFILTER_VERSION
            result["selection_version"] = SELECTION_VERSION
            result["classification_version"] = CLASSIFICATION_VERSION
            result["source_chase_version"] = "deterministic-v0.5.5"
            return result
        finally:
            _FALLBACK_LIMIT.reset(token)


__all__ = ["NativeCollectorPipeline"]
