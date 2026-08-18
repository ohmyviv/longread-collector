from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.final_recall_audit_v13 import (
    _realized_summary,
    evaluate_realized_coverage,
)
from longread_collector.source_run_coverage import SOURCE_RUN_COVERAGE_VERSION

TZ = ZoneInfo("Asia/Shanghai")
LEDGER_START = datetime(2026, 8, 16, 0, 0, tzinfo=TZ)


def _item(
    published_date: str,
    *,
    observation_start: str = "2026-08-17 00:00:00",
    cutoff: str = "2026-08-18 07:35:00",
    match_status: str = "not_discovered",
):
    return {
        "published_date": published_date,
        "item_observation_started_at_bj": observation_start,
        "cutoff_at_bj": cutoff,
        "observation_coverage_status": "full",
        "measurement_age_bucket": "0_3d",
        "match_status": match_status,
    }


def _source(source_id: str = "ft", language: str = "en"):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "language": language,
    }


def _run(
    started: str,
    *,
    group: str = "intl_early",
    persisted: bool = True,
    instrumented: bool = True,
):
    notes = []
    if instrumented:
        notes.append(f"source_run_coverage_version={SOURCE_RUN_COVERAGE_VERSION}")
        notes.append(
            f"source_run_coverage_persisted={'TRUE' if persisted else 'FALSE'}"
        )
    return {
        "collector_run_id": f"RUN-{started}",
        "started_at_bj": started,
        "query_group": group,
        "notes": "; ".join(notes),
    }


def _coverage(
    *,
    source_id: str = "ft",
    run_id: str = "RUN-COVERED",
    started: str = "2026-08-18 04:00:00",
    oldest: str = "2026-08-16 20:00:00",
    newest: str = "2026-08-18 02:00:00",
    route_status: str = "native_covered",
):
    return {
        "collector_run_id": run_id,
        "run_started_at_bj": started,
        "source_id": source_id,
        "route_status": route_status,
        "selected_method": "rss" if route_status.startswith("native") else "",
        "selected_endpoint": "https://example.com/feed",
        "oldest_observed_published_at": oldest,
        "newest_observed_published_at": newest,
        "observed_horizon_hours": 32.0,
        "coverage_confidence": "lower_bound" if route_status == "native_covered" else "unknown",
    }


def test_exact_publication_datetime_inside_native_interval_is_covered() -> None:
    item = _item("2026-08-17 12:00:00+08:00")
    runs = [_run("2026-08-18 04:00:00")]
    coverage = [_coverage()]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=coverage,
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.realized_coverage_status == "realized_route_covered"
    assert result.coverage_contract_denominator_status == "coverage_contract_denominator"
    assert result.conditional_surface_denominator_status == "conditional_surface_denominator"
    assert result.realized_coverage_run_id == "RUN-COVERED"


def test_date_only_item_requires_full_calendar_day_enclosure() -> None:
    item = _item("2026-08-17")
    runs = [_run("2026-08-18 04:00:00")]
    coverage = [_coverage(oldest="2026-08-16 20:00:00")]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=coverage,
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.publication_precision == "date"
    assert result.realized_coverage_status == "realized_route_covered"


def test_date_only_same_day_scan_is_boundary_ambiguous() -> None:
    item = _item("2026-08-17")
    runs = [_run("2026-08-17 22:00:00")]
    coverage = [
        _coverage(
            started="2026-08-17 22:00:00",
            oldest="2026-08-16 20:00:00",
        )
    ]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=coverage,
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.realized_coverage_status == "publication_time_boundary_ambiguous"
    assert result.conditional_surface_denominator_status == "excluded"


def test_fallback_only_is_not_native_surface_coverage() -> None:
    item = _item("2026-08-17 12:00:00+08:00")
    runs = [_run("2026-08-18 04:00:00")]
    coverage = [_coverage(route_status="fallback_only")]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=coverage,
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.realized_coverage_status == "fallback_only_target_missing"
    assert result.coverage_contract_denominator_status == "coverage_contract_denominator"
    assert result.conditional_surface_denominator_status == "excluded"


def test_absent_source_row_with_complete_run_telemetry_means_not_selected() -> None:
    item = _item("2026-08-17 12:00:00+08:00")
    runs = [_run("2026-08-18 04:00:00")]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=[],
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.coverage_ledger_observation_status == "full"
    assert result.realized_coverage_status == "source_not_selected_in_window"
    assert result.coverage_contract_denominator_status == "coverage_contract_denominator"


def test_failed_or_missing_run_telemetry_fails_measurement_closed() -> None:
    item = _item("2026-08-17 12:00:00+08:00")
    runs = [_run("2026-08-18 04:00:00", persisted=False)]

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=[],
        collector_runs=runs,
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.coverage_ledger_observation_status == "evidence_gap"
    assert result.coverage_persistence_gap_runs == 1
    assert result.realized_coverage_status == "coverage_evidence_gap"
    assert result.coverage_contract_denominator_status == "coverage_evidence_gap"


def test_preinstrumentation_item_is_partial_not_a_contract_failure() -> None:
    item = _item(
        "2026-08-15 12:00:00+08:00",
        observation_start="2026-08-15 12:00:00",
    )

    result = evaluate_realized_coverage(
        item=item,
        source_row=_source(),
        coverage_rows=[],
        collector_runs=[],
        ledger_started_at=LEDGER_START,
        tz=TZ,
    )

    assert result.coverage_ledger_observation_status == "partial"
    assert result.realized_coverage_status == "coverage_ledger_partial_observation"
    assert result.coverage_contract_denominator_status == "coverage_ledger_partial_observation"


def test_realized_summary_separates_contract_from_conditional_surface_recall() -> None:
    items = [
        {
            "coverage_contract_denominator_status": "coverage_contract_denominator",
            "realized_coverage_status": "realized_route_covered",
            "conditional_surface_denominator_status": "conditional_surface_denominator",
            "match_status": "captured_eligible",
        },
        {
            "coverage_contract_denominator_status": "coverage_contract_denominator",
            "realized_coverage_status": "source_not_selected_in_window",
            "conditional_surface_denominator_status": "excluded",
            "match_status": "not_discovered",
        },
        {
            "coverage_contract_denominator_status": "coverage_contract_denominator",
            "realized_coverage_status": "realized_route_covered",
            "conditional_surface_denominator_status": "conditional_surface_denominator",
            "match_status": "not_discovered",
        },
        {
            "coverage_contract_denominator_status": "coverage_ledger_partial_observation",
            "realized_coverage_status": "coverage_ledger_partial_observation",
            "conditional_surface_denominator_status": "excluded",
            "match_status": "not_discovered",
        },
    ]

    summary = _realized_summary(items, LEDGER_START)

    assert summary["realized_coverage_contract_denominator"] == 3
    assert summary["realized_coverage_contract_covered"] == 2
    assert summary["realized_coverage_contract_rate"] == 2 / 3
    assert summary["conditional_surface_recall_denominator"] == 2
    assert summary["conditional_surface_recall_discovered"] == 1
    assert summary["conditional_surface_recall"] == 0.5
    assert summary["conditional_surface_editable"] == 1
    assert summary["coverage_ledger_partial_items"] == 1
