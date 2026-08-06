"""Event-derived run metrics and legacy-summary comparison."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..contracts import StageEvent, StageEventType

METRICS_VERSION = "v06-stage-event-metrics-v1"
_REQUIRED_RESULT_TYPES = (
    StageEventType.DISCOVERY_RESULT,
    StageEventType.GATE_RESULT,
    StageEventType.ACQUISITION_RESULT,
    StageEventType.CANONICAL_RESULT,
    StageEventType.EDITORIAL_RESULT,
    StageEventType.SELECTION_RESULT,
    StageEventType.PROJECTION_RESULT,
)


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class StageEventMetrics:
    metrics_version: str
    run_id: str
    event_count: int
    item_count: int
    closed_item_count: int
    incomplete_item_count: int
    duplicate_result_count: int
    stage_event_counts: Mapping[str, int] = field(default_factory=dict)
    event_type_counts: Mapping[str, int] = field(default_factory=dict)
    technical_status_counts: Mapping[str, int] = field(default_factory=dict)
    flow_status_counts: Mapping[str, int] = field(default_factory=dict)
    disposition_counts: Mapping[str, int] = field(default_factory=dict)
    selection_track_counts: Mapping[str, int] = field(default_factory=dict)
    extractor_attempt_counts: Mapping[str, int] = field(default_factory=dict)
    extractor_request_counts: Mapping[str, int] = field(default_factory=dict)
    extractor_success_counts: Mapping[str, int] = field(default_factory=dict)
    extractor_failure_counts: Mapping[str, int] = field(default_factory=dict)
    extractor_skipped_counts: Mapping[str, int] = field(default_factory=dict)
    selected_extractor_success_counts: Mapping[str, int] = field(default_factory=dict)
    acquisition_success_count: int = 0
    acquisition_failed_count: int = 0
    eligible_for_editor_count: int = 0
    firecrawl_requests_sent: int = 0
    firecrawl_requests_succeeded: int = 0
    firecrawl_requests_failed: int = 0
    firecrawl_requests_skipped_group_cap: int = 0
    firecrawl_requests_skipped_daily_cap: int = 0
    total_cost: float = 0.0
    closure_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "stage_event_counts",
            "event_type_counts",
            "technical_status_counts",
            "flow_status_counts",
            "disposition_counts",
            "selection_track_counts",
            "extractor_attempt_counts",
            "extractor_request_counts",
            "extractor_success_counts",
            "extractor_failure_counts",
            "extractor_skipped_counts",
            "selected_extractor_success_counts",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_mapping(getattr(self, field_name)),
            )


@dataclass(frozen=True, slots=True)
class LegacySummaryComparison:
    comparison_version: str
    compared_fields: tuple[str, ...]
    matched_fields: tuple[str, ...]
    differences: Mapping[str, tuple[Any, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "differences", _freeze_mapping(self.differences))

    @property
    def is_closed(self) -> bool:
        return not self.differences


def summarize_stage_events(events: Iterable[StageEvent]) -> StageEventMetrics:
    event_list = tuple(events)
    run_ids = {event.run_id for event in event_list if event.run_id}
    if len(run_ids) > 1:
        raise ValueError(f"events contain multiple run ids: {sorted(run_ids)}")
    run_id = next(iter(run_ids), "")

    stage_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    technical_counts: Counter[str] = Counter()
    flow_counts: Counter[str] = Counter()
    dispositions: Counter[str] = Counter()
    tracks: Counter[str] = Counter()
    attempt_counts: Counter[str] = Counter()
    request_counts: Counter[str] = Counter()
    success_counts: Counter[str] = Counter()
    failure_counts: Counter[str] = Counter()
    skipped_counts: Counter[str] = Counter()
    selected_extractor_success: Counter[str] = Counter()
    item_types: dict[str, Counter[StageEventType]] = defaultdict(Counter)

    acquisition_success = 0
    acquisition_failed = 0
    eligible = 0
    total_cost = 0.0
    fc_sent = fc_succeeded = fc_failed = fc_group = fc_daily = 0

    for event in event_list:
        stage_counts[event.stage.value] += 1
        type_counts[event.event_type.value] += 1
        technical_counts[event.technical_status.value] += 1
        flow_counts[event.flow_status.value] += 1
        item_types[event.item_id][event.event_type] += 1
        total_cost += float(event.cost or 0.0)

        attrs = event.attributes
        if event.event_type is StageEventType.EXTRACTOR_ATTEMPT:
            extractor = str(attrs.get("extractor", "unknown") or "unknown").lower()
            outcome = str(attrs.get("request_outcome", "") or "")
            request_sent = bool(attrs.get("request_sent", False))
            attempt_counts[extractor] += 1
            if request_sent:
                request_counts[extractor] += 1
            if outcome == "request_succeeded":
                success_counts[extractor] += 1
            elif outcome == "request_failed":
                failure_counts[extractor] += 1
            elif outcome.startswith("skipped_"):
                skipped_counts[extractor] += 1
            if extractor == "firecrawl":
                fc_sent += int(request_sent)
                fc_succeeded += int(outcome == "request_succeeded")
                fc_failed += int(outcome == "request_failed")
                fc_group += int(outcome == "skipped_group_cap")
                fc_daily += int(outcome == "skipped_daily_cap")

        elif event.event_type is StageEventType.ACQUISITION_RESULT:
            extraction_status = str(attrs.get("extraction_status", ""))
            if extraction_status == "success":
                acquisition_success += 1
                extractor = str(attrs.get("best_extractor", "") or "").lower()
                if extractor:
                    selected_extractor_success[extractor] += 1
            else:
                acquisition_failed += 1

        elif event.event_type is StageEventType.SELECTION_RESULT:
            track = str(attrs.get("selection_track", "") or "")
            if track:
                tracks[track] += 1

        elif event.event_type is StageEventType.PROJECTION_RESULT:
            disposition = str(attrs.get("candidate_disposition", "") or "")
            if disposition:
                dispositions[disposition] += 1
            eligible += int(bool(attrs.get("eligible_for_editor", False)))

    closure_errors: list[str] = []
    closed = 0
    duplicate_results = 0
    for item_id, counts in sorted(item_types.items()):
        missing = [
            event_type.value
            for event_type in _REQUIRED_RESULT_TYPES
            if counts[event_type] == 0
        ]
        duplicates = [
            event_type.value
            for event_type in _REQUIRED_RESULT_TYPES
            if counts[event_type] > 1
        ]
        duplicate_results += sum(
            counts[event_type] - 1
            for event_type in _REQUIRED_RESULT_TYPES
            if counts[event_type] > 1
        )
        if missing or duplicates:
            if missing:
                closure_errors.append(f"{item_id}:missing={','.join(missing)}")
            if duplicates:
                closure_errors.append(f"{item_id}:duplicate={','.join(duplicates)}")
        else:
            closed += 1

    item_count = len(item_types)
    return StageEventMetrics(
        metrics_version=METRICS_VERSION,
        run_id=run_id,
        event_count=len(event_list),
        item_count=item_count,
        closed_item_count=closed,
        incomplete_item_count=item_count - closed,
        duplicate_result_count=duplicate_results,
        stage_event_counts=dict(stage_counts),
        event_type_counts=dict(type_counts),
        technical_status_counts=dict(technical_counts),
        flow_status_counts=dict(flow_counts),
        disposition_counts=dict(dispositions),
        selection_track_counts=dict(tracks),
        extractor_attempt_counts=dict(attempt_counts),
        extractor_request_counts=dict(request_counts),
        extractor_success_counts=dict(success_counts),
        extractor_failure_counts=dict(failure_counts),
        extractor_skipped_counts=dict(skipped_counts),
        selected_extractor_success_counts=dict(selected_extractor_success),
        acquisition_success_count=acquisition_success,
        acquisition_failed_count=acquisition_failed,
        eligible_for_editor_count=eligible,
        firecrawl_requests_sent=fc_sent,
        firecrawl_requests_succeeded=fc_succeeded,
        firecrawl_requests_failed=fc_failed,
        firecrawl_requests_skipped_group_cap=fc_group,
        firecrawl_requests_skipped_daily_cap=fc_daily,
        total_cost=round(total_cost, 6),
        closure_errors=tuple(closure_errors),
    )


def compare_legacy_summary(
    summary: Mapping[str, Any],
    metrics: StageEventMetrics,
) -> LegacySummaryComparison:
    fallback = summary.get("fallback_request_audit", {})
    if not isinstance(fallback, Mapping):
        fallback = {}

    event_values: dict[str, Any] = {
        "jina_success": int(
            metrics.selected_extractor_success_counts.get("jina", 0)
        ),
        "firecrawl_success": int(
            metrics.selected_extractor_success_counts.get("firecrawl", 0)
        ),
        "failed": metrics.acquisition_failed_count,
        "requests_sent": metrics.firecrawl_requests_sent,
        "requests_succeeded": metrics.firecrawl_requests_succeeded,
        "requests_failed": metrics.firecrawl_requests_failed,
        "requests_skipped_group_cap": metrics.firecrawl_requests_skipped_group_cap,
        "requests_skipped_daily_cap": metrics.firecrawl_requests_skipped_daily_cap,
    }
    compared: list[str] = []
    matched: list[str] = []
    differences: dict[str, tuple[Any, Any]] = {}
    for field_name, event_value in event_values.items():
        if field_name in summary:
            legacy_value = summary[field_name]
        elif field_name in fallback:
            legacy_value = fallback[field_name]
        else:
            continue
        try:
            normalized_legacy = int(legacy_value)
        except (TypeError, ValueError):
            normalized_legacy = legacy_value
        compared.append(field_name)
        if normalized_legacy == event_value:
            matched.append(field_name)
        else:
            differences[field_name] = (normalized_legacy, event_value)

    return LegacySummaryComparison(
        comparison_version="v06-legacy-summary-comparison-v1",
        compared_fields=tuple(compared),
        matched_fields=tuple(matched),
        differences=differences,
    )


__all__ = [
    "LegacySummaryComparison",
    "METRICS_VERSION",
    "StageEventMetrics",
    "compare_legacy_summary",
    "summarize_stage_events",
]
