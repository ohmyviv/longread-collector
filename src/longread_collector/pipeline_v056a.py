"""v0.5.6 PR-A: effective native-route coverage on top of v0.5.5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import pipeline_v05 as _pipeline_v05
from . import pipeline_v055 as _pipeline_v055
from .effective_route_v056 import (
    EFFECTIVE_ROUTE_VERSION,
    EffectiveRouteDiscovery,
    begin_effective_route_audit,
    current_effective_route_audit,
    end_effective_route_audit,
)

# pipeline_v05 resolves this module-level class when each collection run starts.
# Patching here preserves all v0.5.5 prefilter, selection, source-chase and
# operational behavior while replacing only native metadata discovery.
_pipeline_v05.NativeSourceDiscovery = EffectiveRouteDiscovery


class NativeCollectorPipeline(_pipeline_v055.NativeCollectorPipeline):
    """Run v0.5.5 with the v0.5.6 effective native-route contract."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        route_token = begin_effective_route_audit()
        original_append = self.store.append_collector_run

        def append_with_route_audit(values: dict[str, Any]) -> None:
            audit = current_effective_route_audit() or {}
            notes = str(values.get("notes", "") or "")
            route_marker = (
                f"effective_route_version={EFFECTIVE_ROUTE_VERSION}; "
                f"effective_native_successes={audit.get('effective_native_successes', 0)}; "
                f"partial_native_routes={audit.get('partial_native_routes', 0)}; "
                f"no_native_results={audit.get('no_native_results', 0)}; "
                f"native_metadata_items={audit.get('items_discovered', 0)}; "
                f"native_lookback_days={audit.get('configured_lookback_days', 7)}; "
                f"native_metadata_limit={audit.get('metadata_limit_per_source', 24)}"
            )
            if f"effective_route_version={EFFECTIVE_ROUTE_VERSION}" not in notes:
                values["notes"] = f"{notes}; {route_marker}" if notes else route_marker
            original_append(values)

        self.store.append_collector_run = append_with_route_audit
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            audit = current_effective_route_audit() or {}
            result["effective_route_version"] = EFFECTIVE_ROUTE_VERSION
            result["effective_route_audit"] = audit
            return result
        finally:
            self.store.append_collector_run = original_append
            end_effective_route_audit(route_token)


__all__ = ["NativeCollectorPipeline"]
