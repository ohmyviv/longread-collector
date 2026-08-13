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


class Phase0BSourceSelectionHook:
    def __init__(self, pipeline: object, group_id: str, query_file: object = None) -> None:
        self.pipeline = pipeline
        self.group_id = group_id
        self.query_file = query_file
        self.audit = _disabled_audit(group_id)
        self._token = None
        self._old_selector = None
        self._old_append = None

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
                audit = selection_audit_payload()
                notes = str(values.get("notes", "") or "")
                marker = _compact_selection_marker(audit)
                values["notes"] = f"{notes}; {marker}" if notes else marker
                old_append(values)

            store.append_collector_run = audited_append
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
        end_source_selection(self._token)
        return None


__all__ = [
    "Phase0BSourceSelectionHook",
    "SOURCE_SELECTION_POLICY_VERSION",
    "_compact_selection_marker",
]
