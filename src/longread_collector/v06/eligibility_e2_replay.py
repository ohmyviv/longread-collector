"""Offline replay metrics for E2 length hypotheses.

The helpers quantify trade-offs for hypothetical thresholds.  They never apply a
threshold to production eligibility and deliberately keep missing historical
lengths visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from longread_collector.v06.eligibility_replay import HIT_LABELS


@dataclass(frozen=True, slots=True)
class LengthReplayRow:
    review_id: str
    review_label: str
    human_short: bool
    body_chars_read: int | None

    @property
    def is_hit(self) -> bool:
        return self.review_label in HIT_LABELS


@dataclass(frozen=True, slots=True)
class LengthThresholdReplay:
    threshold_chars: int
    total_rows: int
    observed_length_rows: int
    unknown_length_rows: int
    human_short_count: int
    human_short_with_length: int
    human_short_captured: int
    hit_count: int
    hit_with_length: int
    hit_lost: int

    @property
    def human_short_capture_rate(self) -> float:
        if not self.human_short_count:
            return 0.0
        return self.human_short_captured / self.human_short_count

    @property
    def known_hit_loss_rate(self) -> float:
        if not self.hit_count:
            return 0.0
        return self.hit_lost / self.hit_count


def replay_length_threshold(
    rows: Iterable[LengthReplayRow],
    threshold_chars: int,
) -> LengthThresholdReplay:
    """Evaluate a hypothetical strict ``chars < threshold`` rule."""

    if threshold_chars < 0:
        raise ValueError("threshold_chars must be non-negative")
    materialized = tuple(rows)
    observed = tuple(row for row in materialized if row.body_chars_read is not None)
    short_rows = tuple(row for row in materialized if row.human_short)
    hit_rows = tuple(row for row in materialized if row.is_hit)
    short_with_length = tuple(row for row in short_rows if row.body_chars_read is not None)
    hit_with_length = tuple(row for row in hit_rows if row.body_chars_read is not None)

    return LengthThresholdReplay(
        threshold_chars=threshold_chars,
        total_rows=len(materialized),
        observed_length_rows=len(observed),
        unknown_length_rows=len(materialized) - len(observed),
        human_short_count=len(short_rows),
        human_short_with_length=len(short_with_length),
        human_short_captured=sum(
            row.body_chars_read is not None and row.body_chars_read < threshold_chars
            for row in short_rows
        ),
        hit_count=len(hit_rows),
        hit_with_length=len(hit_with_length),
        hit_lost=sum(
            row.body_chars_read is not None and row.body_chars_read < threshold_chars
            for row in hit_rows
        ),
    )


def replay_length_thresholds(
    rows: Iterable[LengthReplayRow],
    thresholds: Iterable[int],
) -> tuple[LengthThresholdReplay, ...]:
    materialized = tuple(rows)
    return tuple(
        replay_length_threshold(materialized, threshold)
        for threshold in thresholds
    )


__all__ = [
    "LengthReplayRow",
    "LengthThresholdReplay",
    "replay_length_threshold",
    "replay_length_thresholds",
]
