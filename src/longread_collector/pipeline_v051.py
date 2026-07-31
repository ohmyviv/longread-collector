"""Collector v0.5.1 entrypoint with source repairs and recall instrumentation."""

from pathlib import Path
from typing import Any

from . import pipeline_v05 as _pipeline_v05
from .known_source_fixes import (
    KnownFallbackAwareDiscovery,
    select_sources_for_run,
)
from .recall_instrumentation import (
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
    install_recall_snapshot_hooks,
)
from .sheets import GoogleSheetStore

_pipeline_v05.NativeSourceDiscovery = KnownFallbackAwareDiscovery
_pipeline_v05.select_sources_for_run = select_sources_for_run
install_recall_snapshot_hooks(_pipeline_v05, GoogleSheetStore)


class NativeCollectorPipeline(_pipeline_v05.NativeCollectorPipeline):
    """Run v0.5.1 while preserving immutable raw-discovery evidence."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        token = begin_snapshot_capture(group_id or "all")
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
            return result
        finally:
            end_snapshot_capture(token)
