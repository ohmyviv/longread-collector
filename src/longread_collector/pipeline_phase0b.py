"""Scoped Phase 0B scheduling helper for one Collector control run."""

from __future__ import annotations

from typing import Any

from . import pipeline_v05 as _pipeline_v05
from .runtime_config import load_collector_runtime_config
from .source_selection_phase0b import (
    SOURCE_SELECTION_POLICY_VERSION,
    SourceFreshnessPolicy,
    begin_source_selection,
    end_source_selection,
    select_sources_for_run,
    selection_audit_payload,
)


def _disabled_audit(group_id: str) -> dict[str, Any]:
    return {
        "version": SOURCE_SELECTION_POLICY_VERSION,
        "enabled": False,
        "group_id": group_id,
        "freshness_source_ids": [],
        "freshness_max_sources": 0,
        "selected": [],
        "missing_freshness_source_ids": [],
    }


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
        age = item.get("scan_age_hours")
        detail.append(
            f"{item.get('source_id', '')}:{item.get('selection_reason', '')}:"
            f"{'na' if age is None else age}"
        )
    return (
        f"source_selection_policy_version={SOURCE_SELECTION_POLICY_VERSION}; "
        f"source_selection_policy_enabled={str(bool(audit.get('enabled'))).upper()}; "
        f"source_selection_group={audit.get('group_id', '')}; "
        f"source_selection_selected={'|'.join(selected_ids)}; "
        f"source_selection_freshness={'|'.join(freshness_ids)}; "
        f"source_selection_missing={'|'.join(missing)}; "
        f"source_selection_detail={'|'.join(detail)}"
    )


def _apply_selection_marker(values: dict[str, object], audit: dict[str, Any]) -> None:
    """Idempotently add the Phase 0B audit marker to one final run row."""

    notes = str(values.get("notes", "") or "")
    marker_key = f"source_selection_policy_version={SOURCE_SELECTION_POLICY_VERSION}"
    if marker_key in notes:
        return
    marker = _compact_selection_marker(audit)
    values["notes"] = f"{notes}; {marker}" if notes else marker


class Phase0BSourceSelectionHook:
    def __init__(self, pipeline: object, group_id: str, query_file: object = None) -> None:
        self.pipeline = pipeline
        self.group_id = group_id
        self.query_file = query_file
        self.audit = _disabled_audit(group_id)
        self._token = None
        self._old_selector = None
        self._old_append = None
        self._direct_append_owner = None
        self._old_direct_append = None

    def __enter__(self):
        store = getattr(self.pipeline, "store", None)
        if store is None:
            return self
        runtime = load_collector_runtime_config(store)
        source_ids = tuple(runtime.native_freshness_sources_by_group.get(self.group_id, ()))
        policy = SourceFreshnessPolicy(
            enabled=(
                self.query_file is None
                and runtime.native_freshness_policy_enabled
                and bool(source_ids)
                and runtime.native_freshness_max_per_run > 0
            ),
            group_id=self.group_id,
            freshness_source_ids=source_ids,
            freshness_max_sources=min(
                runtime.native_freshness_max_per_run,
                runtime.native_source_scans_per_run,
            ),
        )
        self.audit = {
            "version": SOURCE_SELECTION_POLICY_VERSION,
            "enabled": policy.enabled,
            "group_id": policy.group_id,
            "freshness_source_ids": list(policy.freshness_source_ids),
            "freshness_max_sources": policy.freshness_max_sources,
            "selected": [],
            "missing_freshness_source_ids": [],
        }
        if not policy.enabled:
            return self

        self._token = begin_source_selection(policy)
        self._old_selector = _pipeline_v05.select_sources_for_run
        _pipeline_v05.select_sources_for_run = select_sources_for_run
        old_append = getattr(store, "append_collector_run", None)
        if callable(old_append):
            self._old_append = old_append

            def audited_append(values: dict[str, object]) -> None:
                _apply_selection_marker(values, selection_audit_payload())
                old_append(values)

            store.append_collector_run = audited_append

        # v0.5.6b intentionally bypasses outer append wrappers when it writes
        # the final collector_runs row so it can avoid re-appending the stale
        # v0.5.5 selection marker.  That direct sink also bypassed the Phase 0B
        # wrapper above.  Patch only that scoped sink for the lifetime of this
        # enabled Phase 0B run; preserve the legacy bypass semantics otherwise.
        from . import pipeline_v055 as _pipeline_v055

        old_direct_append = _pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN
        self._direct_append_owner = _pipeline_v055
        self._old_direct_append = old_direct_append

        def audited_direct_append(store_obj: object, values: dict[str, object]) -> None:
            _apply_selection_marker(values, selection_audit_payload())
            old_direct_append(store_obj, values)

        _pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN = audited_direct_append
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._token is None:
            return None
        self.audit = selection_audit_payload()
        store = getattr(self.pipeline, "store", None)
        if store is not None and self._old_append is not None:
            store.append_collector_run = self._old_append
        if self._old_selector is not None:
            _pipeline_v05.select_sources_for_run = self._old_selector
        if self._direct_append_owner is not None and self._old_direct_append is not None:
            self._direct_append_owner._ORIGINAL_APPEND_COLLECTOR_RUN = self._old_direct_append
        end_source_selection(self._token)
        return None


__all__ = [
    "Phase0BSourceSelectionHook",
    "SOURCE_SELECTION_POLICY_VERSION",
    "_compact_selection_marker",
]
