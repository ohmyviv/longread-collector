"""Offline replay helpers for Standard Longread Eligibility.

The replay layer is intentionally data-source agnostic.  It does not read
Sheets, perform network I/O, or infer human labels.  Callers provide durable
human review rows plus candidate eligibility dispositions and receive compact
acceptance metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from longread_collector.v06.eligibility import StandardLongreadDisposition

HIT_LABELS = frozenset({"强烈值得", "值得"})
WRONG_MEDIUM_ASSET_SUBTYPES = frozenset(
    {
        "video",
        "daily_briefing",
        "academic_paper",
        "wrong_medium_or_asset",
    }
)


@dataclass(frozen=True, slots=True)
class EligibilityReplayRow:
    review_id: str
    review_label: str
    attribution_bucket: str
    failure_subtype: str
    disposition: StandardLongreadDisposition

    @property
    def is_hit(self) -> bool:
        return self.review_label in HIT_LABELS

    @property
    def is_wrong_medium_asset(self) -> bool:
        return self.failure_subtype in WRONG_MEDIUM_ASSET_SUBTYPES


@dataclass(frozen=True, slots=True)
class EligibilityReplaySummary:
    total: int
    hit_count: int
    hit_lost_from_standard: int
    wrong_medium_asset_count: int
    wrong_medium_asset_kept_standard: int
    wrong_medium_asset_removed_from_standard: int
    unknown_count: int
    route_special_count: int
    ineligible_standard_count: int

    @property
    def known_hit_loss_rate(self) -> float:
        if not self.hit_count:
            return 0.0
        return self.hit_lost_from_standard / self.hit_count

    @property
    def wrong_medium_asset_capture_rate(self) -> float:
        if not self.wrong_medium_asset_count:
            return 0.0
        return self.wrong_medium_asset_removed_from_standard / self.wrong_medium_asset_count


def summarize_eligibility_replay(
    rows: Iterable[EligibilityReplayRow],
) -> EligibilityReplaySummary:
    materialized = tuple(rows)
    hit_count = sum(row.is_hit for row in materialized)
    hit_lost = sum(
        row.is_hit
        and row.disposition is not StandardLongreadDisposition.ELIGIBLE_STANDARD
        for row in materialized
    )
    wrong_medium_asset_count = sum(row.is_wrong_medium_asset for row in materialized)
    wrong_medium_asset_kept = sum(
        row.is_wrong_medium_asset
        and row.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD
        for row in materialized
    )
    wrong_medium_asset_removed = sum(
        row.is_wrong_medium_asset
        and row.disposition is not StandardLongreadDisposition.ELIGIBLE_STANDARD
        for row in materialized
    )
    return EligibilityReplaySummary(
        total=len(materialized),
        hit_count=hit_count,
        hit_lost_from_standard=hit_lost,
        wrong_medium_asset_count=wrong_medium_asset_count,
        wrong_medium_asset_kept_standard=wrong_medium_asset_kept,
        wrong_medium_asset_removed_from_standard=wrong_medium_asset_removed,
        unknown_count=sum(
            row.disposition is StandardLongreadDisposition.UNKNOWN
            for row in materialized
        ),
        route_special_count=sum(
            row.disposition is StandardLongreadDisposition.ROUTE_SPECIAL
            for row in materialized
        ),
        ineligible_standard_count=sum(
            row.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
            for row in materialized
        ),
    )
