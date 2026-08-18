from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from longread_collector.pipeline_phase0b import Phase0BSourceSelectionHook
from longread_collector.source_run_coverage import SOURCE_RUN_COVERAGE_VERSION
from longread_collector.source_selection_phase0b import (
    SourceFreshnessPolicy,
    begin_source_selection,
    end_source_selection,
    selection_audit_payload,
)

TZ = ZoneInfo("Asia/Shanghai")


def src(source_id: str, tier: str = "rotate"):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "priority_tier": tier,
        "enabled": True,
        "last_scanned_at_bj": "2026-08-16 00:00:00",
        "parser_config_json": "{}",
    }


def coverage(source_id: str, started: str, horizon: float, route="native_covered"):
    return {
        "source_id": source_id,
        "run_started_at_bj": started,
        "route_status": route,
        "observed_horizon_hours": horizon,
        "coverage_version": SOURCE_RUN_COVERAGE_VERSION,
    }


def test_hook_computes_debt_using_actual_selector_start_time() -> None:
    started = datetime(2026, 8, 17, 22, 52, tzinfo=TZ)
    sources = [
        src("fresh1"),
        src("fresh2"),
        src("fresh3"),
        src("fresh4"),
        src("fresh5"),
        src("fresh6"),
        src("ft"),
        src("ordinary", tier="explore"),
    ]
    policy = SourceFreshnessPolicy(
        enabled=True,
        group_id="intl_early",
        freshness_source_ids=(
            "fresh1",
            "fresh2",
            "fresh3",
            "fresh4",
            "fresh5",
            "fresh6",
        ),
        freshness_max_sources=6,
        coverage_debt_enabled=True,
        coverage_debt_max_sources=1,
    )
    hook = Phase0BSourceSelectionHook(SimpleNamespace(), "intl_early")
    hook._coverage_rows = [
        coverage("ft", "2026-08-16 22:50:00", 18.8),
        coverage("ft", "2026-08-14 23:17:00", 21.5),
    ]
    hook._coverage_debt_projection_hours = 5.5
    hook._coverage_debt_safety_margin_hours = 2.0
    hook._coverage_debt_min_samples = 2
    hook._coverage_debt_recent_samples = 5

    token = begin_source_selection(policy)
    try:
        selected = hook._select_with_dynamic_debt(
            sources,
            started=started,
            max_sources=8,
        )
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)

    assert len(selected) == 8
    assert audit["coverage_debt_source_ids"] == ["ft"]
    ft_row = next(row for row in audit["selected"] if row["source_id"] == "ft")
    assert ft_row["selection_reason"] == "coverage_debt"
    assert sum(
        row["selection_reason"] == "coverage_rotation" for row in audit["selected"]
    ) == 1


def test_hook_excludes_route_debt_even_if_historical_horizons_exist() -> None:
    started = datetime(2026, 8, 17, 22, 52, tzinfo=TZ)
    policy = SourceFreshnessPolicy(
        enabled=True,
        group_id="intl_early",
        coverage_debt_enabled=True,
        coverage_debt_max_sources=1,
    )
    hook = Phase0BSourceSelectionHook(SimpleNamespace(), "intl_early")
    hook._coverage_rows = [
        coverage("reuters-special", "2026-08-17 22:00:00", 0, route="fallback_only"),
        coverage("reuters-special", "2026-08-16 22:00:00", 36.0),
        coverage("reuters-special", "2026-08-15 22:00:00", 40.0),
    ]
    hook._coverage_debt_projection_hours = 5.5

    token = begin_source_selection(policy)
    try:
        hook._select_with_dynamic_debt(
            [src("reuters-special"), src("ordinary", tier="explore")],
            started=started,
            max_sources=2,
        )
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)

    assert audit["coverage_debt_source_ids"] == []
    assert not any(
        row["selection_reason"] == "coverage_debt" for row in audit["selected"]
    )
