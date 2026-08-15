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

## 1. Current decision

**DO NOT PROMOTE.**

Transport/engineering is healthy, but promotion evidence is incomplete. Final Recall v1.2 has now produced its first live scheduled strict datapoint; the result is an early negative signal, not a pass. Human Utility, multi-day A/B, E1 factual eligibility readiness and current-version health/evaluation reconciliation are also not complete.

## 2. Historical promotion settings

Still-valid principles:

- Transport Gate and Editorial Gate must both be READY before promotion is considered.
- Shadow validation must complete.
- product-breaking false accepts must remain zero.
- code/config/run/evaluation versions must reconcile.
- `auto_promote_when_ready` remains FALSE.
- production switch requires explicit human approval.

Historical thresholds remain useful diagnostics but are not sufficient current-v0.6 promotion criteria by themselves:

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
```

They were introduced under older v0.4/v0.5/v0.5.6 semantics. The project later changed L4 provenance, snapshot integrity, Phase0B freshness selection, Recall denominator, full-funnel measurement and Human Recommendation evidence. Preserve these rows as history; reclassify them only in a future reviewed config change.

## 3. Promotion Gate v1

### Gate A — Engineering / Transport

Current: **PASS / READY**.

Required: stable natural Collector runs, durable full snapshot/readback, capture gap=0, no duplicate or unapproved incremental shadow network/body/Firecrawl cost, body fingerprint integrity, semantic P0=0/P1 within budget, and source-cap/freshness compliance.

The 2026-08-15 baseline satisfies these for the evaluated run.

### Gate B — Promotion-grade Recall

Current: **STARTED / FIRST LIVE STRICT DATAPOINT AVAILABLE / EARLY NEGATIVE SIGNAL / NOT PASS**.

GitHub Actions `31857563720` completed the first scheduled Final Recall v1.2 `write_to_sheets` run and verified both `final_recall_daily_v12` and all 8 detail rows in `final_recall_audit_v12`.

Audited final run:

```text
LR-20260815-0811-BJT-LRv35
final_items=8
registered/effective-route discovered=2/8=25%
partial_observation_items=5
strict_effective_route_denominator=3
strict_effective_route_discovered=1
strict_effective_route_discovery_recall=33.33%
strict_effective_route_editable=0
```

The five partial items cross the Phase0A strict snapshot epoch and are correctly excluded from the promotion-grade strict denominator.

The three strict 0–3d items are:

- FT `AI frenzy drives Chinese tech valuations to multiples of US peers`: captured by RSS but rejected at prefilter `source_initial_cap_reserve`;
- Reuters `While the world is distracted, China steps up its strategic game`: strict `not_discovered`;
- Guardian extreme-weather/culture-war commentary: strict `not_discovered`.

This 1/3 result is a meaningful early warning that route/discovery quality may remain a promotion blocker, but n=3 is too small for a stable threshold or route rewrite. Continue prospective accumulation; do not expand budgets or patch routes from this datapoint alone.

### Gate C — Human Utility / Incremental Human-Useful Recall

Current: **PENDING**.

Required: multi-day Collector-only/overlap evaluation against independent native/manual-High reference, established human labels for plausible high-value candidates, Collector-exclusive Human-useful additions, and noise burden reported separately.

### Gate D — Multi-day Editorial A/B and stability

Current: **PENDING**.

Required: multiple natural days on the same downstream L4/eligibility/L5/L6 basis, comparing strong recall, selected recall, Chinese recall, source breadth, actionable yield and Human Hit Rate without changing thresholds during the measurement window.

### Gate E — Standard Longread factual / eligibility readiness

Current: **PARTIAL / E0 ONLY**.

Before `cache_primary` or Primary Discovery: E1 must resolve high-confidence recurring briefing, academic asset and video-first identities; known wrong-medium/asset failures must not occupy Standard Longread slots; no source-wide blacklist; length remains measurement-first until E2 proves a safe rule.

### Gate F — Version and health reconciliation

Current: **FAIL / STALE LEGACY STATE**.

`collector_health` still references `editorial_gate_not_ready_v056j_review_pending`, while runtime is `collector-v0.6-pr7.3.9`; `collector_evaluations` still lacks a formal current-pr7.3.9 Human/Editorial release evaluation. Existing `collector_version_reconciliation_policy` makes this mismatch promotion-blocking.

### Gate G — Manual approval

Current: **NOT REQUESTED**.

`auto_promote_when_ready` remains FALSE. All prior gates, rollback criteria and measurement window must be reviewed before an explicit human approval.

## 4. Recommended staged adoption

Do not jump from Shadow directly to exclusive Primary Discovery.

```text
Stage 1 — Shadow (current)
  ↓
Stage 2 — Production Candidate Input
  Collector candidates may enter the 07:35 universe;
  native Discovery remains parallel;
  candidate_origin/provenance retained;
  identical eligibility/L5/L6 rules;
  no origin preference.
  ↓
Stage 3 — Primary Discovery
  only after production-context multi-day A/B proves adequate
  selected/strong/Chinese recall, Human Utility and stability.
```

This is release design only and does not activate a mode switch.

## 5. Current matrix

```text
A Engineering/Transport          PASS / READY
B Strict Recall                  STARTED / EARLY NEGATIVE SIGNAL / NOT PASS
C Human Utility                  PENDING
D Multi-day Editorial A/B        PENDING
E Eligibility readiness          PARTIAL / E0 ONLY
F Version/health reconciliation  FAIL / STALE LEGACY STATE
G Manual approval                NOT REQUESTED

Overall                          NOT_READY / remain SHADOW
```

## 6. Near-term evidence plan

1. keep Collector in Shadow and freeze promotion state;
2. continue Final Recall v1.2 prospective strict accumulation from the Phase0A epoch;
3. over 3–7 natural days, produce daily artifact-only funnel summaries;
4. compare Collector universe with independent native/manual-High references where available;
5. human-review plausible Collector-exclusive high-value candidates, not every raw URL;
6. calculate Incremental Human-Useful Recall and Chinese recall;
7. keep E1 factual identity/eligibility work offline and separate;
8. after evidence accumulates, perform a reviewed current-v0.6 Promotion Reconciliation config/release change and create a current release-candidate evaluation;
9. only then request manual approval for Production Candidate Input.

## 7. Hard boundaries

- mode remains `shadow`;
- Promotion Gate remains `SHADOW`;
- Editorial Gate remains `NOT_READY`;
- `article_cache` production consumption remains prohibited;
- auto promotion remains FALSE;
- no source/network/Firecrawl/body budget expansion to manufacture Recall;
- no production L5 change to make promotion metrics look better;
- no direct `cache_primary` switch from this review.
