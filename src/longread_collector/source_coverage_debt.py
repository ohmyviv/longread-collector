from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from .final_recall_audit import _sheet_datetime

COVERAGE_DEBT_VERSION = "deadline-coverage-debt-v0.1"


@dataclass(frozen=True, slots=True)
class CoverageDebtCandidate:
    source_id: str
    source_name: str
    last_successful_coverage_at_bj: str
    current_age_hours: float
    projection_hours: float
    projected_age_hours: float
    proven_horizon_hours: float
    safety_margin_hours: float
    coverage_slack_hours: float
    sample_count: int
    latest_route_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "last_successful_coverage_at_bj": self.last_successful_coverage_at_bj,
            "current_age_hours": self.current_age_hours,
            "projection_hours": self.projection_hours,
            "projected_age_hours": self.projected_age_hours,
            "proven_horizon_hours": self.proven_horizon_hours,
            "safety_margin_hours": self.safety_margin_hours,
            "coverage_slack_hours": self.coverage_slack_hours,
            "sample_count": self.sample_count,
            "latest_route_status": self.latest_route_status,
            "version": COVERAGE_DEBT_VERSION,
        }


def _enabled(source: dict[str, Any]) -> bool:
    return (
        str(source.get("priority_tier", "")).strip() != "monitor"
        and source.get("enabled", True) is not False
        and str(source.get("enabled", "TRUE")).strip().upper()
        not in {"FALSE", "0", "NO", "N"}
    )


def _as_positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _coverage_started(row: dict[str, Any], tz: Any) -> datetime | None:
    return _sheet_datetime(row.get("run_started_at_bj"), tz)


def compute_coverage_debt_candidates(
    *,
    sources: Iterable[dict[str, Any]],
    coverage_rows: Iterable[dict[str, Any]],
    started: datetime,
    projection_hours: float,
    safety_margin_hours: float,
    min_samples: int = 2,
    recent_samples: int = 5,
) -> list[CoverageDebtCandidate]:
    """Return healthy native sources whose proven horizon is about to expire.

    ``observed_horizon_hours`` is only a lower-bound observation. The policy
    therefore uses the minimum recent positive lower bound as the conservative
    proven horizon, never a configured lookback claim. A source is eligible
    only when its latest attempt is itself ``native_covered``; degraded routes
    become Route Debt and cannot consume a Coverage Debt pre-emption slot.
    """

    projection = max(0.0, float(projection_hours))
    margin = max(0.0, float(safety_margin_hours))
    required_samples = max(1, int(min_samples))
    sample_limit = max(required_samples, int(recent_samples))
    tz = started.tzinfo

    rows_by_source: dict[str, list[dict[str, Any]]] = {}
    for row in coverage_rows:
        source_id = str(row.get("source_id", "") or "").strip()
        row_started = _coverage_started(row, tz)
        if not source_id or row_started is None or row_started > started:
            continue
        rows_by_source.setdefault(source_id, []).append(row)

    result: list[CoverageDebtCandidate] = []
    for source in sources:
        if not _enabled(source):
            continue
        source_id = str(source.get("source_id", "") or "").strip()
        if not source_id:
            continue
        rows = rows_by_source.get(source_id, [])
        if not rows:
            continue
        rows.sort(
            key=lambda row: _coverage_started(row, tz)
            or datetime.min.replace(tzinfo=tz),
            reverse=True,
        )

        latest = rows[0]
        latest_route_status = str(latest.get("route_status", "") or "")
        if latest_route_status != "native_covered":
            continue

        successful = [
            row for row in rows if str(row.get("route_status", "")) == "native_covered"
        ]
        samples: list[float] = []
        for row in successful[:sample_limit]:
            horizon = _as_positive_float(row.get("observed_horizon_hours"))
            if horizon is not None:
                samples.append(horizon)
        if len(samples) < required_samples:
            continue

        last_success = _coverage_started(successful[0], tz)
        if last_success is None:
            continue
        current_age = max(0.0, (started - last_success).total_seconds() / 3600)
        projected_age = current_age + projection
        proven_horizon = min(samples)
        slack = proven_horizon - projected_age
        if slack > margin:
            continue

        result.append(
            CoverageDebtCandidate(
                source_id=source_id,
                source_name=str(source.get("source_name", "") or source_id),
                last_successful_coverage_at_bj=last_success.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                current_age_hours=round(current_age, 3),
                projection_hours=round(projection, 3),
                projected_age_hours=round(projected_age, 3),
                proven_horizon_hours=round(proven_horizon, 3),
                safety_margin_hours=round(margin, 3),
                coverage_slack_hours=round(slack, 3),
                sample_count=len(samples),
                latest_route_status=latest_route_status,
            )
        )

    result.sort(key=lambda item: (item.coverage_slack_hours, item.source_id))
    return result
