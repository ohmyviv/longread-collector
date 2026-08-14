from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.final_recall_audit_v12 import (
    _age_bucket,
    _item_snapshots,
    _measurement_denominator_status,
    _measurement_summary,
    _measurement_validity,
    _observation_coverage_status,
    _observation_start,
    _track_window_status,
    no_final_items_summary,
)

TZ = ZoneInfo("Asia/Shanghai")
CUTOFF = datetime(2026, 8, 12, 7, 35, tzinfo=TZ)


def test_deep_read_item_observes_from_publication_not_global_48h() -> None:
    published = datetime(2026, 8, 5, 0, 0, tzinfo=TZ)
    validity = _measurement_validity(published, CUTOFF, max_observation_days=14)
    start = _observation_start(
        published,
        CUTOFF,
        max_observation_days=14,
        validity=validity,
    )

    assert validity == "valid"
    assert start == published
    assert start < datetime(2026, 8, 10, 7, 35, tzinfo=TZ)
    assert _age_bucket(7) == "4_7d"
    assert _track_window_status("deep_read", published, CUTOFF, validity) == "consistent_deep_read"


def test_eight_to_fourteen_day_deep_read_exception_remains_measurement_valid() -> None:
    published = datetime(2026, 7, 31, 0, 0, tzinfo=TZ)
    validity = _measurement_validity(published, CUTOFF, max_observation_days=14)

    assert validity == "valid"
    assert _age_bucket(12) == "8_14d"
    assert _track_window_status("deep_read", published, CUTOFF, validity) == "deep_read_exception_8_14d"


def test_historical_timely_label_older_than_72h_is_qa_failure_not_measurement_exclusion() -> None:
    published = datetime(2026, 8, 5, 0, 0, tzinfo=TZ)
    validity = _measurement_validity(published, CUTOFF, max_observation_days=14)

    assert validity == "valid"
    assert _track_window_status("timely", published, CUTOFF, validity) == "inconsistent_timely_gt72h"


def test_snapshot_filter_excludes_prepublication_capture() -> None:
    snapshots = [
        {"captured_at_bj": "2026-08-04 12:00:00", "snapshot_id": "too-early"},
        {"captured_at_bj": "2026-08-05 12:00:00", "snapshot_id": "eligible"},
    ]
    filtered = _item_snapshots(
        snapshots,
        observation_start=datetime(2026, 8, 5, 0, 0, tzinfo=TZ),
        cutoff=CUTOFF,
        tz=TZ,
    )

    assert [row["snapshot_id"] for row in filtered] == ["eligible"]


def test_preinstrumentation_item_is_partial_and_excluded_from_strict_denominator() -> None:
    observation_start = datetime(2026, 7, 30, 0, 0, tzinfo=TZ)
    snapshot_start = datetime(2026, 7, 31, 14, 40, 35, tzinfo=TZ)
    coverage = _observation_coverage_status(
        observation_start,
        snapshot_start,
        CUTOFF,
        "valid",
    )
    row = {
        "measurement_validity": "valid",
        "registry_status": "registered",
        "promotion_denominator_status": "effective_route_denominator",
        "observation_coverage_status": coverage,
    }

    assert coverage == "partial"
    assert _measurement_denominator_status(row) == "partial_observation"


def test_strict_summary_counts_only_full_effective_route_measurement_rows() -> None:
    items = [
        {
            "measurement_denominator_status": "strict_effective_route_denominator",
            "measurement_age_bucket": "0_3d",
            "match_status": "captured_eligible",
            "track_window_status": "consistent_timely",
        },
        {
            "measurement_denominator_status": "strict_effective_route_denominator",
            "measurement_age_bucket": "4_7d",
            "match_status": "not_discovered",
            "track_window_status": "consistent_deep_read",
        },
        {
            "measurement_denominator_status": "partial_observation",
            "measurement_age_bucket": "8_14d",
            "match_status": "captured_eligible",
            "track_window_status": "deep_read_exception_8_14d",
        },
        {
            "measurement_denominator_status": "source_coverage_gap",
            "measurement_age_bucket": "0_3d",
            "match_status": "not_discovered",
            "track_window_status": "inconsistent_timely_gt72h",
        },
    ]
    summary = _measurement_summary(
        items,
        datetime(2026, 7, 31, 14, 40, 35, tzinfo=TZ),
    )

    assert summary["strict_effective_route_denominator"] == 2
    assert summary["strict_effective_route_discovered"] == 1
    assert summary["strict_effective_route_discovery_recall"] == 0.5
    assert summary["strict_effective_route_editable"] == 1
    assert summary["age_0_3d_denominator"] == 1
    assert summary["age_0_3d_recall"] == 1.0
    assert summary["age_4_7d_denominator"] == 1
    assert summary["age_4_7d_recall"] == 0.0
    assert summary["age_8_14d_denominator"] == 0
    assert summary["partial_observation_items"] == 1
    assert summary["time_track_inconsistent_items"] == 1


def test_no_final_items_summary_is_non_retryable_skip_contract() -> None:
    summary = no_final_items_summary(datetime(2026, 8, 14).date())

    assert summary["audit_status"] == "no_final_items"
    assert summary["write_performed"] is False
    assert summary["audit_version"].startswith("final-recall-audit-v1.2")
