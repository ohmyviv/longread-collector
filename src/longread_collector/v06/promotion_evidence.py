"""Offline promotion-evidence daily and cumulative aggregation.

This module is intentionally *not* a promotion decision engine.  It aggregates
already-audited evidence inside explicit evaluation cohorts.  It has no Sheets,
network, workflow, config-write, mode-switch, or auto-promotion dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PROMOTION_EVIDENCE_VERSION = "promotion-evidence-v0.6-v1"


@dataclass(frozen=True, slots=True)
class CountMetric:
    numerator: int = 0
    denominator: int = 0

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("metric counts must be non-negative")
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")

    @property
    def rate(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def __add__(self, other: "CountMetric") -> "CountMetric":
        return CountMetric(
            numerator=self.numerator + other.numerator,
            denominator=self.denominator + other.denominator,
        )


@dataclass(frozen=True, slots=True)
class PromotionEvidenceCohort:
    """Version/config identity within which evidence may be pooled.

    Callers must change ``evaluation_cohort_id`` whenever a semantic change can
    alter the meaning of a measured numerator/denominator.  Docs-only changes
    need not create a new cohort.
    """

    evaluation_cohort_id: str
    collector_version: str
    source_policy_version: str
    snapshot_version: str
    canonical_version: str
    eligibility_version: str
    editorial_version: str
    selection_version: str
    final_recall_version: str
    overlap_framework_version: str

    def __post_init__(self) -> None:
        if not self.evaluation_cohort_id.strip():
            raise ValueError("evaluation_cohort_id is required")


@dataclass(frozen=True, slots=True)
class DailyPromotionEvidence:
    """One report-date evidence record, containing facts rather than decisions."""

    report_date: str
    cohort: PromotionEvidenceCohort

    # Gate A / transport facts.
    natural_runs: CountMetric = CountMetric()
    snapshot_rows: CountMetric = CountMetric()
    capture_gap_count: int = 0
    duplicate_shadow_network_requests: int = 0
    incremental_shadow_firecrawl_requests: int = 0
    body_fingerprint_mismatches: int = 0
    semantic_p0_count: int = 0
    systemic_p1_count: int = 0

    # Gate B / strict, promotion-grade numerators and denominators only.
    strict_final_recall: CountMetric = CountMetric()
    strict_final_editable_recall: CountMetric = CountMetric()
    strict_m2_overlap: CountMetric = CountMetric()
    strict_m2_overlap_zh: CountMetric = CountMetric()
    strict_m2_overlap_en: CountMetric = CountMetric()
    partial_observation_items: int = 0

    # Task 2 attribution evidence.  These count strict Recall misses only.
    strict_miss_attribution_confirmed: CountMetric = CountMetric()
    strict_miss_attribution_strongly_supported: CountMetric = CountMetric()
    unresolved_strict_miss_count: int = 0

    # Gate C / bounded human review of plausible Collector-exclusive items.
    collector_exclusive_human_useful: CountMetric = CountMetric()
    overlapping_reference_human_useful: CountMetric = CountMetric()

    # Gate D / paired execution evidence.
    scheduled_manual_pairs_complete: CountMetric = CountMetric()

    # Gate E/F/G states remain explicit evidence, not synthesized decisions.
    eligibility_evidence_status: str = "unknown"
    version_reconciliation_status: str = "unknown"
    manual_approval_status: str = "not_requested"

    evidence_complete: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        integer_fields = (
            "capture_gap_count",
            "duplicate_shadow_network_requests",
            "incremental_shadow_firecrawl_requests",
            "body_fingerprint_mismatches",
            "semantic_p0_count",
            "systemic_p1_count",
            "partial_observation_items",
            "unresolved_strict_miss_count",
        )
        for field_name in integer_fields:
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        for metric_name in (
            "strict_miss_attribution_confirmed",
            "strict_miss_attribution_strongly_supported",
        ):
            metric = getattr(self, metric_name)
            if metric.denominator != self.strict_final_recall.denominator - self.strict_final_recall.numerator:
                raise ValueError(
                    f"{metric_name} denominator must equal strict Recall miss count"
                )


@dataclass(frozen=True, slots=True)
class CumulativePromotionEvidence:
    evidence_version: str
    cohort: PromotionEvidenceCohort
    report_dates: tuple[str, ...]
    evidence_days: int
    complete_evidence_days: int

    natural_runs: CountMetric
    snapshot_rows: CountMetric
    capture_gap_count: int
    duplicate_shadow_network_requests: int
    incremental_shadow_firecrawl_requests: int
    body_fingerprint_mismatches: int
    semantic_p0_count: int
    systemic_p1_count: int

    strict_final_recall: CountMetric
    strict_final_editable_recall: CountMetric
    strict_m2_overlap: CountMetric
    strict_m2_overlap_zh: CountMetric
    strict_m2_overlap_en: CountMetric
    partial_observation_items: int

    strict_miss_attribution_confirmed: CountMetric
    strict_miss_attribution_strongly_supported: CountMetric
    unresolved_strict_miss_count: int

    collector_exclusive_human_useful: CountMetric
    overlapping_reference_human_useful: CountMetric
    scheduled_manual_pairs_complete: CountMetric

    eligibility_evidence_statuses: tuple[str, ...]
    version_reconciliation_statuses: tuple[str, ...]
    manual_approval_statuses: tuple[str, ...]

    @property
    def all_evidence_days_complete(self) -> bool:
        return self.evidence_days > 0 and self.complete_evidence_days == self.evidence_days


def _sum_metrics(days: tuple[DailyPromotionEvidence, ...], field_name: str) -> CountMetric:
    total = CountMetric()
    for day in days:
        total = total + getattr(day, field_name)
    return total


def _unique_statuses(days: tuple[DailyPromotionEvidence, ...], field_name: str) -> tuple[str, ...]:
    return tuple(sorted({str(getattr(day, field_name)) for day in days}))


def aggregate_promotion_evidence(
    days: Iterable[DailyPromotionEvidence],
) -> tuple[CumulativePromotionEvidence, ...]:
    """Pool counts only inside identical explicit evaluation cohorts.

    Daily percentages are never averaged.  Numerators and denominators are
    summed first, and callers may read the resulting ``CountMetric.rate``.
    Different cohorts are returned as separate rollups rather than silently
    mixed.
    """

    grouped: dict[PromotionEvidenceCohort, list[DailyPromotionEvidence]] = {}
    for day in days:
        grouped.setdefault(day.cohort, []).append(day)

    rollups: list[CumulativePromotionEvidence] = []
    for cohort, cohort_days_list in grouped.items():
        cohort_days = tuple(sorted(cohort_days_list, key=lambda item: item.report_date))
        rollups.append(
            CumulativePromotionEvidence(
                evidence_version=PROMOTION_EVIDENCE_VERSION,
                cohort=cohort,
                report_dates=tuple(day.report_date for day in cohort_days),
                evidence_days=len(cohort_days),
                complete_evidence_days=sum(day.evidence_complete for day in cohort_days),
                natural_runs=_sum_metrics(cohort_days, "natural_runs"),
                snapshot_rows=_sum_metrics(cohort_days, "snapshot_rows"),
                capture_gap_count=sum(day.capture_gap_count for day in cohort_days),
                duplicate_shadow_network_requests=sum(
                    day.duplicate_shadow_network_requests for day in cohort_days
                ),
                incremental_shadow_firecrawl_requests=sum(
                    day.incremental_shadow_firecrawl_requests for day in cohort_days
                ),
                body_fingerprint_mismatches=sum(
                    day.body_fingerprint_mismatches for day in cohort_days
                ),
                semantic_p0_count=sum(day.semantic_p0_count for day in cohort_days),
                systemic_p1_count=sum(day.systemic_p1_count for day in cohort_days),
                strict_final_recall=_sum_metrics(cohort_days, "strict_final_recall"),
                strict_final_editable_recall=_sum_metrics(
                    cohort_days, "strict_final_editable_recall"
                ),
                strict_m2_overlap=_sum_metrics(cohort_days, "strict_m2_overlap"),
                strict_m2_overlap_zh=_sum_metrics(cohort_days, "strict_m2_overlap_zh"),
                strict_m2_overlap_en=_sum_metrics(cohort_days, "strict_m2_overlap_en"),
                partial_observation_items=sum(
                    day.partial_observation_items for day in cohort_days
                ),
                strict_miss_attribution_confirmed=_sum_metrics(
                    cohort_days, "strict_miss_attribution_confirmed"
                ),
                strict_miss_attribution_strongly_supported=_sum_metrics(
                    cohort_days, "strict_miss_attribution_strongly_supported"
                ),
                unresolved_strict_miss_count=sum(
                    day.unresolved_strict_miss_count for day in cohort_days
                ),
                collector_exclusive_human_useful=_sum_metrics(
                    cohort_days, "collector_exclusive_human_useful"
                ),
                overlapping_reference_human_useful=_sum_metrics(
                    cohort_days, "overlapping_reference_human_useful"
                ),
                scheduled_manual_pairs_complete=_sum_metrics(
                    cohort_days, "scheduled_manual_pairs_complete"
                ),
                eligibility_evidence_statuses=_unique_statuses(
                    cohort_days, "eligibility_evidence_status"
                ),
                version_reconciliation_statuses=_unique_statuses(
                    cohort_days, "version_reconciliation_status"
                ),
                manual_approval_statuses=_unique_statuses(
                    cohort_days, "manual_approval_status"
                ),
            )
        )

    return tuple(
        sorted(rollups, key=lambda item: item.cohort.evaluation_cohort_id)
    )


__all__ = [
    "PROMOTION_EVIDENCE_VERSION",
    "CountMetric",
    "CumulativePromotionEvidence",
    "DailyPromotionEvidence",
    "PromotionEvidenceCohort",
    "aggregate_promotion_evidence",
]
