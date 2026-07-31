"""Collector v0.5.4 entrypoint with ranked, source-aware URL selection."""

from __future__ import annotations

from typing import Any

# Patch the v0.5 module before importing v0.5.3. The latter installs immutable
# recall-snapshot hooks at import time and therefore must capture this ranked
# filter rather than the legacy first-seen filter.
from . import pipeline_v05 as _pipeline_v05
from .ranked_selection import filter_discovered as ranked_filter_discovered
from .sheets import GoogleSheetStore

_pipeline_v05.filter_discovered = ranked_filter_discovered

_ORIGINAL_APPEND_COLLECTOR_RUN = GoogleSheetStore.append_collector_run
_SELECTION_MARKER = (
    "selection_version=ranked-source-aware-v0.5.4; "
    "native_source_cap=4; open_domain_cap=2; absolute_host_cap=4"
)


def _append_collector_run_with_selection_version(
    self: GoogleSheetStore,
    values: dict[str, Any],
) -> None:
    notes = str(values.get("notes", "") or "")
    if "selection_version=ranked-source-aware-v0.5.4" not in notes:
        values["notes"] = f"{notes}; {_SELECTION_MARKER}" if notes else _SELECTION_MARKER
    _ORIGINAL_APPEND_COLLECTOR_RUN(self, values)


GoogleSheetStore.append_collector_run = _append_collector_run_with_selection_version

from .pipeline_v051 import NativeCollectorPipeline  # noqa: E402,F401

__all__ = ["NativeCollectorPipeline"]
