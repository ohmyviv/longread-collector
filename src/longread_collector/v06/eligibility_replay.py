"""Offline replay helpers for Standard Longread Eligibility.

The replay layer is intentionally data-source agnostic. It does not read
Sheets, perform network I/O, or infer human labels. Callers provide durable
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
EXPECTED_DISPOSITION_BY_SUBTYPE = {
    "video": StandardLongreadDisposition.INELIGIBLE_STANDARD,
    "daily_briefing": StandardLongreadDisposition.INELIGIBLE_STANDARD,
    "academic_paper": StandardLongreadDisposition.ROUTE_SPECIAL,
}
RESOLVED_NONSTANDARD_DISPOSITIONS = frozenset(
    {
        StandardLongreadDisposition.ROUTE_SPECIAL,
        StandardLongreadDisposition.INELIGIBLE_STANDARD,
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

    @property
    def expected_disposition(self) -> StandardLongreadDisposition | None:
        return EXPECTED_DISPOSITION_BY_SUBTYPE.get(self.failure_subtype)

    @property
    def is_resolved_nonstandard(self) -> bool:
        return self.disposition in RESOLVED_NONSTANDARD_DISPOSITIONS

    @property
    def is_correctly_dispositioned_wrong_medium_asset(self) -> bool:
        if not self.is_wrong_medium_asset:
            return False
        expected = self.expected_disposition
        if expected is None:
            # The generic family has no unique route expectation, but UNKNOWN
            # must never count as a successful capture.
            return self.is_resolved_nonstandard
        return self.disposition is expected


@dataclass(frozen=True, slots=True)
class EligibilityReplaySummary:
    total: int
    hit_count: int
    hit_lost_from_standard: int
    wrong_medium_asset_count: int
    wrong_medium_asset_kept_standard: int
    wrong_medium_asset_resolved_nonstandard: int
    wrong_medium_asset_unknown: int
    wrong_medium_asset_correctly_dispositioned: int
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
        """High-confidence family resolved away from Standard Longread.

        UNKNOWN is intentionally not counted as capture: abstaining from a
        product decision is different from correctly resolving a non-standard
        object.
        """

        if not self.wrong_medium_asset_count:
            return 0.0
        return self.wrong_medium_asset_resolved_nonstandard / self.wrong_medium_asset_count

    @property
    def wrong_medium_asset_correct_disposition_rate(self) -> float:
        """Rate assigned to the expected route/class for known subtypes."""

        if not self.wrong_medium_asset_count:
            return 0.0
        return (
            self.wrong_medium_asset_correctly_dispositioned
            / self.wrong_medium_asset_count
        )


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
    wrong_rows = tuple(row for row in materialized if row.is_wrong_medium_asset)
    wrong_medium_asset_kept = sum(
        row.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD
        for row in wrong_rows
    )
    wrong_medium_asset_resolved = sum(row.is_resolved_nonstandard for row in wrong_rows)
    wrong_medium_asset_unknown = sum(
        row.disposition is StandardLongreadDisposition.UNKNOWN for row in wrong_rows
    )
    wrong_medium_asset_correct = sum(
        row.is_correctly_dispositioned_wrong_medium_asset for row in wrong_rows
    )
    return EligibilityReplaySummary(
        total=len(materialized),
        hit_count=hit_count,
        hit_lost_from_standard=hit_lost,
        wrong_medium_asset_count=len(wrong_rows),
        wrong_medium_asset_kept_standard=wrong_medium_asset_kept,
        wrong_medium_asset_resolved_nonstandard=wrong_medium_asset_resolved,
        wrong_medium_asset_unknown=wrong_medium_asset_unknown,
        wrong_medium_asset_correctly_dispositioned=wrong_medium_asset_correct,
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
