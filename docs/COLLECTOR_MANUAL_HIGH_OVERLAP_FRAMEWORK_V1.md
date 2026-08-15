# Collector vs Independent Native / Manual-High Overlap Framework v1

Status: design + first diagnostic baseline; offline only; not a promotion switch

Date: 2026-08-15

## 1. Purpose

This framework measures how much of an independently discovered, human-verified longread reference universe the Collector had observed before the daily 07:35 report cutoff.

It is intentionally separate from Final Recall v1.2:

- Final Recall asks whether the Collector captured the **final published recommendation set**.
- Overlap evaluation asks whether the Collector captured the broader **independent candidate universe**, especially candidates that independently met the Standard Longread editorial bar even if portfolio selection later excluded them.

Using only final selected items understates Discovery misses because portfolio decisions shrink the denominator. Using all raw manual discoveries overstates Discovery misses because raw discovery includes short pieces, newsletters, duplicates, out-of-window items and candidates that cannot be independently verified.

## 2. Frozen boundaries

This framework does not change:

- Collector runtime, source registry, routes or source cap;
- Firecrawl/network/body budget;
- Final Recall v1.2 denominators;
- L4/L5/L6;
- LR-v3.5.2;
- production `article_cache` consumption;
- Promotion state or auto-promotion.

No route change should be justified from one overlap cohort alone.

## 3. Reference-run classes

Each independent comparator run must declare `reference_run_type`.

```text
prospective_independent
retrospective_manual_high
scheduled_native_reference
other_explicit_reference
```

The 2026-08-15 manual GPT-5.6 Thinking + High run is `retrospective_manual_high`: it started after the 07:35 Collector/editorial cutoff and therefore can be used as a high-quality diagnostic reference, but must not silently be treated as a perfectly prospective gold standard.

A retrospective reference item is eligible for cutoff-aligned comparison only if its publication evidence places it at or before the 07:35 cutoff. Post-cutoff publications are excluded from that report-date overlap denominator.

Retrospective search/index state may be richer than state available exactly at cutoff. This is a known asymmetry and must remain visible in interpretation.

## 4. Nested manual reference cohorts

For each manual/native reference run, derive four nested sets.

### M0 — raw discovery effort

Every candidate persisted by the independent run.

Purpose: measure search breadth/effort only. Never use M0 directly as a Collector Recall denominator.

### M1 — independently verified candidate universe

M0 items with sufficient source/date/body verification under the reference run contract.

Typical inclusion: verification level A/B or equivalent.

Purpose: remove tool-access failures and unverifiable candidates while retaining both Standard and non-Standard formats.

### M2 — Standard Longread reference universe

M1 items that independently meet the Standard Longread editorial bar before portfolio composition.

For LR-v3.5-style logs, the initial operational mapping is:

```text
disposition in {selected, strong_rejected}
```

`strong_rejected` is included only when its reason states that the item met the editorial standard and lost at portfolio/pairwise selection. Candidates rejected as non-Standard Longread, too shallow/newsy, duplicate, out of time window, or unverifiable are excluded.

M2 is the primary candidate-universe overlap denominator.

### M3 — final selected reference set

The final recommendation set.

Purpose: product-output Recall. This remains governed by Final Recall v1.2 rather than replacing it with this framework.

## 5. Why M2 is the primary overlap cohort

M2 best isolates the question:

> Did Collector Discovery observe the independently identified articles that were actually strong enough to deserve downstream editorial consideration?

It avoids two opposite errors:

- M0/M1 inflation: counting Axios-length explainers, newsletters, duplicates or failed-verification pages as Collector misses;
- M3 compression: allowing portfolio selection to hide articles that were editorially strong but lost only because another same-source/same-cluster article was chosen.

M2 still contains independent editorial judgement and therefore is not a pure universe census. It is a high-value reference cohort, not proof that all M2-only articles are objective Collector failures.

## 6. Cutoff and observation-window alignment

Every M2/M3 item is evaluated using the same temporal discipline as Final Recall v1.2:

```text
item observation start = publication time/date, bounded by the maximum editorial window
item observation end   = report-date 07:35 BJT cutoff
```

Collector observations after 07:35 are `late_observation_after_cutoff`, not hits.

The Phase0A promotion-grade strict snapshot epoch remains authoritative. If an item observation window starts before the strict epoch, the item is `partial_observation` and excluded from promotion-grade strict overlap even if a historical diagnostic match exists.

Therefore every cohort reports both:

- all-item diagnostic overlap; and
- strict-overlap subset.

## 7. Matching contract

Preferred match precedence:

```text
1. canonical URL exact/normalized match
2. original URL / known tracking-parameter-normalized match
3. normalized title + compatible source/domain
4. high-confidence title/source fuzzy match requiring explicit review
```

A source/domain mismatch cannot be overridden by title similarity without explicit manual review.

Record:

```text
match_status
match_type
matched_snapshot_id
matched_run_id
matched_first_seen_at_bj
late_observation_after_cutoff
manual_match_review_required
```

Matching must use immutable `collector_discovery_snapshot`, not mutable `article_cache` alone, so historical first observation and prefilter state are preserved.

## 8. Core set notation

For a cutoff-aligned reference cohort `R` and Collector raw discovery observations `C` within each item's valid window:

```text
R_hit  = items in R with a Collector observation by cutoff
R_miss = R \ R_hit
```

Do not define `Collector precision = |R_hit| / |C|`. The manual reference is not an exhaustive universe, so Collector-exclusive items are not false positives merely because manual High did not find them.

## 9. Core metrics

For M2:

```text
M2_diagnostic_overlap = observed_M2_all / M2_all
M2_strict_overlap     = observed_M2_strict / M2_strict
M2_partial_overlap    = observed_M2_partial / M2_partial
```

Also report:

```text
M2_reference_only_count
M2_overlap_count
M2_late_observation_count
M2_unknown_match_count
```

Slice at minimum by:

- language: zh / en;
- source cohort;
- source registry / outside-registry status;
- route status;
- timely vs deep-read age bucket;
- primary miss attribution stage from Final Recall Attribution Contract v1 when available.

M3 continues to use Final Recall v1.2 strict Recall as the primary product-output metric.

## 10. Collector-exclusive items

Collector-exclusive candidates are potentially valuable incremental recall, not false positives.

Let:

```text
C_exclusive = plausible Collector candidates not matched to M2
```

Only a bounded, plausibility-filtered subset should receive human review. For reviewed items, record whether the user would consider them recommendation-worthy.

Future metric:

```text
Incremental Human-Useful Recall
= human-useful Collector-exclusive items / reviewed plausible Collector-exclusive items
```

This metric must remain separate from M2 reference overlap because the independent manual run can itself miss good articles.

## 11. Reference independence and contamination controls

A comparator is strongest when its Discovery process is independent from Collector outputs.

Record per reference run:

```text
reference_run_id
reference_run_type
requested_model
requested_reasoning_effort
started_at_bj
completed_at_bj
report_cutoff_at_bj
collector_output_visible_to_reference_run
reference_used_article_cache
reference_used_collector_snapshot
reference_search_method
```

For a clean manual-High comparator:

- Collector candidate lists should not be injected as seeds;
- Collector `article_cache` should not be used to discover candidate URLs;
- overlap should be computed only after the independent candidate set is frozen;
- if Collector output was visible to the operator/model, mark possible contamination rather than asserting full independence.

The 2026-08-15 manual rerun was explicitly intended as an independent rerun, but it remains retrospective relative to the 07:35 cutoff.

## 12. 2026-08-15 manual-High reference cohorts

Reference run:

```text
LR-20260815-0811-BJT-LRv35
requested: GPT-5.6 Thinking + High
report_date: 2026-08-15
reference_run_type: retrospective_manual_high
```

Persisted candidate structure:

```text
M0 raw                         26
M1 independently verified     23
M2 Standard Longread          13
M3 final selected              8
```

M2 composition:

```text
8 selected
5 strong_rejected that met editorial standard but lost portfolio/pairwise selection
```

### 12.1 Diagnostic all-M2 overlap

Across all 13 M2 items, two have a pre-cutoff Collector raw observation:

1. FT — `AI frenzy drives Chinese tech valuations to multiples of US peers`;
2. 虎嗅 — `中国车把日本车打成了奢侈品`.

```text
M2_all = 13
M2_observed_all = 2
M2_diagnostic_overlap = 15.38%
```

This is **diagnostic only** because seven M2 item windows begin before the promotion-grade strict snapshot epoch.

### 12.2 Promotion-grade strict-M2 overlap

M2 items whose observation windows begin after the strict snapshot epoch and are available before 07:35:

1. FT valuation article — observed;
2. Reuters `While the world is distracted...` — not observed;
3. Guardian weather/culture-war article — not observed;
4. Guardian Burnham/climate article — not observed;
5. Guardian Stourbridge wildfire article — not observed;
6. Guardian Great Barrier Reef/media-climate article — not observed.

```text
M2_strict = 6
M2_observed_strict = 1
M2_strict_overlap = 16.67%
```

The other seven M2 items remain `partial_observation` for promotion-grade purposes.

### 12.3 M3 comparison

The same report date's Final Recall v1.2 product-output result is:

```text
M3 final selected = 8
headline discovered = 2 / 8 = 25%          # mixed strict + partial, diagnostic headline
strict M3 = 3
strict discovered = 1 / 3 = 33.33%         # promotion-grade early sample
```

M2 and M3 answer different questions and must not be substituted for one another.

## 13. First interpretation of the 2026-08-15 M2 baseline

The low M2 overlap supports the proposition that the 07:35 two-item scheduled result was not explained by true article supply scarcity. Independent High found a substantially larger editorial-standard candidate set.

It does **not** establish one root cause. Known strict M2 misses already span different upstream mechanisms:

- Reuters: source attempt evidenced but zero raw source observations; exact attempt-vs-surface submechanism unresolved under current durable evidence;
- Guardian cluster: effective route exists but no successful evidenced source attempt in the item window;
- FT valuation: observed but deferred at prefilter capacity, therefore an overlap hit but a downstream candidate-reach miss.

Overlap measures candidate coverage; the Attribution Contract identifies why reference-only items were missed.

## 14. Multi-day reporting contract

For each natural report date with an independent reference run, persist one cohort summary:

```text
report_date
reference_run_id
reference_run_type
M0_count
M1_count
M2_count
M2_strict_count
M2_observed_count
M2_strict_observed_count
M2_diagnostic_overlap
M2_strict_overlap
M2_late_observation_count
M3_count
M3_strict_count
M3_strict_recall
zh_M2_strict_count
zh_M2_strict_observed
en_M2_strict_count
en_M2_strict_observed
reference_contamination_status
notes
framework_version
```

Item-level rows should retain match and attribution references rather than only summary counts.

Do not average daily percentages naïvely. Cumulative overlap should be calculated from cumulative numerators and denominators:

```text
cumulative_M2_strict_overlap
= sum(M2_strict_observed_count) / sum(M2_strict_count)
```

## 15. Acceptance conditions for using M2 in Promotion Review

M2 overlap becomes promotion-grade evidence only when:

1. reference cohort construction is deterministic and persisted;
2. comparator independence/retrospective status is explicit;
3. publication/cutoff eligibility is verified;
4. Collector snapshot coverage is strict for the item window;
5. matching uses immutable observations;
6. unresolved fuzzy matches are excluded or manually adjudicated;
7. strict numerator/denominator are reproducible from persisted rows;
8. at least several natural days and both language cohorts are represented.

No single-day threshold is defined by this document.

## 16. Relationship to other work packages

- Task 2 / Final Recall Attribution Contract v1 explains **where** M2 reference-only items fell out.
- Task 3 / this framework measures **how much** of an independent high-value candidate universe Collector covered.
- Task 4 audits whether scheduled vs manual execution cohorts differ in discovery effort and quality.
- Task 5 Eligibility E1/E2 can later make M2 construction less dependent on manual disposition labels.
- Task 6 should define durable daily/item schemas and cumulative aggregation; it may reuse this framework but must not alter runtime behavior without separate review.
