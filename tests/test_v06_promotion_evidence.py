import pytest

from longread_collector.v06.promotion_evidence import (
    CountMetric,
    DailyPromotionEvidence,
    PromotionEvidenceCohort,
    aggregate_promotion_evidence,
)


def _cohort(cohort_id="pr739-baseline"):
    return PromotionEvidenceCohort(
        evaluation_cohort_id=cohort_id,
        collector_version="collector-v0.6-pr7.3.9",
        source_policy_version="deadline-freshness-reserve-v0.6-phase0b.1",
        snapshot_version="snapshot-persistence-v0.6-pr7.3.8",
        canonical_version="canonical-source-v0.6-pr7.3.9",
        eligibility_version="standard-longread-eligibility-v0.6-e1-offline",
        editorial_version="editorial-judge-v0.6-pr7.2",
        selection_version="selection-control-shadow-v1",
        final_recall_version="final-recall-audit-v1.2-item-window",
        overlap_framework_version="collector-manual-high-overlap-v1",
    )


def _day(
    report_date,
    *,
    cohort=None,
    strict_hit=0,
    strict_total=0,
    confirmed=0,
    strongly_supported=0,
    unresolved=0,
    m2_hit=0,
    m2_total=0,
    complete=True,
):
    miss_count = strict_total - strict_hit
    return DailyPromotionEvidence(
        report_date=report_date,
        cohort=cohort or _cohort(),
        natural_runs=CountMetric(4, 4),
        snapshot_rows=CountMetric(200, 200),
        strict_final_recall=CountMetric(strict_hit, strict_total),
        strict_final_editable_recall=CountMetric(0, strict_total),
        strict_m2_overlap=CountMetric(m2_hit, m2_total),
        strict_m2_overlap_en=CountMetric(m2_hit, m2_total),
        strict_miss_attribution_confirmed=CountMetric(confirmed, miss_count),
        strict_miss_attribution_strongly_supported=CountMetric(
            strongly_supported, miss_count
        ),
        unresolved_strict_miss_count=unresolved,
        eligibility_evidence_status="offline_e1_ready_e2_measurement_only",
        version_reconciliation_status="stale_legacy_state",
        manual_approval_status="not_requested",
        evidence_complete=complete,
    )


def test_count_metric_rate_and_validation():
    assert CountMetric(1, 3).rate == pytest.approx(1 / 3)
    assert CountMetric().rate is None
    with pytest.raises(ValueError):
        CountMetric(2, 1)
    with pytest.raises(ValueError):
        CountMetric(-1, 1)


def test_rollup_sums_numerators_denominators_instead_of_averaging_daily_rates():
    # Daily rates are 1/3 and 9/10.  The correct cumulative result is 10/13,
    # not the unweighted mean of 33.3% and 90%.
    days = (
        _day(
            "2026-08-15",
            strict_hit=1,
            strict_total=3,
            confirmed=0,
            strongly_supported=2,
            unresolved=1,
            m2_hit=1,
            m2_total=6,
        ),
        _day(
            "2026-08-16",
            strict_hit=9,
            strict_total=10,
            confirmed=1,
            strongly_supported=0,
            unresolved=0,
            m2_hit=7,
            m2_total=8,
        ),
    )
    (rollup,) = aggregate_promotion_evidence(days)
    assert rollup.report_dates == ("2026-08-15", "2026-08-16")
    assert rollup.strict_final_recall == CountMetric(10, 13)
    assert rollup.strict_final_recall.rate == pytest.approx(10 / 13)
    assert rollup.strict_m2_overlap == CountMetric(8, 14)
    assert rollup.strict_m2_overlap.rate == pytest.approx(8 / 14)
    assert rollup.strict_miss_attribution_confirmed == CountMetric(1, 3)
    assert rollup.strict_miss_attribution_strongly_supported == CountMetric(2, 3)
    assert rollup.unresolved_strict_miss_count == 1


def test_different_semantic_cohorts_are_never_silently_pooled():
    days = (
        _day("2026-08-15", cohort=_cohort("cohort-a"), strict_hit=1, strict_total=3),
        _day("2026-08-16", cohort=_cohort("cohort-b"), strict_hit=2, strict_total=3),
    )
    rollups = aggregate_promotion_evidence(days)
    assert len(rollups) == 2
    assert [row.cohort.evaluation_cohort_id for row in rollups] == [
        "cohort-a",
        "cohort-b",
    ]
    assert [row.strict_final_recall for row in rollups] == [
        CountMetric(1, 3),
        CountMetric(2, 3),
    ]


def test_partial_and_incomplete_evidence_remain_visible_but_outside_strict_metric():
    day = DailyPromotionEvidence(
        report_date="2026-08-15",
        cohort=_cohort(),
        strict_final_recall=CountMetric(1, 3),
        strict_final_editable_recall=CountMetric(0, 3),
        partial_observation_items=5,
        strict_miss_attribution_confirmed=CountMetric(0, 2),
        strict_miss_attribution_strongly_supported=CountMetric(2, 2),
        unresolved_strict_miss_count=1,
        evidence_complete=False,
    )
    (rollup,) = aggregate_promotion_evidence([day])
    assert rollup.strict_final_recall == CountMetric(1, 3)
    assert rollup.partial_observation_items == 5
    assert rollup.complete_evidence_days == 0
    assert rollup.all_evidence_days_complete is False


def test_attribution_denominator_must_equal_strict_recall_miss_count():
    with pytest.raises(ValueError, match="strict Recall miss count"):
        DailyPromotionEvidence(
            report_date="2026-08-15",
            cohort=_cohort(),
            strict_final_recall=CountMetric(1, 3),
            strict_final_editable_recall=CountMetric(0, 3),
            strict_miss_attribution_confirmed=CountMetric(0, 3),
            strict_miss_attribution_strongly_supported=CountMetric(0, 2),
        )


def test_transport_human_utility_and_status_evidence_aggregate_without_decision_logic():
    day1 = DailyPromotionEvidence(
        report_date="2026-08-15",
        cohort=_cohort(),
        natural_runs=CountMetric(4, 4),
        snapshot_rows=CountMetric(218, 218),
        strict_final_recall=CountMetric(1, 3),
        strict_final_editable_recall=CountMetric(0, 3),
        strict_miss_attribution_confirmed=CountMetric(0, 2),
        strict_miss_attribution_strongly_supported=CountMetric(2, 2),
        unresolved_strict_miss_count=1,
        collector_exclusive_human_useful=CountMetric(2, 3),
        overlapping_reference_human_useful=CountMetric(4, 5),
        scheduled_manual_pairs_complete=CountMetric(1, 1),
        eligibility_evidence_status="offline_e1_ready_e2_measurement_only",
        version_reconciliation_status="stale_legacy_state",
        manual_approval_status="not_requested",
    )
    day2 = DailyPromotionEvidence(
        report_date="2026-08-16",
        cohort=_cohort(),
        natural_runs=CountMetric(3, 4),
        snapshot_rows=CountMetric(190, 200),
        capture_gap_count=10,
        strict_final_recall=CountMetric(0, 0),
        strict_final_editable_recall=CountMetric(0, 0),
        strict_miss_attribution_confirmed=CountMetric(0, 0),
        strict_miss_attribution_strongly_supported=CountMetric(0, 0),
        collector_exclusive_human_useful=CountMetric(1, 2),
        overlapping_reference_human_useful=CountMetric(1, 2),
        scheduled_manual_pairs_complete=CountMetric(0, 1),
        eligibility_evidence_status="offline_e1_ready_e2_measurement_only",
        version_reconciliation_status="stale_legacy_state",
        manual_approval_status="not_requested",
    )
    (rollup,) = aggregate_promotion_evidence([day1, day2])
    assert rollup.natural_runs == CountMetric(7, 8)
    assert rollup.snapshot_rows == CountMetric(408, 418)
    assert rollup.capture_gap_count == 10
    assert rollup.collector_exclusive_human_useful == CountMetric(3, 5)
    assert rollup.scheduled_manual_pairs_complete == CountMetric(1, 2)
    assert rollup.version_reconciliation_statuses == ("stale_legacy_state",)
    assert rollup.manual_approval_statuses == ("not_requested",)
    # There is deliberately no synthesized promotion/READY decision here.
    assert not hasattr(rollup, "promotion_decision")
