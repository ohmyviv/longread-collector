# Scheduled vs Manual Cohort Audit v1

Status: offline analysis / design-only; no LR runtime change

Date: 2026-08-15

## 1. Question

When the scheduled 07:35 run yields materially fewer longreads than an independent manual rerun, determine which parts of the execution differ without falsely attributing the gap to model or reasoning strength when the scheduled model is not observed.

This audit separates:

1. article supply;
2. Discovery/search effort and candidate formation;
3. verification completion;
4. strong-candidate formation;
5. portfolio/final conversion;
6. persistence/readback reliability;
7. model/reasoning observability.

It does not change LR-v3.5.2 or any Collector runtime.

## 2. Pairing contract

A scheduled/manual pair is comparable when, as far as durable evidence allows:

- `report_date` is the same;
- prompt/editor version is the same;
- both use the same active source/config contract or differences are explicitly recorded;
- the manual run is intended as an independent rerun rather than a repair seeded from the scheduled candidate list;
- the manual candidate payload is frozen before scheduled payload inspection when that isolation can be enforced;
- Collector cache is not used pre-freeze unless the comparison explicitly tests that condition;
- temporal offset between runs is recorded;
- publication cutoff eligibility is preserved when comparing final/reference items.

A pair can still be diagnostic when one condition is unknown, but its causal confidence must be reduced.

## 3. Minimum per-run fields

```text
run_id
report_date
run_type
prompt_version
started_at_bj
completed_at_bj
wall_clock_minutes
model_requested
reasoning_effort_requested
model_observed
reasoning_effort_observed
coverage_gate_status
lanes_completed
international_attempted
zh_attempted
special_sections_attempted
raw_candidates
verified_candidates
strong_candidates
selected_count
selected_unique_sources
candidate_log_persisted
final_items_persisted
readback_status
archive_status
article_cache_used_pre_freeze
scheduled_payload_read_pre_freeze
notes
```

If a field is not durably observed, store `unknown`; do not infer it from the client UI or from a later manual run.

## 4. Core derived metrics

### 4.1 Breadth / formation

```text
raw_candidates
raw_per_minute
manual_to_scheduled_raw_multiplier
```

### 4.2 Verification

```text
verified_candidates
verification_completion = verified / raw
```

Only compare this when both runs use comparable verification semantics.

### 4.3 Editorial-strength formation

```text
strong_candidates
strong_yield = strong / raw
strong_per_minute
manual_to_scheduled_strong_multiplier
```

### 4.4 Portfolio conversion

```text
selected_count
selected_over_strong = selected / strong
selected_over_raw = selected / raw
```

A high `selected/strong` with very low strong count is not evidence of a healthy run; it can mean the run produced too little choice for portfolio construction.

### 4.5 Candidate-set stability

When candidate logs are complete for both runs:

```text
raw_exact_url_intersection
raw_jaccard
strong_exact_url_intersection
strong_jaccard
selected_exact_url_intersection
selected_jaccard
```

Low Jaccard with same-day, same-version runs is execution-instability evidence. It is not automatically a model-effect estimate.

### 4.6 Reliability

Report separately:

```text
startup_persistence
candidate_log_persistence
final_items_persistence
history_persistence
archive_persistence
readback
```

Do not allow persistence failure to erase a successful in-memory execution or, conversely, allow an in-memory payload to masquerade as a fully auditable run.

## 5. Causal-identification rule

Observed output difference does not identify the effect of High reasoning unless the treatment is isolated.

For the current 2026-08-15 pair:

```text
scheduled:
  model_requested=unspecified
  reasoning_effort_requested=unspecified
  model_observed=unavailable
  reasoning_effort_observed=unavailable

manual:
  model_requested=GPT-5.6 Thinking
  reasoning_effort_requested=High
  model_observed=unavailable
  reasoning_effort_observed=unavailable
```

Therefore the estimand is not `effect_of_High`.

The observed treatment bundle includes at least:

- scheduled vs interactive execution context;
- model/reasoning request difference;
- search/tool call allocation;
- retry/persistence behavior;
- temporal offset;
- potentially different handling of low-yield lanes despite the same coarse Coverage Gate.

Allowed conclusion:

> The manual GPT-5.6 Thinking + High execution bundle materially outperformed the scheduled execution on candidate breadth and strong-candidate formation.

Not allowed:

> High reasoning alone caused the improvement.

## 6. 2026-08-13 paired cohort

Scheduled:

```text
LR-20260813-0735-BJT-LRv35
run_type=scheduled_auto
prompt_version=LR-v3.5
07:35 → 08:06 (~31 min)
Coverage Gate PASS
raw=5
strong=3
selected=3
candidate_log persisted
```

Manual:

```text
LR-20260813-0832-BJT-LRv35
run_type=manual
prompt_version=LR-v3.5
08:32 → 08:57:23 (~25.4 min)
independent manual rerun
Coverage Gate PASS
raw=14
strong=13
selected=8
candidate_log persisted
```

Multipliers:

```text
manual/scheduled raw      = 14/5  = 2.80x
manual/scheduled strong   = 13/3  = 4.33x
manual/scheduled selected = 8/3   = 2.67x
```

Candidate-set stability:

- scheduled raw exact-URL set: 5 items;
- manual raw exact-URL set: 14 items;
- exact-URL intersection: 0;
- raw Jaccard: 0.

Selected-set exact-URL intersection is also 0 (`3` scheduled vs `8` manual).

The manual set is largely composed of articles already published on 2026-08-12, so the zero overlap cannot be explained simply by new supply arriving during the roughly one-hour temporal offset.

Interpretation: the two executions explored materially different candidate universes despite both formally satisfying the active Coverage Gate.

## 7. 2026-08-15 paired cohort

Scheduled:

```text
LR-20260815-0735-BJT-LRv35
run_type=scheduled_auto
runtime_reliability_version=LR-v3.5.1
07:34:42 → 08:03 (~28.3 min)
source_scan_minimum_met=true
four_lanes_completed=true
raw=8
verified=2
strong=2
selected=2
final payload frozen=2
candidate_log_persisted=false
final_items_persisted=false
final persistence failed: FINAL_PERSISTENCE_SHEETID_MISMATCH
model/reasoning requested=unspecified
model/reasoning observed=unavailable
```

The live `runs` table contains a startup row plus persistence-failure continuation rows rather than one clean fully updated run row. This is an observability/reliability defect and must not be confused with candidate-generation quality.

Manual:

```text
LR-20260815-0811-BJT-LRv35
run_type=manual_rerun
runtime_reliability_version=LR-v3.5.1
08:11:29 → 08:37:20 (~25.9 min)
requested GPT-5.6 Thinking + High
Coverage Gate PASS
lanes=source_pool|open_topic|gap_fill|serendipity
raw=26
verified=23
strong=13
selected=8
candidate/final/history/archive readback completed
scheduled payload not read pre-freeze
article_cache not used pre-freeze
```

Multipliers:

```text
manual/scheduled raw      = 26/8 = 3.25x
manual/scheduled strong   = 13/2 = 6.50x
manual/scheduled selected = 8/2  = 4.00x
```

Verification completion on this pair:

```text
scheduled = 2/8  = 25.00%
manual    = 23/26 = 88.46%
```

Candidate-level Jaccard cannot be reconstructed for the scheduled run because its candidate log was not persisted. The audit must preserve that limitation rather than inventing a scheduled candidate list from the two finals.

## 8. Pooled two-day paired signal

Using only metrics whose definitions are stable across both paired days:

```text
scheduled raw      = 5 + 8  = 13
manual raw         = 14 + 26 = 40
scheduled strong   = 3 + 2  = 5
manual strong      = 13 + 13 = 26
scheduled selected = 3 + 2  = 5
manual selected    = 8 + 8  = 16
```

Pooled multipliers:

```text
manual/scheduled raw      = 40/13 = 3.08x
manual/scheduled strong   = 26/5  = 5.20x
manual/scheduled selected = 16/5  = 3.20x
```

Pooled formation/conversion:

```text
scheduled strong/raw   = 5/13  = 38.46%
manual strong/raw      = 26/40 = 65.00%

scheduled selected/raw = 5/13  = 38.46%
manual selected/raw    = 16/40 = 40.00%

scheduled selected/strong = 5/5   = 100%
manual selected/strong    = 16/26 = 61.54%
```

The similar selected/raw ratio is misleading if read alone. Scheduled runs generated far fewer raw and strong candidates and then selected essentially every strong candidate, leaving little portfolio choice. The largest relative gap is strong-candidate formation.

Approximate pooled wall clock:

```text
scheduled ~59.3 min for 13 raw / 5 strong
manual    ~51.3 min for 40 raw / 26 strong
```

The manual advantage therefore cannot be reduced to a longer elapsed runtime. Wall clock is only a coarse efficiency proxy because it includes tool latency and persistence work.

## 9. Hypothesis adjudication from current evidence

### H1 — true daily supply scarcity

**Rejected as the primary explanation.**

Independent manual runs on both paired days found much larger candidate/strong sets, and Task 3 shows 13 manual editorial-standard candidates on 2026-08-15.

### H2 — scheduled run simply spent less wall-clock time

**Not supported.**

Both manual paired runs completed in less elapsed wall-clock time while producing substantially more raw and strong candidates.

### H3 — existing Coverage Gate guarantees comparable Discovery quality

**Rejected.**

Both 2026-08-13 runs passed the Coverage Gate while their raw candidate sets had zero exact-URL overlap and materially different sizes. On 2026-08-15 the scheduled run also reports source-scan minimum + four lanes complete while yielding only 8 raw / 2 verified.

The gate is therefore necessary operational telemetry, not sufficient evidence of search completion under low-yield conditions.

### H4 — GPT-5.6 Thinking + High alone causes the gap

**Not identifiable.**

Scheduled model/reasoning request and observed runtime are unavailable. The treatment bundle is confounded.

### H5 — scheduled execution quality / effort allocation contributes materially

**Strongly supported.**

Repeated paired-day breadth and strong-candidate gaps, zero candidate overlap on the day with complete dual ledgers, and low verification completion on 2026-08-15 all support an execution-quality difference beyond article supply.

## 10. Relationship to LR-v3.5.2

LR-v3.5.2 already introduces low-yield effort-completion behavior, truthful model audit fields, delta-only checkpoints, dynamic tab location and persistence/readback hardening.

This audit does not authorize another LR edit before the first scheduled natural LR-v3.5.2 acceptance run on 2026-08-16 07:35 BJT.

The next natural sample should be evaluated against this cohort framework before changing LR-v3.5.2 again.

Particularly important questions for that sample:

- Does low-yield effort completion increase raw/verified/strong formation while Coverage Gate remains PASS?
- Is candidate-level persistence complete?
- Does the final run row reconcile cleanly rather than leaving split startup/continuation state?
- Are model/reasoning request/observed fields more informative or still unavailable?
- Does scheduled candidate-set overlap with an independent reference materially improve?

## 11. Future causal test, if model-strength attribution is required

To estimate a reasoning-strength effect, use a separately designed controlled experiment. At minimum hold constant:

- report date/reference corpus or frozen web snapshot;
- prompt/editor/config version;
- discovery lanes and source pool;
- tool/network budget;
- time budget / stopping rule;
- persistence behavior;
- candidate evaluation contract.

Vary only the model/reasoning treatment and persist both requested and observed identities where the platform exposes them.

Without this, report bundle-level performance rather than a model-effect coefficient.

## 12. Multi-day cohort summary schema

Suggested offline fields for Task 6:

```text
pair_id
report_date
scheduled_run_id
manual_run_id
prompt_version
pair_comparability_status
scheduled_raw
manual_raw
raw_multiplier
scheduled_verified
manual_verified
scheduled_strong
manual_strong
strong_multiplier
scheduled_selected
manual_selected
selected_multiplier
scheduled_wall_clock_min
manual_wall_clock_min
raw_jaccard
strong_jaccard
selected_jaccard
scheduled_candidate_log_complete
manual_candidate_log_complete
scheduled_persistence_complete
manual_persistence_complete
scheduled_model_audit_status
manual_model_audit_status
causal_identification_status
notes
framework_version
```

Cumulative reporting should retain per-day pairs; do not collapse different runtime versions into one causal estimate without stratification.
