from longread_collector.sheets_read_budget_v2 import (
    CURRENT_RETRY_DELAYS_SECONDS,
    FROZEN_20260830_LOWER_BOUND,
    SHEETS_READS_PER_USER_PER_MINUTE,
    quota_window_retry_is_credible,
    retry_horizon_seconds,
)


def test_frozen_20260830_lower_bound_exceeds_per_user_quota() -> None:
    estimate = FROZEN_20260830_LOWER_BOUND
    assert estimate.doctor_reads_lower_bound == 15
    assert estimate.collect_reads_lower_bound == 50
    assert estimate.total_reads_lower_bound == 65
    assert estimate.quota_per_minute == SHEETS_READS_PER_USER_PER_MINUTE == 60
    assert estimate.headroom == -5
    assert estimate.structurally_over_quota is True


def test_current_retry_horizon_cannot_span_one_minute_quota_window() -> None:
    assert CURRENT_RETRY_DELAYS_SECONDS == (1.0, 2.0, 4.0)
    assert retry_horizon_seconds() == 7.0
    assert quota_window_retry_is_credible() is False


def test_quota_window_helper_is_diagnostic_not_policy_specific() -> None:
    assert quota_window_retry_is_credible(delays=(15.0, 15.0, 15.0, 15.0)) is True
    assert quota_window_retry_is_credible(delays=(10.0, 10.0), quota_window_seconds=30.0) is False
