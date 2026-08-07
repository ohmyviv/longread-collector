"""Evaluation metrics focused on destructive Acquisition Gate errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..contracts import GateAction, GateDecision


@dataclass(frozen=True, slots=True)
class GateReplayMetrics:
    total_count: int
    expected_hard_reject_count: int
    hard_reject_count: int
    true_hard_reject_count: int
    false_hard_reject_count: int
    high_value_false_hard_reject_count: int
    hard_reject_precision: float


def evaluate_gate_replay(
    rows: Iterable[tuple[GateDecision, bool, bool]],
) -> GateReplayMetrics:
    """Measure early-gate precision.

    Each tuple is `(decision, expected_hard_reject, high_value)`. Fixed replay
    results are development evidence, not natural holdout release evidence.
    """

    values = tuple(rows)
    expected = sum(int(expected_hard) for _, expected_hard, _ in values)
    actual_rows = [row for row in values if row[0].action is GateAction.HARD_REJECT]
    true_hard = sum(int(expected_hard) for _, expected_hard, _ in actual_rows)
    false_hard = len(actual_rows) - true_hard
    high_value_false = sum(
        int(high_value and not expected_hard)
        for _, expected_hard, high_value in actual_rows
    )
    precision = true_hard / len(actual_rows) if actual_rows else 1.0
    return GateReplayMetrics(
        total_count=len(values),
        expected_hard_reject_count=expected,
        hard_reject_count=len(actual_rows),
        true_hard_reject_count=true_hard,
        false_hard_reject_count=false_hard,
        high_value_false_hard_reject_count=high_value_false,
        hard_reject_precision=precision,
    )


__all__ = ["GateReplayMetrics", "evaluate_gate_replay"]
