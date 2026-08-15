from longread_collector.v06.promotion_evidence import (
    CountMetric,
    DailyPromotionEvidence,
    PromotionEvidenceCohort,
    aggregate_promotion_evidence,
)


def _cohort():
    return PromotionEvidenceCohort(
        evaluation_cohort_id="gap-test",
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


def test_strict_misses_may_have_unmeasured_attribution_without_forcing_a_guess():
    day = DailyPromotionEvidence(
        report_date="2026-08-15",
        cohort=_cohort(),
        strict_final_recall=CountMetric(1, 3),
        strict_final_editable_recall=CountMetric(0, 3),
        strict_miss_attribution_confirmed=CountMetric(0, 0),
        strict_miss_attribution_strongly_supported=CountMetric(0, 0),
        evidence_complete=False,
    )
    (rollup,) = aggregate_promotion_evidence([day])
    assert rollup.strict_final_recall == CountMetric(1, 3)
    assert rollup.strict_miss_attribution_confirmed == CountMetric(0, 0)
    assert rollup.strict_miss_attribution_confirmed.rate is None
