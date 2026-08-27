from __future__ import annotations

import json

from longread_collector.source_run_coverage import SOURCE_RUN_COVERAGE_VERSION
from longread_collector.v06.shadow.run_summary_persistence import SHADOW_RUN_SUMMARY_VERSION
from longread_collector.zh_route_shadow_contracts_v1 import (
    ROUTE_SHADOW_CONTRACT_VERSION,
    S1_BODY_MODE,
    active_s1_surfaces,
)
from longread_collector.zh_route_shadow_discovery_v1 import ROUTE_SHADOW_DISCOVERY_VERSION
from longread_collector.zh_route_shadow_s1_audit_v1 import (
    AuditVerdict,
    audit_s1_run,
    audit_surface_contracts,
)
from longread_collector.zh_route_shadow_telemetry_v1 import ROUTE_SHADOW_TELEMETRY_VERSION

RUN_ID = "COL-S1-AUDIT-FIXTURE"


def _run(*, group: str = "zh_midday") -> dict[str, str]:
    notes = "; ".join(
        [
            f"source_run_coverage_version={SOURCE_RUN_COVERAGE_VERSION}",
            "source_run_coverage_persisted=TRUE",
            "source_run_coverage_rows=8",
            "snapshot_persistence_status=success",
            "snapshot_expected_rows=120",
            "snapshot_persisted_rows=120",
            "snapshot_readback_performed=TRUE",
            "native_source_cap=4",
            "absolute_host_cap=4",
            "extraction_attempt_cap=32",
            "first_stage_attempts=24",
            "second_stage_attempts=8",
        ]
    )
    return {
        "collector_run_id": RUN_ID,
        "query_group": group,
        "started_at_bj": "2026-08-28 11:50:03",
        "final_status": "success",
        "notes": notes,
    }


def _coverage(selected_target: str | None = "yicai") -> list[dict[str, str]]:
    sources = ["yicai", "huxiu", "thepaper", "nfpeople", "fanpu", "guokr", "caijing", "latepost"]
    if selected_target is None:
        sources[0] = "twreporter"
    elif selected_target != "yicai":
        sources[0] = selected_target
    return [
        {
            "collector_run_id": RUN_ID,
            "query_group": "zh_midday",
            "source_id": source_id,
            "selected": "TRUE",
            "coverage_version": SOURCE_RUN_COVERAGE_VERSION,
        }
        for source_id in sources
    ]


def _shadow_summary() -> dict[str, str]:
    return {
        "collector_run_id": RUN_ID,
        "summary_version": SHADOW_RUN_SUMMARY_VERSION,
        "full_snapshot_invariant": "TRUE",
        "capture_gap_count": "0",
        "control_result_preserved": "TRUE",
    }


def _route_row(source_id: str, surface) -> dict[str, str]:
    return {
        "collector_run_id": RUN_ID,
        "source_id": source_id,
        "surface_id": surface.surface_id,
        "surface_role": surface.role.value,
        "publication_surface_id": surface.publication_surface_id,
        "endpoint": surface.url,
        "transport": surface.transport,
        "body_mode": S1_BODY_MODE,
        "route_contract_version": ROUTE_SHADOW_CONTRACT_VERSION,
        "route_discovery_version": ROUTE_SHADOW_DISCOVERY_VERSION,
        "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
        "request_success": "TRUE",
        "parse_success": "TRUE",
        "surface_status": "empty",
        "raw_item_count": "0",
        "unique_item_count": "0",
        "recent_item_count": "0",
        "dated_item_count": "0",
        "exact_timestamp_count": "0",
        "control_overlap_count": "0",
        "treatment_unique_count": "0",
        "noise_item_count": "0",
        "noise_reason_counts_json": "{}",
    }


def _empty_yicai_route_rows() -> list[dict[str, str]]:
    return [_route_row("yicai", surface) for surface in active_s1_surfaces("yicai")]


def test_static_preflight_freezes_21_active_surfaces_and_noise_isolation() -> None:
    result = audit_surface_contracts()
    assert result["pass"] is True
    assert result["active_surface_count"] == 21
    assert set(result["target_sources"]) == {"yicai", "eeo", "caixin", "jiemian-depth"}
    assert "section_clock_context_is_s1_observation_not_final_recall_A_level" in result["warnings"]


def test_missing_natural_run_is_not_evaluable_not_failure() -> None:
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[],
        coverage_rows=[],
    )
    assert report.verdict == AuditVerdict.NOT_EVALUABLE
    assert report.eligible_exposure is False
    assert report.layers[0].layer == "L0_scheduler_availability"


def test_natural_run_without_target_source_is_not_an_exposure() -> None:
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[_run()],
        coverage_rows=_coverage(selected_target=None),
        shadow_summary_rows=[_shadow_summary()],
    )
    assert report.verdict == AuditVerdict.NOT_EVALUABLE
    assert report.eligible_exposure is False


def test_complete_empty_yicai_surface_set_is_valid_day0_exposure() -> None:
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[_run()],
        coverage_rows=_coverage(),
        shadow_summary_rows=[_shadow_summary()],
        route_observation_rows=_empty_yicai_route_rows(),
        route_item_rows=[],
    )
    assert report.verdict == AuditVerdict.PASS
    assert report.eligible_exposure is True
    assert report.treatment_source_ids == ["yicai"]
    by_layer = {layer.layer: layer for layer in report.layers}
    assert by_layer["L3_telemetry_integrity"].facts["expected_surface_count"] == 6
    assert by_layer["L4_route_technical_health"].verdict == AuditVerdict.OBSERVE
    assert by_layer["L5_route_utility_evidence"].verdict == AuditVerdict.OBSERVE


def test_missing_one_expected_surface_invalidates_exposure() -> None:
    rows = _empty_yicai_route_rows()[:-1]
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[_run()],
        coverage_rows=_coverage(),
        shadow_summary_rows=[_shadow_summary()],
        route_observation_rows=rows,
    )
    assert report.verdict == AuditVerdict.FAIL
    assert report.eligible_exposure is False
    telemetry = next(layer for layer in report.layers if layer.layer == "L3_telemetry_integrity")
    assert telemetry.checks["expected_surface_set_complete"] is False


def test_item_ledger_recomputes_observation_counts_and_preserves_incremental_semantics() -> None:
    surface = active_s1_surfaces("yicai")[0]
    routes = _empty_yicai_route_rows()
    target = next(row for row in routes if row["surface_id"] == surface.surface_id)
    target.update(
        {
            "surface_status": "observed",
            "raw_item_count": "2",
            "unique_item_count": "2",
            "recent_item_count": "2",
            "dated_item_count": "2",
            "exact_timestamp_count": "2",
            "control_overlap_count": "1",
            "treatment_unique_count": "1",
            "noise_item_count": "1",
            "noise_reason_counts_json": json.dumps({"single_stock_flow_snapshot": 1}, separators=(",", ":")),
        }
    )
    common = {
        "collector_run_id": RUN_ID,
        "query_group": "zh_midday",
        "source_id": "yicai",
        "surface_id": surface.surface_id,
        "surface_role": surface.role.value,
        "publication_surface_id": surface.publication_surface_id,
        "endpoint": surface.url,
        "transport": surface.transport,
        "route_contract_version": ROUTE_SHADOW_CONTRACT_VERSION,
        "route_discovery_version": ROUTE_SHADOW_DISCOVERY_VERSION,
        "body_mode": S1_BODY_MODE,
        "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
        "published_at": "2026-08-28T10:00:00+08:00",
        "publication_time_confidence": "high",
        "within_freshness": "TRUE",
    }
    items = [
        {
            **common,
            "url_canonical": "https://www.yicai.com/news/1.html",
            "control_overlap": "TRUE",
            "noise_reason": "",
        },
        {
            **common,
            "url_canonical": "https://www.yicai.com/news/2.html",
            "control_overlap": "FALSE",
            "noise_reason": "single_stock_flow_snapshot",
        },
    ]
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[_run()],
        coverage_rows=_coverage(),
        shadow_summary_rows=[_shadow_summary()],
        route_observation_rows=routes,
        route_item_rows=items,
    )
    assert report.verdict == AuditVerdict.PASS
    utility = next(layer for layer in report.layers if layer.layer == "L5_route_utility_evidence")
    assert utility.facts["canonical_proven_recent_incremental"] == 1
    assert utility.facts["incremental_noise_rate"] == 1.0


def test_failed_snapshot_control_cannot_become_eligible_exposure() -> None:
    run = _run()
    run["notes"] = run["notes"].replace("snapshot_persistence_status=success", "snapshot_persistence_status=failed")
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[run],
        coverage_rows=_coverage(),
        shadow_summary_rows=[_shadow_summary()],
        route_observation_rows=_empty_yicai_route_rows(),
    )
    assert report.verdict == AuditVerdict.FAIL
    assert report.eligible_exposure is False


def test_runtime_unobservable_isolation_claims_remain_explicitly_unknown() -> None:
    report = audit_s1_run(
        collector_run_id=RUN_ID,
        run_rows=[_run()],
        coverage_rows=_coverage(),
        shadow_summary_rows=[_shadow_summary()],
        route_observation_rows=_empty_yicai_route_rows(),
    )
    isolation = next(layer for layer in report.layers if layer.layer == "L2_experimental_isolation")
    assert isolation.checks["treatment_body_requests_zero_runtime_observable"] is None
    assert isolation.checks["treatment_never_enters_candidate_selection_runtime_observable"] is None
    assert isolation.checks["treatment_article_cache_isolation_runtime_observable"] is None
