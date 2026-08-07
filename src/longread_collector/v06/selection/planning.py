"""Shadow-only 24+4+4 acquisition planning primitives for v0.6 PR-4.

This module does not perform discovery or acquisition. It consumes forecast
objects supplied by a future integration layer and returns an immutable plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PLANNING_VERSION = "shadow-planner-v0.6-pr4"
LEGACY_PLANNING_VERSION = "legacy-static-24-plus-8-comparator-v0.6-pr4"


@dataclass(frozen=True, slots=True)
class AcquisitionForecast:
    item_id: str
    expected_editorial_utility: float
    confidence: float
    expected_cost: float = 0.0
    source_group: str = ""
    stratum: str = ""
    legacy_priority: float = 0.0
    deterministic_reject: bool = False


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    strategy_version: str
    exploit_ids: tuple[str, ...]
    replacement_ids: tuple[str, ...]
    exploration_ids: tuple[str, ...]

    @property
    def ordered_ids(self) -> tuple[str, ...]:
        return self.exploit_ids + self.replacement_ids + self.exploration_ids

    @property
    def attempt_count(self) -> int:
        return len(self.ordered_ids)


class ShadowAcquisitionPlanner:
    """Create a bounded exploit/replacement/exploration plan from forecasts."""

    stage_version = PLANNING_VERSION

    def plan(
        self,
        forecasts: Iterable[AcquisitionForecast],
        *,
        max_attempts: int = 32,
        exploit_slots: int = 24,
        replacement_slots: int = 4,
        exploration_slots: int = 4,
    ) -> AcquisitionPlan:
        _validate_slot_budget(
            max_attempts,
            exploit_slots,
            replacement_slots,
            exploration_slots,
        )
        pool = [
            forecast
            for forecast in forecasts
            if not forecast.deterministic_reject
        ]
        _ensure_unique_ids(pool)

        exploit = _greedy_exploit(pool, exploit_slots)
        used = {item.item_id for item in exploit}
        remaining = [item for item in pool if item.item_id not in used]

        replacements = sorted(
            remaining,
            key=lambda item: (-_forecast_score(item), item.item_id),
        )[:replacement_slots]
        used.update(item.item_id for item in replacements)
        remaining = [item for item in remaining if item.item_id not in used]

        exploration = _stratified_exploration(
            remaining,
            exploration_slots,
            already_selected=exploit + replacements,
        )

        plan = AcquisitionPlan(
            strategy_version=PLANNING_VERSION,
            exploit_ids=tuple(item.item_id for item in exploit),
            replacement_ids=tuple(item.item_id for item in replacements),
            exploration_ids=tuple(item.item_id for item in exploration),
        )
        if plan.attempt_count > max_attempts:
            raise AssertionError("planner exceeded max_attempts")
        return plan


def legacy_static_plan(
    forecasts: Iterable[AcquisitionForecast],
    *,
    max_attempts: int = 32,
    first_stage_slots: int = 24,
) -> AcquisitionPlan:
    """Deterministic 24+8 comparator using only legacy priority."""
    if max_attempts < 0 or first_stage_slots < 0 or first_stage_slots > max_attempts:
        raise ValueError("invalid legacy slot budget")
    pool = [
        forecast
        for forecast in forecasts
        if not forecast.deterministic_reject
    ]
    _ensure_unique_ids(pool)
    ranked = sorted(
        pool,
        key=lambda item: (-float(item.legacy_priority), item.item_id),
    )[:max_attempts]
    first = ranked[:first_stage_slots]
    reserve = ranked[first_stage_slots:max_attempts]
    return AcquisitionPlan(
        strategy_version=LEGACY_PLANNING_VERSION,
        exploit_ids=tuple(item.item_id for item in first),
        replacement_ids=tuple(item.item_id for item in reserve),
        exploration_ids=(),
    )


def _greedy_exploit(
    pool: list[AcquisitionForecast],
    limit: int,
) -> list[AcquisitionForecast]:
    selected: list[AcquisitionForecast] = []
    remaining = list(pool)
    source_counts: dict[str, int] = {}
    while remaining and len(selected) < limit:
        ranked = []
        for item in remaining:
            source = item.source_group.strip().lower() or item.item_id
            source_penalty = min(0.16, 0.035 * source_counts.get(source, 0))
            ranked.append((
                _forecast_score(item) - source_penalty,
                item.item_id,
                item,
            ))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        best = ranked[0][2]
        selected.append(best)
        source = best.source_group.strip().lower() or best.item_id
        source_counts[source] = source_counts.get(source, 0) + 1
        remaining = [item for item in remaining if item.item_id != best.item_id]
    return selected


def _stratified_exploration(
    pool: list[AcquisitionForecast],
    limit: int,
    *,
    already_selected: list[AcquisitionForecast],
) -> list[AcquisitionForecast]:
    selected: list[AcquisitionForecast] = []
    remaining = list(pool)
    source_counts: dict[str, int] = {}
    stratum_counts: dict[str, int] = {}

    for item in already_selected:
        source = item.source_group.strip().lower()
        stratum = item.stratum.strip().lower()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        if stratum:
            stratum_counts[stratum] = stratum_counts.get(stratum, 0) + 1

    while remaining and len(selected) < limit:
        ranked = []
        for item in remaining:
            source = item.source_group.strip().lower()
            stratum = item.stratum.strip().lower()
            source_novelty = 1.0 / (1.0 + source_counts.get(source, 0)) if source else 0.5
            stratum_novelty = 1.0 / (1.0 + stratum_counts.get(stratum, 0)) if stratum else 0.5
            uncertainty = 1.0 - _clamp(item.confidence)
            score = (
                0.40 * uncertainty
                + 0.25 * _clamp(item.expected_editorial_utility)
                + 0.20 * stratum_novelty
                + 0.12 * source_novelty
                - 0.05 * max(0.0, float(item.expected_cost))
            )
            ranked.append((score, item.item_id, item))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        best = ranked[0][2]
        selected.append(best)
        source = best.source_group.strip().lower()
        stratum = best.stratum.strip().lower()
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        if stratum:
            stratum_counts[stratum] = stratum_counts.get(stratum, 0) + 1
        remaining = [item for item in remaining if item.item_id != best.item_id]
    return selected


def _forecast_score(item: AcquisitionForecast) -> float:
    utility = _clamp(item.expected_editorial_utility)
    confidence = _clamp(item.confidence)
    cost = max(0.0, float(item.expected_cost))
    return utility * (0.70 + 0.30 * confidence) - 0.07 * cost


def _validate_slot_budget(
    max_attempts: int,
    exploit_slots: int,
    replacement_slots: int,
    exploration_slots: int,
) -> None:
    values = (max_attempts, exploit_slots, replacement_slots, exploration_slots)
    if any(value < 0 for value in values):
        raise ValueError("slot budgets must be >= 0")
    if exploit_slots + replacement_slots + exploration_slots > max_attempts:
        raise ValueError("24+4+4 slot budget exceeds max_attempts")


def _ensure_unique_ids(pool: list[AcquisitionForecast]) -> None:
    ids = [item.item_id for item in pool]
    if len(ids) != len(set(ids)):
        raise ValueError("forecast item_id values must be unique")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "AcquisitionForecast",
    "AcquisitionPlan",
    "LEGACY_PLANNING_VERSION",
    "PLANNING_VERSION",
    "ShadowAcquisitionPlanner",
    "legacy_static_plan",
]