"""Scoped Phase 0B scheduling helper for one Collector control run."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import pipeline_v05 as _pipeline_v05
from .runtime_config import load_collector_runtime_config
from .source_coverage_debt import compute_coverage_debt_candidates
from .source_run_coverage import (
    SOURCE_RUN_COVERAGE_HEADERS,
    SOURCE_RUN_COVERAGE_SHEET,
)
from .source_selection_phase0b import (
    SOURCE_SELECTION_POLICY_VERSION,
    SourceFreshnessPolicy,
    begin_source_selection,
    current_source_selection_state,
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
        "coverage_debt_enabled": False,
        "coverage_debt_source_ids": [],
        "coverage_debt_max_sources": 0,
        "coverage_debt_error": "",
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
    debt_selected = [
        str(item.get("source_id", ""))
        for item in selected
        if str(item.get("selection_reason", "")) == "coverage_debt"
    ]
    debt_candidates = [
        str(value) for value in audit.get("coverage_debt_source_ids") or []
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
        f"source_selection_debt_enabled={str(bool(audit.get('coverage_debt_enabled'))).upper()}; "
        f"source_selection_debt_candidates={'|'.join(debt_candidates)}; "
        f"source_selection_debt_selected={'|'.join(debt_selected)}; "
        f"source_selection_debt_error={audit.get('coverage_debt_error', '')}; "
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
        self._coverage_rows: list[dict[str, Any]] = []
        self._coverage_debt_error = ""
        self._coverage_debt_projection_hours: float | None = None
        self._coverage_debt_safety_margin_hours = 2.0
        self._coverage_debt_min_samples = 2
        self._coverage_debt_recent_samples = 5

    def _audit_payload(self) -> dict[str, Any]:
        audit = selection_audit_payload()
        audit["coverage_debt_error"] = self._coverage_debt_error
        return audit

    def _select_with_dynamic_debt(
        self,
        sources: list[dict[str, Any]],
        *,
        started: Any,
        max_sources: int,
        rotate_share: float = 0.75,
    ) -> list[dict[str, Any]]:
        state = current_source_selection_state()
        if state is None:
            return select_sources_for_run(
                sources,
                started=started,
                max_sources=max_sources,
                rotate_share=rotate_share,
            )

        policy = state.policy
        candidate_ids: tuple[str, ...] = ()
        if (
            policy.coverage_debt_enabled
            and self._coverage_debt_projection_hours is not None
            and self._coverage_rows
        ):
            try:
                candidates = compute_coverage_debt_candidates(
                    sources=sources,
                    coverage_rows=self._coverage_rows,
                    started=started,
                    projection_hours=self._coverage_debt_projection_hours,
                    safety_margin_hours=self._coverage_debt_safety_margin_hours,
                    min_samples=self._coverage_debt_min_samples,
                    recent_samples=self._coverage_debt_recent_samples,
                )
                candidate_ids = tuple(candidate.source_id for candidate in candidates)
            except Exception as exc:
                self._coverage_debt_error = f"{type(exc).__name__}: {exc}"[:1000]

        state.policy = replace(policy, coverage_debt_source_ids=candidate_ids)
        return select_sources_for_run(
            sources,
            started=started,
            max_sources=max_sources,
            rotate_share=rotate_share,
        )

    def __enter__(self):
        store = getattr(self.pipeline, "store", None)
        if store is None:
            return self
        runtime = load_collector_runtime_config(store)
        source_ids = tuple(
            getattr(runtime, "native_freshness_sources_by_group", {}).get(
                self.group_id, ()
            )
        )
        freshness_enabled = (
            self.query_file is None
            and getattr(runtime, "native_freshness_policy_enabled", False)
            and bool(source_ids)
            and getattr(runtime, "native_freshness_max_per_run", 0) > 0
        )

        projection_map = getattr(
            runtime,
            "native_coverage_debt_projection_hours_by_group",
            {},
        )
        self._coverage_debt_projection_hours = projection_map.get(self.group_id)
        debt_requested = (
            self.query_file is None
            and getattr(runtime, "native_coverage_debt_policy_enabled", False)
            and getattr(runtime, "native_coverage_debt_max_per_run", 0) > 0
            and self._coverage_debt_projection_hours is not None
        )
        debt_enabled = debt_requested
        if debt_requested:
            try:
                self._coverage_rows = store.book.worksheet(
                    SOURCE_RUN_COVERAGE_SHEET
                ).get_all_records(expected_headers=SOURCE_RUN_COVERAGE_HEADERS)
                if not self._coverage_rows:
                    debt_enabled = False
                    self._coverage_debt_error = "coverage_ledger_empty"
            except Exception as exc:
                debt_enabled = False
                if exc.__class__.__name__ == "WorksheetNotFound":
                    self._coverage_debt_error = "coverage_ledger_unavailable"
                else:
                    self._coverage_debt_error = (
                        f"{type(exc).__name__}: {exc}"[:1000]
                    )

        self._coverage_debt_safety_margin_hours = float(
            getattr(runtime, "native_coverage_debt_safety_margin_hours", 2.0)
        )
        self._coverage_debt_min_samples = int(
            getattr(runtime, "native_coverage_debt_min_samples", 2)
        )
        self._coverage_debt_recent_samples = int(
            getattr(runtime, "native_coverage_debt_recent_samples", 5)
        )

        policy = SourceFreshnessPolicy(
            enabled=freshness_enabled or debt_requested,
            group_id=self.group_id,
            freshness_source_ids=source_ids,
            freshness_max_sources=min(
                getattr(runtime, "native_freshness_max_per_run", 0),
                getattr(runtime, "native_source_scans_per_run", 8),
            ),
            coverage_debt_enabled=debt_enabled,
            coverage_debt_source_ids=(),
            coverage_debt_max_sources=min(
                getattr(runtime, "native_coverage_debt_max_per_run", 0),
                getattr(runtime, "native_source_scans_per_run", 8),
            ),
            coverage_debt_min_rotation_slots=1,
        )
        self.audit = {
            "version": SOURCE_SELECTION_POLICY_VERSION,
            "enabled": policy.enabled,
            "group_id": policy.group_id,
            "freshness_source_ids": list(policy.freshness_source_ids),
            "freshness_max_sources": policy.freshness_max_sources,
            "coverage_debt_enabled": policy.coverage_debt_enabled,
            "coverage_debt_source_ids": [],
            "coverage_debt_max_sources": policy.coverage_debt_max_sources,
            "coverage_debt_error": self._coverage_debt_error,
            "selected": [],
            "missing_freshness_source_ids": [],
        }
        if not policy.enabled:
            return self

        self._token = begin_source_selection(policy)
        self._old_selector = _pipeline_v05.select_sources_for_run
        _pipeline_v05.select_sources_for_run = self._select_with_dynamic_debt
        old_append = getattr(store, "append_collector_run", None)
        if callable(old_append):
            self._old_append = old_append

            def audited_append(values: dict[str, object]) -> None:
                _apply_selection_marker(values, self._audit_payload())
                old_append(values)

            store.append_collector_run = audited_append

        from . import pipeline_v055 as _pipeline_v055

        old_direct_append = _pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN
        self._direct_append_owner = _pipeline_v055
        self._old_direct_append = old_direct_append

        def audited_direct_append(store_obj: object, values: dict[str, object]) -> None:
            _apply_selection_marker(values, self._audit_payload())
            old_direct_append(store_obj, values)

        _pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN = audited_direct_append
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._token is None:
            return None
        self.audit = self._audit_payload()
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
