# Collector Promotion Review v1

Status: **COMPLETE / PROMOTION NOT READY / SHADOW MUST CONTINUE**

Review date: 2026-08-15 BJT

```text
mode: shadow
Collector: collector-v0.6-pr7.3.9
Transport Gate: READY
Editorial Gate: NOT_READY
Promotion Gate: SHADOW
auto_promote_when_ready: FALSE
```

The durable Google Doc version is `每日长文推荐 — Collector Promotion Review v1`, document id `1C3H3aHSGLNI-7FYOsKtQsMw4htpx_wG8FuGuHiX_zus`.

## 1. Purpose

Reconcile historical promotion thresholds with the current v0.6 architecture and evidence, and define what must be true before Collector can move from Shadow to production use.

This is an evaluation/release-design document only. It does not change `collector_config`, `collector_health`, mode, `article_cache`, the 07:35 input path, budgets, L4/L5/L6, or auto-promotion.

## 2. Current decision

**DO NOT PROMOTE.**

Reasons:

- Transport/engineering is READY and the 2026-08-15 Shadow baseline is healthy.
- Editorial Gate remains NOT_READY.
- Promotion Gate remains SHADOW.
- Final Recall v1.2 prospective strict baseline does not yet exist.
- `collector_evaluations` has no formal current `collector-v0.6-pr7.3.9` Human/Editorial release evaluation.
- live `collector_health` blocker still references legacy `v056j` review state.
- Standard Longread Eligibility E0 is offline-only; E1 factual recognition/routing is not production-ready.
- no multi-day Collector universe vs independent High/native Human Utility A/B has established promotion-grade selected/strong/Chinese recall.

## 3. Historical promotion settings

Still-valid principles:

- Transport Gate and Editorial Gate must both be READY before promotion is considered.
- Shadow validation must complete.
- critical product-breaking false accepts must remain zero.
- code/config/run/evaluation versions must reconcile.
- `auto_promote_when_ready` remains FALSE.
- a production switch requires explicit human approval.

Historical/reference thresholds remain useful diagnostics but are not sufficient current-v0.6 promotion criteria on their own:

```text
promotion_min_shadow_days=3
promotion_min_eligible_48h=18
promotion_min_unique_domains_48h=12
promotion_min_success_rate=0.6
promotion_min_ground_truth_accuracy=0.85
promotion_min_candidate_precision=0.85
promotion_min_source_chase_recall=6/7
promotion_min_critical_false_accepts=0
promotion_min_wire_dedup_accuracy=1
v0.4/v0.5 version-specific minimum shadow days
```

Why not mechanical promotion criteria:

- they were introduced under older v0.4/v0.5/v0.5.6 semantics;
- the project later changed L4 provenance semantics, snapshot integrity, Phase0B freshness selection, Recall denominator, full-funnel measurement and Human Recommendation evidence;
- raw eligible counts and technical-domain counts are not Human Utility;
- old fixed-fixture accuracy cannot substitute for current natural Recall/editorial utility.

Do not delete these historical rows today. Reclassify/migrate them in a future reviewed config change while preserving history.

## 4. Promotion Gate v1

### Gate A — Engineering / Transport

Current: **PASS / READY**.

Required:

- multiple stable scheduled natural Collector runs;
- durable full snapshot/readback;
- capture gap=0;
- no duplicate shadow network/body request;
- no unapproved incremental Firecrawl/body/network cost;
- body fingerprint integrity;
- semantic P0=0 and P1 within error budget;
- source cap/freshness policy respected.

The 2026-08-15 baseline satisfies these for the evaluated run, but one run alone cannot authorize promotion.

### Gate B — Promotion-grade Recall

Current: **PENDING**.

Required:

- Final Recall v1.2 item-observation-window evidence from Phase0A-post durable snapshots;
- a prospective strict baseline, not legacy `53/75` or raw candidate counts;
- separation of registry/source coverage, route miss after timely scan, acquisition observation boundary, L4 failure and downstream editorial/portfolio loss;
- strong-item and selected-item recall against an independent reference;
- Chinese Recall reported separately.

No numeric v1.2 promotion threshold is invented here. Calibrate it from prospective evidence.

### Gate C — Human Utility / Incremental Human-Useful Recall

Current: **PENDING**.

Required:

- multi-day evaluation of Collector-only and overlapping candidates against an independent native/manual-High reference;
- established human labels where feasible: 强烈值得 / 值得 / 一般 / 不应推荐;
- Human-useful overlap plus Collector-exclusive Human-useful additions;
- noise/false-accept burden reported separately;
- more raw URLs must never be treated as product value by itself.

Primary question: does Collector consistently add worthwhile articles the existing native path misses without reducing final recommendation quality?

### Gate D — Multi-day Editorial A/B and stability

Current: **PENDING**.

Required:

- multiple natural days, not one favorable run;
- same downstream L4/eligibility/L5/L6 basis for Collector and independent reference universes;
- comparison of strong recall, selected recall, Chinese recall, source breadth, actionable yield and Human Hit Rate;
- evidence that Collector candidate formation is at least as reliable and materially more reproducible than the current scheduled native path;
- no threshold changes during the A/B window to manufacture a pass.

### Gate E — Standard Longread factual / eligibility readiness

Current: **PARTIAL / E0 ONLY**.

Required before `cache_primary` or Primary Discovery:

- E1 high-confidence factual recognition/routing for recurring briefings, academic assets and video-first pages;
- known wrong-medium/asset failures cannot occupy Standard Longread slots;
- no source-wide blacklist;
- length remains measurement-first until E2 proves a safe rule.

E0 is evidence architecture, not production readiness.

### Gate F — Version and health reconciliation

Current: **FAIL / STALE LEGACY STATE**.

Required:

- GitHub merged version, `collector_config`, latest `collector_runs` classification/pipeline version and `collector_evaluations` describe the same release candidate;
- `collector_health` no longer points to stale `v056j` blocker language;
- a current `collector-v0.6-pr7.3.9` evaluation decision exists;
- disagreement blocks promotion rather than being papered over by editing a READY cell.

### Gate G — Manual approval

Current: **NOT REQUESTED**.

Required:

- `auto_promote_when_ready` remains FALSE;
- all prior gates are reviewed together;
- a human explicitly approves the transition;
- rollback criteria and measurement window are defined before switching.

## 5. Recommended staged adoption

Do not jump directly from Shadow to exclusive Primary Discovery.

### Stage 1 — Shadow (current)

- Collector produces evidence/candidate universe only.
- `article_cache` cannot influence pre-freeze 07:35 selection.
- native/manual reference remains independent.

### Stage 2 — Production Candidate Input (future)

Requires manual approval.

- Collector candidates may enter the 07:35 candidate universe.
- native Discovery remains active in parallel.
- `candidate_origin` and provenance are retained.
- all candidates face the same eligibility/L5/L6 rules.
- origin=Collector receives no preferential score.
- production-context overlap, incremental utility and misses are measured.

### Stage 3 — Primary Discovery (later)

Only after Stage 2 demonstrates adequate selected/strong/Chinese recall, Human Utility, stable operations and no systematic blind spot. Native ChatGPT Discovery can then become a bounded audit/fallback/benchmark lane.

This staged path is release design only and does not activate a mode switch.

## 6. Current matrix

```text
A Engineering/Transport       PASS / READY
B Strict Recall               PENDING
C Human Utility               PENDING
D Multi-day Editorial A/B     PENDING
E Eligibility readiness       PARTIAL / E0 ONLY
F Version/health reconciliation FAIL / STALE LEGACY STATE
G Manual approval             NOT REQUESTED

Overall                       NOT_READY / remain SHADOW
```

## 7. Near-term evidence plan

1. keep Collector in Shadow and freeze promotion state;
2. establish Final Recall v1.2 prospective strict baseline from Phase0A-post snapshots;
3. over 3–7 natural days, produce daily artifact-only funnel summaries;
4. compare Collector universe with independent native/manual-High references where available;
5. human-review plausible Collector-exclusive high-value candidates, not every raw URL;
6. calculate Incremental Human-Useful Recall and Chinese recall;
7. continue E1 factual identity/eligibility work offline and separately;
8. after evidence accumulates, create a current-v0.6 Promotion Reconciliation config/release review that retires or reclassifies stale legacy health semantics and writes a current release-candidate evaluation;
9. only then request manual approval for Production Candidate Input.

## 8. Hard boundaries until next review

- mode remains `shadow`;
- Promotion Gate remains `SHADOW`;
- Editorial Gate remains `NOT_READY`;
- `article_cache` production consumption remains prohibited;
- auto promotion remains FALSE;
- no source/network/Firecrawl/body budget expansion to manufacture Recall;
- no production L5 change to make promotion metrics look better;
- no direct `cache_primary` switch from this review.
