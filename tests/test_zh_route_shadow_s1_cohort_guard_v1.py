from __future__ import annotations

from longread_collector.zh_route_shadow_s1_audit_v1 import AuditVerdict
from longread_collector.zh_route_shadow_s1_cohort_guard_v1 import (
    S1_ACTIVATED_AT_BJ,
    S1_COHORT_GUARD_VERSION,
    audit_prospective_s1_run,
)


def test_pre_activation_historical_zh_run_is_not_evaluable_not_failure() -> None:
    run_id = "COL-20260826-HISTORICAL-zh_evening"
    report = audit_prospective_s1_run(
        collector_run_id=run_id,
        run_rows=[
            {
                "collector_run_id": run_id,
                "started_at_bj": "2026-08-26 17:50:10",
                "query_group": "zh_evening",
                "final_status": "success",
                "notes": "",
            }
        ],
        coverage_rows=[],
        shadow_summary_rows=[],
        route_observation_rows=[],
        route_item_rows=[],
    )

    assert report.verdict == AuditVerdict.NOT_EVALUABLE
    assert report.eligible_exposure is False
    assert report.layers[0].checks["within_s1_activation_cohort"] is False
    assert report.layers[0].facts["cohort_guard_version"] == S1_COHORT_GUARD_VERSION
    assert report.layers[0].facts["s1_activated_at_bj"] == S1_ACTIVATED_AT_BJ.isoformat()


def test_missing_run_still_delegates_to_scheduler_not_evaluable() -> None:
    report = audit_prospective_s1_run(
        collector_run_id="COL-MISSING",
        run_rows=[],
        coverage_rows=[],
    )
    assert report.verdict == AuditVerdict.NOT_EVALUABLE
    assert report.eligible_exposure is False
    assert report.layers[0].checks["durable_control_run_exists"] is False
    assert report.layers[0].facts["cohort_guard_version"] == S1_COHORT_GUARD_VERSION


def test_post_activation_run_delegates_to_full_audit() -> None:
    run_id = "COL-POST-ACTIVATION"
    report = audit_prospective_s1_run(
        collector_run_id=run_id,
        run_rows=[
            {
                "collector_run_id": run_id,
                "started_at_bj": "2026-08-28 11:50:10",
                "query_group": "zh_midday",
                "final_status": "failed",
                "notes": "",
            }
        ],
        coverage_rows=[],
    )
    # The cohort guard must not hide a real post-activation Control failure.
    assert report.verdict == AuditVerdict.FAIL
    assert report.eligible_exposure is False
    assert report.layers[0].facts["s1_activated_at_bj"] == S1_ACTIVATED_AT_BJ.isoformat()
