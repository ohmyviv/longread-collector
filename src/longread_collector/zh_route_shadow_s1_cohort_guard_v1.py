"""Prospective cohort guard for the Chinese Route Shadow S1 audit.

The low-level audit engine can validate any ledger-shaped fixture.  This guard
adds the real experiment activation boundary so pre-S1 historical Chinese runs
cannot be mislabeled as Treatment telemetry failures merely because the sidecar
did not exist yet.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .zh_route_shadow_s1_audit_v1 import (
    AuditVerdict,
    LayerResult,
    S1_AUDIT_VERSION,
    S1AuditReport,
    audit_s1_run as _audit_s1_run,
    audit_surface_contracts,
)

S1_COHORT_GUARD_VERSION = "zh-route-shadow-s1-cohort-guard-v1"
# PR #134 merged to main at 2026-08-27 16:24:01 BJT. A durable Collector run
# that started before this instant was never eligible to emit S1 sidecar rows.
S1_ACTIVATED_AT_BJ = datetime(2026, 8, 27, 16, 24, 1, tzinfo=ZoneInfo("Asia/Shanghai"))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_started_at(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    else:
        parsed = parsed.astimezone(ZoneInfo("Asia/Shanghai"))
    return parsed


def audit_prospective_s1_run(
    *,
    collector_run_id: str,
    run_rows: Iterable[dict[str, Any]],
    coverage_rows: Iterable[dict[str, Any]],
    shadow_summary_rows: Iterable[dict[str, Any]] = (),
    route_observation_rows: Iterable[dict[str, Any]] = (),
    route_item_rows: Iterable[dict[str, Any]] = (),
) -> S1AuditReport:
    """Apply the frozen S1 activation cohort boundary, then run the base audit."""

    run_rows = list(run_rows)
    matching = [
        row for row in run_rows
        if _text(row.get("collector_run_id")) == collector_run_id
    ]
    if len(matching) == 1:
        started = _parse_started_at(matching[0].get("started_at_bj"))
        if started is not None and started < S1_ACTIVATED_AT_BJ:
            return S1AuditReport(
                audit_version=S1_AUDIT_VERSION,
                collector_run_id=collector_run_id,
                verdict=AuditVerdict.NOT_EVALUABLE,
                eligible_exposure=False,
                treatment_source_ids=[],
                layers=[
                    LayerResult(
                        layer="L0_scheduler_availability",
                        verdict=AuditVerdict.NOT_EVALUABLE,
                        checks={
                            "durable_control_run_exists": True,
                            "within_s1_activation_cohort": False,
                        },
                        facts={
                            "started_at_bj": started.isoformat(),
                            "s1_activated_at_bj": S1_ACTIVATED_AT_BJ.isoformat(),
                            "cohort_guard_version": S1_COHORT_GUARD_VERSION,
                        },
                        notes=[
                            "Run predates PR #134 activation; absent route sidecar is expected and must not count as S1 failure."
                        ],
                    )
                ],
                static_contract=audit_surface_contracts(),
            )

    report = _audit_s1_run(
        collector_run_id=collector_run_id,
        run_rows=run_rows,
        coverage_rows=coverage_rows,
        shadow_summary_rows=shadow_summary_rows,
        route_observation_rows=route_observation_rows,
        route_item_rows=route_item_rows,
    )
    if report.layers:
        report.layers[0].facts.setdefault(
            "s1_activated_at_bj", S1_ACTIVATED_AT_BJ.isoformat()
        )
        report.layers[0].facts.setdefault(
            "cohort_guard_version", S1_COHORT_GUARD_VERSION
        )
    return report


__all__ = [
    "S1_ACTIVATED_AT_BJ",
    "S1_COHORT_GUARD_VERSION",
    "audit_prospective_s1_run",
]
