"""Stage events, event-derived metrics and legacy-v0.6 comparison."""

from .events import (
    STAGE_EVENT_SCHEMA_VERSION,
    deterministic_event_id,
    make_stage_event,
)
from .metrics import (
    LegacySummaryComparison,
    StageEventMetrics,
    compare_legacy_summary,
    summarize_stage_events,
)

__all__ = [
    "LegacySummaryComparison",
    "STAGE_EVENT_SCHEMA_VERSION",
    "StageEventMetrics",
    "compare_legacy_summary",
    "deterministic_event_id",
    "make_stage_event",
    "summarize_stage_events",
]
