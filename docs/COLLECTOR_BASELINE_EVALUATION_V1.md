# Collector Baseline Evaluation v1

Status: **COMPLETE / SHADOW BASELINE ESTABLISHED / NO PROMOTION EFFECT**

Evaluation date: 2026-08-15 BJT

Primary natural run:

```text
collector_run_id: COL-20260815-041810-BJT-pre_report
GitHub Actions:   31837235761
artifact:         v06-shadow-pre_report-31837235761
Collector:        collector-v0.6-pr7.3.9
control:          collector-v0.5.6m
```

The durable Google Doc version is `每日长文推荐 — Collector Baseline Evaluation v1`, document id `160hPZ0ni0pwYwlGia59MkMIBQJe4Dl2uotxLFwzY4G8`.

## 1. Purpose

Establish the first formal post-Phase0B Collector Shadow baseline using natural scheduled evidence plus merged PR #93 observation-aware funnel semantics. This evaluation does not change Collector runtime/config, source cap, network/Firecrawl/body budgets, L4/L5/L6, `article_cache` consumption or promotion state.

## 2. Authority reconciliation

Earlier handoff text incorrectly associated Actions `31837235761` with `COL-20260815-042614-BJT-pre_report` and snapshot `156`.

Higher-authority GitHub artifact and live `collector_runs` agree on:

```text
COL-20260815-041810-BJT-pre_report
started  04:18:10 BJT
completed 04:29:02 BJT
snapshot 208/208
readback true
```

Source selection:

```text
freshness_reserve:
  wired
  newyorker
  restofworld
  quanta
  atlantic
  propublica
coverage_rotation:
  yale-e360
  404media
```

The Phase0B acceptance decision remains valid; only the stale run tuple is corrected.

## 3. Engineering / Transport baseline

PASS:

- final_status=success;
- sources_scanned=8;
- six freshness + two coverage;
- missing freshness sources=[];
- snapshot expected/persisted=208/208;
- readback=true;
- full_snapshot_invariant=true;
- capture_gap_count=0;
- shadow_request_count=0;
- shadow_firecrawl_request_count=0;
- shadow_incremental_cost=0;
- body_fingerprint_mismatches=0;
- zero_duplicate_network_invariant=true;
- fallback requests_sent/succeeded/failed=0/0/0.

Effective-route audit:

```text
sources_attempted=8
effective_native=4
partial_native=4
no_native_results=0
native_metadata_items=176
lookback=7d
metadata_limit_per_source=24
```

`partial_native` is not synonymous with source failure: all eight selected sources returned native results.

## 4. Observation-aware full funnel

PR #93 semantics apply. Missing `acquisition_result` means the control path did not expose a body to shadow; it is an observation boundary, not an Acquisition failure. Projection is not currently emitted.

```text
12 attempted Discovery surfaces
→ 208 raw Discovery observations
→ 208 unique URL hints
→ 202 gate acquire + 5 hard_reject + 1 defer
→ 32 control-body observed
→ 32 Acquisition success
→ 32 Canonical success
→ 32 Editorial decision-eligible
→ 14 consider/actionable + 18 low_value + 0 recommend
→ 10 selected
Projection emitted: 0
```

Selection actions across all 208 observations:

```text
select_standard=10
reject=23
defer=175
```

Do not describe the 175 defers as 175 Acquisition or editorial failures; most are body-not-observed boundaries.

## 5. Reference comparison

Reference natural pre_report `COL-20260814-042612-BJT-pre_report` / Actions `31740786490`:

```text
12 surfaces
190 raw / 190 unique
186 gate acquire
32 control bodies
30 Acquisition success + 2 partial
30 Canonical/editorial decision-eligible
14 actionable
10 selected
snapshot 190/190/readback/full invariant true
shadow request/Firecrawl/incremental cost = 0
```

2026-08-15 vs reference:

- raw universe 190→208 (+18, +9.5%);
- selected 10→10;
- actionable 14→14;
- observed Acquisition 30 success +2 partial →32 success;
- engineering invariants remain clean.

This supports mechanical stability, not product superiority. The 32 body-observed items are capacity/control-selected, not a random sample of all 208 observations.

## 6. Product/editorial interpretation

The ten v0.6 selected items all carry frozen L5 verdict `consider`; none is `recommend`. This does not establish Human Utility. The existing 80-item Human Recommendation Review covers delivered LR recommendations, not these Shadow selected items.

One selected WIRED item shows a page-surface/medium disagreement. Preserve it as E1/eligibility diagnostic evidence; this single sample is not sufficient to reopen frozen L4/L5.

## 7. Same-day subsequent evidence — Final Recall v1.2

After this engineering baseline was established, GitHub Actions `31857563720` completed the first live scheduled Final Recall v1.2 `write_to_sheets` run and verified both the daily summary and all 8 detail rows.

For the 8-item independent manual-High final set:

```text
registered/effective-route discovered = 2/8 = 25%
partial_observation_items = 5
strict_effective_route_denominator = 3
strict_effective_route_discovered = 1
strict discovery recall = 33.33%
strict editable = 0
```

The strict three are all age 0–3d: one FT item was captured by RSS but rejected at `source_initial_cap_reserve`; Reuters and Guardian items were strict `not_discovered`.

This does not change the engineering baseline PASS. It strengthens the conclusion that product/editorial promotion is NOT READY. The strict denominator is only 3, so this is an early negative signal, not a stable long-run Recall estimate and not grounds for a route/budget rewrite by itself.

## 8. Decision

```text
Collector Baseline Evaluation v1: PASS AS SHADOW BASELINE
Transport/engineering baseline:    PASS
Editorial/product promotion:       NOT READY
Promotion effect:                  NONE
```

Next evidence is multi-day prospective Final Recall v1.2 plus Collector-vs-independent-reference A/B, not a runtime expansion based on a single day.
