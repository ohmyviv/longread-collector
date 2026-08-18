from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.source_coverage_debt import compute_coverage_debt_candidates
from longread_collector.source_run_coverage import SOURCE_RUN_COVERAGE_VERSION

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 17, 22, 52, tzinfo=TZ)


def source(source_id: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": source_id,
        "priority_tier": "rotate",
        "enabled": True,
    }


def coverage(
    source_id: str,
    started: str,
    horizon: float,
    *,
    route_status: str = "native_covered",
    coverage_version: str = SOURCE_RUN_COVERAGE_VERSION,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "run_started_at_bj": started,
        "route_status": route_status,
        "observed_horizon_hours": horizon,
        "coverage_version": coverage_version,
    }


def test_ft_like_shallow_route_enters_debt_before_next_opportunity() -> None:
    rows = [
        coverage("ft", "2026-08-16 22:50:00", 18.8),
        coverage("ft", "2026-08-14 23:17:00", 21.5),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("ft")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=5.5,
        safety_margin_hours=2.0,
        min_samples=2,
        recent_samples=5,
    )

    assert [candidate.source_id for candidate in candidates] == ["ft"]
    candidate = candidates[0]
    assert candidate.current_age_hours == 24.033
    assert candidate.projected_age_hours == 29.533
    assert candidate.proven_horizon_hours == 18.8
    assert candidate.coverage_slack_hours == -10.733
    assert candidate.sample_count == 2


def test_source_with_safe_horizon_does_not_enter_debt() -> None:
    rows = [
        coverage("deep", "2026-08-17 10:00:00", 72.0),
        coverage("deep", "2026-08-16 10:00:00", 80.0),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("deep")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=6.0,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert candidates == []


def test_latest_degraded_route_is_route_debt_not_coverage_debt() -> None:
    rows = [
        coverage(
            "reuters-special",
            "2026-08-17 22:00:00",
            0,
            route_status="fallback_only",
        ),
        coverage("reuters-special", "2026-08-16 22:00:00", 36.0),
        coverage("reuters-special", "2026-08-15 22:00:00", 40.0),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("reuters-special")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=6.0,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert candidates == []


def test_insufficient_native_coverage_samples_fail_closed() -> None:
    rows = [coverage("ft", "2026-08-16 22:50:00", 18.8)]

    candidates = compute_coverage_debt_candidates(
        sources=[source("ft")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=5.5,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert candidates == []


def test_future_coverage_rows_are_ignored() -> None:
    rows = [
        coverage("ft", "2026-08-18 04:00:00", 30.0),
        coverage("ft", "2026-08-16 22:50:00", 18.8),
        coverage("ft", "2026-08-14 23:17:00", 21.5),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("ft")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=5.5,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert len(candidates) == 1
    assert candidates[0].last_successful_coverage_at_bj == "2026-08-16 22:50:00"


def test_older_coverage_contract_versions_are_ignored() -> None:
    rows = [
        coverage(
            "ft",
            "2026-08-16 22:50:00",
            48.0,
            coverage_version="run-source-coverage-legacy",
        ),
        coverage("ft", "2026-08-16 20:00:00", 18.8),
        coverage("ft", "2026-08-14 23:17:00", 21.5),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("ft")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=5.5,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert len(candidates) == 1
    assert candidates[0].proven_horizon_hours == 18.8
    assert candidates[0].last_successful_coverage_at_bj == "2026-08-16 20:00:00"


def test_only_old_contract_evidence_fails_closed() -> None:
    rows = [
        coverage(
            "ft",
            "2026-08-16 22:50:00",
            18.8,
            coverage_version="run-source-coverage-legacy",
        ),
        coverage(
            "ft",
            "2026-08-14 23:17:00",
            21.5,
            coverage_version="run-source-coverage-legacy",
        ),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("ft")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=5.5,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert candidates == []


def test_most_negative_slack_is_most_urgent() -> None:
    rows = [
        coverage("a", "2026-08-16 22:52:00", 18.0),
        coverage("a", "2026-08-15 22:52:00", 20.0),
        coverage("b", "2026-08-17 04:52:00", 18.0),
        coverage("b", "2026-08-16 04:52:00", 20.0),
    ]

    candidates = compute_coverage_debt_candidates(
        sources=[source("a"), source("b")],
        coverage_rows=rows,
        started=NOW,
        projection_hours=6.0,
        safety_margin_hours=2.0,
        min_samples=2,
    )

    assert [candidate.source_id for candidate in candidates] == ["a", "b"]
    assert candidates[0].coverage_slack_hours < candidates[1].coverage_slack_hours
