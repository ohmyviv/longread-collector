from __future__ import annotations

from dataclasses import dataclass


SHEETS_READS_PER_USER_PER_MINUTE = 60
CURRENT_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)


@dataclass(frozen=True, slots=True)
class SheetsReadBudgetEstimate:
    doctor_reads_lower_bound: int
    collect_reads_lower_bound: int
    quota_per_minute: int = SHEETS_READS_PER_USER_PER_MINUTE

    @property
    def total_reads_lower_bound(self) -> int:
        return self.doctor_reads_lower_bound + self.collect_reads_lower_bound

    @property
    def headroom(self) -> int:
        return self.quota_per_minute - self.total_reads_lower_bound

    @property
    def structurally_over_quota(self) -> bool:
        return self.total_reads_lower_bound > self.quota_per_minute


FROZEN_20260830_LOWER_BOUND = SheetsReadBudgetEstimate(
    doctor_reads_lower_bound=15,
    collect_reads_lower_bound=50,
)


def retry_horizon_seconds(delays: tuple[float, ...] = CURRENT_RETRY_DELAYS_SECONDS) -> float:
    return float(sum(delays))


def quota_window_retry_is_credible(
    *,
    delays: tuple[float, ...] = CURRENT_RETRY_DELAYS_SECONDS,
    quota_window_seconds: float = 60.0,
) -> bool:
    """Return whether the retry horizon can span one exhausted quota window.

    This is an offline diagnostic helper, not runtime retry policy. A credible
    horizon does not imply that sleeping through the quota window is the right
    primary remediation; reducing read amplification remains preferred.
    """

    return retry_horizon_seconds(delays) >= quota_window_seconds


__all__ = [
    "CURRENT_RETRY_DELAYS_SECONDS",
    "FROZEN_20260830_LOWER_BOUND",
    "SHEETS_READS_PER_USER_PER_MINUTE",
    "SheetsReadBudgetEstimate",
    "quota_window_retry_is_credible",
    "retry_horizon_seconds",
]
