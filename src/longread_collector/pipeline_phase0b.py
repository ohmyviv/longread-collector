"""Phase 0B source-selection wrapper over the frozen v0.5.6m control path.

The wrapper changes only which registered sources occupy the existing native
source-scan slots when the opt-in freshness policy is enabled. Downstream
v0.5.6m extraction/classification semantics remain unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import pipeline_v05 as _pipeline_v05
from .pipeline_v056f import NativeCollectorPipeline as _BasePipeline
from .runtime_config import load_collector_runtime_config
from .source_selection_phase0b import (
    SOURCE_SELECTION_POLICY_VERSION,
    SourceFreshnessPolicy,
    begin_source_selection,
    end_source_selection,
    select_sources_for_run,
    selection_audit_payload,
)

# pipeline_v05 resolves this module global when each run selects native sources.
# v0.5.3 previously pointed it at the known-source-fix selector; this Phase 0B
# selector preserves that fix layer internally and adds an opt-in scheduling
# policy on top.
_pipeline_v05.select_sources_for_run = select_sources_for_run


def _compact_selection_marker(audit: dict[str, Any]) -> str:
    selected = list(audit.get("selected") or [])
    selected_ids = [str(item.get("source_id", "")) for item in selected]
    freshness_ids = [
        str(item.get("source_id", ""))
        for item in selected
        if str(item.get("selection_reason", "")) == "freshness_reserve"
    ]
    missing = [str(value) for value in audit.get("missing_freshness_source_ids") or []]
    detail = []
    for item in selected:
        source_id = str(item.get("source_id", ""))
        reason = str(item.get("selection_reason", ""))
        age = item.get("scan_age_hours")
        age_text = "na" if age is None else str(age)
        detail.append(f"{source_id}:{reason}:{age_text}")
    return (
        f"source_selection_policy_version={SOURCE_SELECTION_POLICY_VERSION}; "
        f"source_selection_policy_enabled={str(bool(audit.get('enabled'))).upper()}; "
        f"source_selection_group={audit.get('group_id', '')}; "
        f"source_selection_selected={'|'.join(selected_ids)}; "
        f"source_selection_freshness={'|'.join(freshness_ids)}; "
        f"source_selection_missing={'|'.join(missing)}; "
        f"source_selection_detail={'|'.join(detail)}"
    )


class NativeCollectorPipeline(_BasePipeline):
    """Run frozen v0.5.6m semantics with opt-in Phase 0B source scheduling."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        group = str(group_id or "all")
        runtime = load_collector_runtime_config(self.store)
        source_ids = tuple(runtime.native_freshness_sources_by_group.get(group, ()))
        policy = SourceFreshnessPolicy(
            enabled=(
                query_file is None
                and runtime.native_freshness_policy_enabled
                and bool(source_ids)
                and runtime.native_freshness_max_per_run > 0
            ),
            group_id=group,
            freshness_source_ids=source_ids,
            freshness_max_sources=min(
                runtime.native_freshness_max_per_run,
                runtime.native_source_scans_per_run,
            ),
        )

        token = begin_source_selection(policy)
        original_append = self.store.append_collector_run

        def append_with_selection_audit(values: dict[str, object]) -> None:
            audit = selection_audit_payload()
            marker = _compact_selection_marker(audit)
            notes = str(values.get("notes", "") or "")
            if "source_selection_policy_version=" not in notes:
                values["notes"] = f"{notes}; {marker}" if notes else marker
            original_append(values)

        self.store.append_collector_run = append_with_selection_audit
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            audit = selection_audit_payload()
            result["source_selection_policy_version"] = SOURCE_SELECTION_POLICY_VERSION
            result["source_selection_audit"] = audit
            result["source_selection_policy_enabled"] = bool(audit.get("enabled"))
            result["freshness_sources_selected"] = sum(
                str(item.get("selection_reason", "")) == "freshness_reserve"
                for item in audit.get("selected", ())
                if isinstance(item, dict)
            )
            return result
        finally:
            self.store.append_collector_run = original_append
            end_source_selection(token)


__all__ = [
    "NativeCollectorPipeline",
    "SOURCE_SELECTION_POLICY_VERSION",
    "_compact_selection_marker",
]
