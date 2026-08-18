from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from longread_collector.source_run_coverage import build_source_run_coverage_rows

TZ = ZoneInfo("Asia/Shanghai")
STARTED = datetime(2026, 8, 18, 4, 0, tzinfo=TZ)


def source():
    return {
        "source_id": "example",
        "source_name": "Example",
        "language": "en",
    }


def item(published_at: str):
    return SimpleNamespace(
        published_at=published_at,
        query_or_source="source:example",
        metadata={"source_id": "example", "purpose": "native_source_scan"},
    )


def native_log(count: int):
    return {
        "source_id": "example",
        "source_name": "Example",
        "success": True,
        "selected_method": "sitemap",
        "selected_endpoint": "https://example.com/sitemap.xml",
        "results_count": count,
        "fallback_needed": False,
        "attempts": [],
    }


def build(*published_values: str):
    return build_source_run_coverage_rows(
        run_id="COL-DATE-PRECISION",
        query_group="pre_report",
        started=STARTED,
        selected_sources=[source()],
        native_logs=[native_log(len(published_values))],
        native_items=[item(value) for value in published_values],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=STARTED,
    )[0]


def test_date_only_observation_uses_next_day_as_conservative_boundary() -> None:
    row = build("2026-08-17")

    assert row["route_status"] == "native_covered"
    assert row["dated_observation_count"] == 1
    assert row["oldest_observed_published_at"] == "2026-08-18 00:00:00"
    assert row["observed_horizon_hours"] == 4.0
    assert row["coverage_confidence"] == "lower_bound"


def test_same_day_date_only_observation_proves_zero_lookback_not_four_hours() -> None:
    row = build("2026-08-18")

    assert row["oldest_observed_published_at"] == "2026-08-18 04:00:00"
    assert row["observed_horizon_hours"] == 0.0


def test_timestamp_precision_keeps_literal_boundary() -> None:
    row = build("2026-08-17 08:00:00+08:00")

    assert row["oldest_observed_published_at"] == "2026-08-17 08:00:00"
    assert row["observed_horizon_hours"] == 20.0


def test_mixed_precision_uses_oldest_conservatively_proven_boundary() -> None:
    row = build(
        "2026-08-16",
        "2026-08-17 08:00:00+08:00",
        "2026-08-18 02:00:00+08:00",
    )

    # The date-only 8/16 item could have been published as late as 23:59:59,
    # so it proves coverage only back to the 8/17 midnight boundary.
    assert row["oldest_observed_published_at"] == "2026-08-17 00:00:00"
    assert row["observed_horizon_hours"] == 28.0
    assert row["newest_observed_published_at"] == "2026-08-18 02:00:00"


def test_future_timestamp_does_not_create_coverage_evidence() -> None:
    row = build("2026-08-18 05:00:00+08:00")

    assert row["dated_observation_count"] == 0
    assert row["route_status"] == "native_success_date_unknown"
    assert row["oldest_observed_published_at"] == ""
    assert row["observed_horizon_hours"] == ""
