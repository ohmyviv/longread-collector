from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from longread_collector.final_recall_audit_v13 import evaluate_realized_coverage
from longread_collector.source_run_coverage import SOURCE_RUN_COVERAGE_VERSION

TZ = ZoneInfo("Asia/Shanghai")
RUN_ID = "COL-20260818-181236-BJT-zh_evening"
RUN_STARTED = "2026-08-18 18:12:36"
LEDGER_START = datetime(2026, 8, 18, 18, 12, 36, tzinfo=TZ)


def _item() -> dict[str, str]:
    return {
        "published_date": "2026-08-18 10:00:00+08:00",
        "item_observation_started_at_bj": RUN_STARTED,
        "cutoff_at_bj": "2026-08-18 19:00:00",
        "observation_coverage_status": "full",
        "measurement_age_bucket": "0_3d",
        "match_status": "not_discovered",
    }


def _source(source_id: str) -> dict[str, str]:
    return {"source_id": source_id, "source_name": source_id, "language": "zh"}


def _run() -> dict[str, str]:
    return {
        "collector_run_id": RUN_ID,
        "started_at_bj": RUN_STARTED,
        "query_group": "zh_evening",
        "notes": (
            f"source_run_coverage_version={SOURCE_RUN_COVERAGE_VERSION}; "
            "source_run_coverage_persisted=TRUE; source_run_coverage_rows=8"
        ),
    }


def _coverage(source_id: str, route_status: str) -> dict[str, object]:
    selected_method = "section_scan" if route_status == "native_success_date_unknown" else ""
    return {
        "collector_run_id": RUN_ID,
        "run_started_at_bj": RUN_STARTED,
        "source_id": source_id,
        "route_status": route_status,
        "selected_method": selected_method,
        "selected_endpoint": "https://example.com/",
        "oldest_observed_published_at": "",
        "newest_observed_published_at": "",
        "observed_horizon_hours": "",
        "coverage_confidence": "unknown",
        "coverage_version": SOURCE_RUN_COVERAGE_VERSION,
    }


@pytest.mark.parametrize(
    ("source_id", "route_status", "expected_status"),
    [
        ("yicai", "native_success_date_unknown", "observed_horizon_not_established"),
        ("jiemian-depth", "native_success_date_unknown", "observed_horizon_not_established"),
        ("chinawriter", "native_success_date_unknown", "observed_horizon_not_established"),
        ("zaobao-depth", "fallback_only", "fallback_only_target_missing"),
        ("caixin", "fallback_only", "fallback_only_target_missing"),
        ("cyol-freezingpoint", "fallback_only", "fallback_only_target_missing"),
        ("latepost", "fallback_zero", "fallback_zero_results"),
        ("caijing", "fallback_zero", "fallback_zero_results"),
    ],
)
def test_20260818_zh_evening_natural_v02_ledger_statuses(
    source_id: str,
    route_status: str,
    expected_status: str,
) -> None:
    """Acceptance fixture transcribed from the first natural v0.2 zh_evening ledger.

    This test intentionally freezes only the durable route-state facts needed by
    Final Recall v1.3. It does not replay discovery or contact any source.
    """

    assert SOURCE_RUN_COVERAGE_VERSION == "run-source-coverage-v0.2"
    result = evaluate_realized_coverage(
        item=_item(),
        source_row=_source(source_id),
        coverage_rows=[_coverage(source_id, route_status)],
        collector_runs=[_run()],
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.coverage_ledger_observation_status == "full"
    assert result.coverage_candidate_run_count == 1
    assert result.source_coverage_row_count == 1
    assert result.realized_coverage_status == expected_status
    assert result.coverage_contract_denominator_status == "coverage_contract_denominator"
    assert result.conditional_surface_denominator_status == "excluded"
