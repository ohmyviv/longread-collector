# Collector Promotion Evidence Schema v1

Status: **offline evidence schema + aggregation only / not a promotion decision engine**

Date: 2026-08-15

Version: `promotion-evidence-v0.6-v1`

## 1. Purpose

The current Promotion Review v1 defines seven evidence gates:

```text
A Engineering / Transport
B Promotion-grade Recall
C Human Utility / Incremental Human-Useful Recall
D Multi-day Editorial A/B and stability
E Standard Longread factual / eligibility readiness
F Version and health reconciliation
G Manual approval
```

Tasks 0–5 of the second work package now produce more precise evidence for several gates, but that evidence lives in different contracts and time grains. Task 6 defines how those facts should be stored and cumulatively summarized without turning evidence aggregation into an automatic release decision.

The core rule is:

> Daily rows are evidence facts. Cumulative rows are reproducible rollups. Promotion remains a separate manual review.

## 2. Non-goals

This schema does **not**:

- invent a v0.6 promotion threshold;
- average daily percentages;
- mix semantically different runtime/config cohorts without disclosure;
- convert partial observation into strict evidence;
- convert `strongly_supported` or `unknown` causal attribution into `confirmed`;
- write `collector_health`, mode, promotion config, or `auto_promote_when_ready`;
- consume `article_cache` in the production 07:35 path;
- change source selection, source cap, network/body/Firecrawl budget;
- change L4, frozen L5, L6 or LR-v3.5.2;
- trigger Collector manually;
- make a Stage-2/Stage-3 production switch.

## 3. Evidence-source hierarchy

Task 6 does not duplicate item facts that already have an authoritative ledger. It references them.

### Existing authoritative sources

```text
collector_runs
collector_discovery_snapshot
final_recall_audit_v12
final_recall_daily_v12
recommendation_review_v1
recommendation_review_analysis_v1
runs / candidate_log / final_items for LR paired-run evidence
GitHub Actions / merged code versions
```

### Task 2 proposed sources

```text
collector_source_attempts_v1        # future run-scoped selected-source attempt ledger
final_recall_attribution_v1         # future item-level causal sidecar
```

### Task 3 proposed sources

```text
manual/native reference cohort rows
M0 / M1 / M2 / M3 item membership
immutable Collector overlap match references
```

### Task 4 source

```text
scheduled/manual paired-run cohort evidence
```

### Task 5 source

```text
E1/E2 offline eligibility replay/version evidence
```

Task 6 is a summary layer over these sources, never their replacement.

## 4. Evaluation cohort identity

Evidence may be pooled only inside an explicit `evaluation_cohort_id`.

Minimum cohort identity:

```text
evaluation_cohort_id
collector_version
source_policy_version
snapshot_version
canonical_version
eligibility_version
editorial_version
selection_version
final_recall_version
overlap_framework_version
```

A new cohort is required when a semantic/runtime change can alter the meaning of a promotion metric, including material changes to:

- Discovery/source-selection policy;
- snapshot coverage semantics;
- L4/eligibility behavior used in candidate evaluation;
- L5/L6 evaluation basis;
- Final Recall denominator/window semantics;
- independent-reference cohort construction or overlap matching semantics.

Docs-only edits do not reset a cohort.

A pure observability fix may remain comparable only when its output semantics are demonstrably backward compatible; the version difference still remains explicit in source evidence.

## 5. Daily evidence schema

Proposed logical table: `promotion_evidence_daily_v1`.

One row is one report date inside one evaluation cohort. It is not one Collector run.

### Identity

```text
report_date
evaluation_cohort_id
collector_version
source_policy_version
snapshot_version
canonical_version
eligibility_version
editorial_version
selection_version
final_recall_version
overlap_framework_version
evidence_complete
notes
```

### Gate A — Engineering / Transport facts

```text
natural_runs_passed
natural_runs_expected
snapshot_rows_persisted
snapshot_rows_expected
capture_gap_count
duplicate_shadow_network_requests
incremental_shadow_firecrawl_requests
body_fingerprint_mismatches
semantic_p0_count
systemic_p1_count
```

The numerator/denominator for natural runs must describe an explicit audited run set. Do not write `4/4` merely because four schedule slots exist unless all four have reached the evidence cutoff and were actually audited.

### Gate B — strict Recall / candidate-universe coverage

```text
strict_final_discovered
strict_final_denominator
strict_final_editable
strict_final_editable_denominator
strict_m2_observed
strict_m2_denominator
strict_m2_zh_observed
strict_m2_zh_denominator
strict_m2_en_observed
strict_m2_en_denominator
partial_observation_items
```

These are counts. Rates are derived.

`strict_final_*` comes from Final Recall v1.2.

`strict_m2_*` comes from the Collector vs Independent Native / Manual-High Overlap Framework v1.

M2 and M3/final are both retained because they answer different questions.

### Task 2 attribution completeness

Counts are over **strict Recall misses**, not all final items:

```text
strict_miss_confirmed_attribution
strict_miss_total
strict_miss_strongly_supported_attribution
strict_miss_total
unresolved_strict_miss_count
```

Do not use this as a substitute for the item-level sidecar. It only summarizes evidence completeness.

### Gate C — Human Utility

For the bounded plausible subset actually reviewed:

```text
collector_exclusive_human_useful
collector_exclusive_human_reviewed
overlap_human_useful
overlap_human_reviewed
```

An unreviewed Collector-exclusive item is not a negative label.

### Gate D — paired-run evidence

```text
scheduled_manual_pairs_complete
scheduled_manual_pairs_expected
```

Detailed raw/verified/strong/selected multipliers and Jaccard remain in the Task 4 paired-run table/artifact. The daily promotion row only states whether the planned comparable pair evidence was completed.

### Gates E/F/G — explicit states

```text
eligibility_evidence_status
version_reconciliation_status
manual_approval_status
```

These states are stored verbatim. Task 6 does not synthesize them into a READY decision.

## 6. Item-level evidence is never collapsed away

A daily summary cannot explain a miss. Therefore the following item-level identities must remain joinable:

```text
v12_audit_id
attribution_id
reference_item_id
matched_snapshot_id
source_attempt_id
human_review_id
scheduled/manual pair_id
```

Where a sidecar has not yet been implemented, the daily row must mark evidence completeness accordingly rather than inventing an item reference.

## 7. Cumulative rollup contract

The offline implementation in `promotion_evidence.py` uses `CountMetric(numerator, denominator)` and groups days by exact `PromotionEvidenceCohort`.

### Never average daily percentages

Wrong:

```text
Day 1 recall = 1/3 = 33.33%
Day 2 recall = 9/10 = 90%
mean daily recall = 61.67%
```

Correct:

```text
cumulative strict recall = (1+9)/(3+10) = 10/13 = 76.92%
```

The same rule applies to:

- M2 strict overlap;
- Chinese/English M2 overlap;
- Human Utility reviewed fractions;
- paired-run completion;
- transport natural-run reliability;
- snapshot persistence integrity.

### Partial observation

`partial_observation_items` is accumulated as a diagnostic count but never enters a strict denominator.

### Missing evidence

A zero denominator means `not measured / no eligible evidence`, not 0%.

### Mixed versions

If two daily rows have different cohort identities, the aggregator returns two separate cumulative rows. There is no implicit mixed-version aggregate.

## 8. Suggested cumulative materialization

Optional derived table/artifact: `promotion_evidence_cumulative_v1`.

It should be reproducible from daily rows and contain:

```text
evidence_version
evaluation_cohort_id
first_report_date
last_report_date
evidence_days
complete_evidence_days

natural_runs_passed
natural_runs_expected
snapshot_rows_persisted
snapshot_rows_expected
capture_gap_count
...

strict_final_discovered
strict_final_denominator
strict_final_recall
strict_m2_observed
strict_m2_denominator
strict_m2_overlap
strict_m2_zh_observed
strict_m2_zh_denominator
strict_m2_zh_overlap
strict_m2_en_observed
strict_m2_en_denominator
strict_m2_en_overlap

strict_miss_confirmed_attribution
strict_miss_total
strict_miss_confirmed_fraction
unresolved_strict_miss_count

collector_exclusive_human_useful
collector_exclusive_human_reviewed
incremental_human_useful_rate

overlap_human_useful
overlap_human_reviewed

eligibility_evidence_statuses
version_reconciliation_statuses
manual_approval_statuses
```

This cumulative artifact is evidence for Promotion Review, not the authoritative switch state.

## 9. 2026-08-15 first evidence snapshot

The current day is useful as an example but is **not a complete promotion cohort**.

### Gate A

Audited natural evidence includes the accepted pre_report baseline and the clean `zh_midday` run:

```text
COL-20260815-041810-BJT-pre_report
COL-20260815-121459-BJT-zh_midday
```

Both have complete snapshot persistence/readback and no incremental Shadow request/cost defect. However the day is still in progress and Task 0 found a systemic L4 P1 family (`explicit-source / hosting-identity normalization gap`). Therefore a full-day natural-run denominator should not be invented at 16–17 BJT.

### Gate B — Final Recall

```text
strict final denominator = 3
strict discovered = 1
strict recall = 33.33%
strict editable = 0
partial observation items = 5
```

### Gate B — M2 independent-reference overlap

```text
strict M2 denominator = 6
strict M2 observed = 1
strict M2 overlap = 16.67%
```

The all-M2 `2/13=15.38%` figure remains diagnostic because seven item windows are partial relative to the strict snapshot epoch.

### Attribution completeness

Two strict Final Recall misses remain:

```text
Reuters: source attempted, zero raw observations; exact attempt-vs-surface mechanism unresolved
Guardian: no successful evidenced source attempt inside item window
```

Both have strongly supported upstream stage evidence, but the current legacy evidence is not equivalent to a future run-scoped attempt ledger. Do not manufacture a `confirmed` causal distribution from them.

### Gate C

```text
PENDING
```

No bounded Collector-exclusive Human Utility cohort has yet been reviewed under the new framework.

### Gate D

Two historical paired days have been audited (2026-08-13 and 2026-08-15), but the next scheduled LR-v3.5.2 natural sample is still pending 2026-08-16 07:35. The current paired evidence is diagnostic and shows a large scheduled execution-quality gap, not a controlled High-reasoning treatment effect.

### Gate E

After Task 5:

```text
E1: offline high-precision resolver READY
E2: measurement contract READY
E2 hard floor: NOT READY
production eligibility wiring: NOT DONE / NOT AUTHORIZED
```

Therefore Gate E is still **PARTIAL**, not READY for production merely because offline code merged.

### Gate F

```text
FAIL / stale legacy health/evaluation state remains
```

No v0.6 Promotion Reconciliation change has been authorized.

### Gate G

```text
NOT REQUESTED
```

## 10. Current status matrix after Tasks 0–6

Evidence work has become substantially more auditable, but the release decision remains unchanged:

```text
A Engineering/Transport          PASS / READY, prospective natural evidence accumulating
B Strict Recall                  STARTED / EARLY NEGATIVE SIGNAL / NOT PASS
C Human Utility                  PENDING
D Multi-day Editorial A/B        PENDING / framework ready
E Eligibility readiness          PARTIAL / E1 offline ready, E2 measurement-only
F Version/health reconciliation  FAIL / stale legacy state
G Manual approval                NOT REQUESTED

Overall                          NOT_READY / remain SHADOW
```

Task 6 does not itself update the live Promotion Review or `collector_health`; that belongs to a future evidence review / Promotion Reconciliation step after sufficient natural evidence.

## 11. Natural-day update workflow

For each new report day during the 3–7 day evidence window:

1. close/audit the natural Collector run set for the relevant cutoff;
2. verify snapshot/readback/transport invariants;
3. append Final Recall v1.2 strict counts;
4. append item attribution only to the evidence level supported by durable facts;
5. build independent M2/M3 reference cohorts where a valid independent run exists;
6. record strict overlap and language slices;
7. review only a bounded plausible Collector-exclusive set for Human Utility;
8. record scheduled/manual paired-run evidence where available;
9. preserve Eligibility and version-reconciliation states;
10. recompute cumulative numerator/denominator rollups inside the same cohort.

Do not edit historical daily rows merely because a later capture occurred. Late observations are diagnostic sidecars.

## 12. Cohort change / reset rule

When a material semantic change occurs during the evidence window:

- keep all prior daily rows immutable;
- start a new `evaluation_cohort_id`;
- continue reporting both old and new cohorts;
- never backfill the new semantics into old days unless an explicit offline replay is possible and is clearly labelled replay rather than natural evidence.

This preserves controlled comparison instead of hiding moving-goalpost effects.

## 13. Implementation added

```text
src/longread_collector/v06/promotion_evidence.py
tests/test_v06_promotion_evidence.py
```

The module has no production imports or side effects. It contains no promotion-decision or mode-switch method.