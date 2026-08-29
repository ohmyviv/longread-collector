# Phase 3 — Chinese Route S1 Timestamp Measurement Contract v2

Date: 2026-08-29 BJT

Version: `zh-route-shadow-timestamp-measurement-v2`

Status: OFFLINE / READ-ONLY / MEASUREMENT ONLY

## Why v2 exists

S1 Day-0 and subsequent natural exposures proved that Treatment execution and telemetry can be valid while the persisted listing timestamp association is materially wrong. Therefore route execution validity and freshness utility must be measured separately.

The v2 contract answers one narrow question:

> Given an already-persisted S1 route item, what publication-time interval is supported by explicit evidence, and can the item be classified fresh/stale without guessing?

It does not change live Treatment discovery/parsing and does not define Final Recall publication evidence.

## Evidence types

### 1. Persisted trusted exact

A persisted `published_at` participates as exact evidence only when `publication_time_confidence=high` and it is not a date-only value.

### 2. Persisted date-only

A persisted value explicitly marked `date_only` is a full local calendar-day interval, not midnight-as-exact-time.

### 3. Listing card relative age

Explicit article-card text `N分钟前` / `N小时前` becomes a bounded interval relative to `treatment_observed_at_bj`.

- minute label uncertainty: ±2 minutes;
- hour label uncertainty: ±2 hours;
- interval is clipped so it cannot imply publication after observation.

The uncertainty is deliberately conservative. It is sufficient for the 7-day S1 freshness question without pretending to know an exact publication minute.

### 4. Listing card `今天/昨天 HH:MM`

Explicit article-card local clock text is treated as an S1 exact-to-minute listing observation. It is still S1 listing evidence only, not Final Recall A-level evidence.

### 5. First-party URL path date

Supported path forms include conventional `/YYYY/MM/DD/`, `/YYYY-MM-DD/`, and EEO `/YYYY/MMDD/`. A URL path date is a calendar-day interval only. It never becomes an exact publication timestamp.

## Conflict policy

Fail closed.

- trusted persisted evidence vs article-card relative/day-clock evidence that cannot overlap → `conflict`;
- measurement-bearing evidence vs URL-path date on a different calendar day → `conflict`;
- low-confidence/untrusted persisted values are diagnostic only and do not override explicit measurement-bearing evidence;
- no trustworthy evidence → `unknown`.

No conflict is silently resolved in favor of the value that makes a route look fresher.

## Freshness policy

The current live S1 metadata target is 7 days. With observation time `T`, v2 uses:

`[T - 7 days, T + 5 minutes]`

For an evidence interval:

- entire interval inside window → `fresh`;
- entire interval before lower bound → `stale`;
- entire interval after upper bound → `future`;
- interval straddles the lower/upper boundary → `boundary_unknown`;
- contradictory evidence → `conflict`;
- no usable evidence → `unknown`.

This avoids converting date-only evidence at the 7-day edge into a false exact answer.

## Fixed four-exposure replay universe

Frozen eligible runs:

1. `COL-20260827-224813-BJT-zh_midday`
2. `COL-20260828-040117-BJT-zh_evening`
3. `COL-20260828-234148-BJT-zh_midday`
4. `COL-20260829-050025-BJT-zh_evening`

Persisted Treatment item rows: **871**.

Source rows:

- Yicai: 428
- Jiemian-depth: 292
- Caixin: 95
- EEO: 56

### Ledger-derived v2 replay

The following counts are deterministic reconstruction from the frozen live item ledger under the v2 evidence rules above. They are not written back to the Sheet.

| Source | Fresh | Stale | Conflict | Boundary unknown | Unknown | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Yicai | **297** | 0 | **6** | 0 | 125 | 428 |
| Jiemian-depth | **180** | **112** | 0 | 0 | 0 | 292 |
| Caixin | **15** | **5** | **72** | 2 | 1 | 95 |
| EEO | **9** | **40** | 0 | 0 | 7 | 56 |
| **Total** | **501** | **157** | **78** | **2** | **133** | **871** |

Interpretable `fresh + stale` rows = **658/871 = 75.5%**. This number is a measurement-coverage statistic, not route precision or utility.

### Measurement-state decomposition

| Measurement state | Count |
| --- | ---: |
| bounded relative | 163 |
| card-clock exact | 134 |
| trusted exact | 292 |
| date-only | 71 |
| conflict | 78 |
| unknown | 133 |
| **Total** | **871** |

## What changed relative to persisted S1 status

### Yicai

The old parser made most Yicai rows look `date_unknown`. The ledger contains 167 item rows with explicit `N分钟前/N小时前` evidence and 136 rows with `昨天 HH:MM` evidence. v2 can interpret most of these conservatively as fresh. Six rows contain a persisted high-confidence timestamp that contradicts the card-local evidence and therefore become `conflict`, not fresh.

Conclusion: Yicai is **not mostly timestamp-unobservable**; rather, the current parser fails to associate abundant card-local time evidence reliably.

### Jiemian-depth

All 292 rows have exact/high listing evidence. The existing timestamp observability signal survives v2: 180 are within the 7-day window and 112 are genuinely older. Jiemian therefore has the cleanest current S1 timestamp measurement.

### Caixin

The prior surface summary labeled core routes stale because 72 core rows persisted Aug 1–2 date-only values. Those same rows carry first-party URL-path dates spanning later August dates. Because both are explicit date evidence and disagree, v2 marks all 72 as `conflict` rather than choosing one side. This is the clearest proof that the previous `stale_surface` label was measurement-contaminated.

The remaining latest/promotion-control rows demonstrate a mix of current, boundary, old, and unknown URL dates; commercial-control noise remains a separate content-quality dimension.

### EEO

The first exposure becomes more interpretable:

- 9 `technology_plus` items have current compact URL date paths and are fresh under the 7-day S1 window;
- 40 finance/industry RSS items expose explicit 2011 URL paths and are genuinely stale;
- 7 rows lack usable time evidence.

This supports the earlier technical diagnosis that EEO is not simply `date_unknown`: part of the route is current, while legacy RSS surfaces are truly stale/broken for present-day discovery.

## Decision implications

1. Persisted S1 `recent_item_count` / `proven_recent` must not be used directly for source utility comparison.
2. v2 is sufficient to unblock **measurement interpretation**, but it does not itself prove source utility.
3. Jiemian can proceed to later fixed-32 utility counterfactual when the S1 review reaches that stage.
4. Yicai utility can now be re-evaluated with v2-derived freshness rather than current persisted freshness.
5. Caixin remains blocked by explicit timestamp conflict and needs another independent intended-date exposure before route-level judgment.
6. EEO needs another independent intended-date exposure; its first exposure already identifies stale RSS surfaces as a technical issue.
7. S1 overall remains `NOT_READY` for S2 admission because fixed-budget displacement/value evidence has not been produced and two sources lack repeatability.

## Non-goals / frozen boundary

This contract does **not**:

- modify `zh_route_shadow_discovery_v1.py` or the live Treatment parser;
- rewrite `collector_route_shadow_items` or observations;
- promote URL path date to Final Recall A-level publication evidence;
- change source registry, source/host cap, 32-body budget or route portfolio;
- connect S2 body extraction or the 07:35 Editor;
- change production, article_cache consumption, `v06_primary` or auto-promotion;
- design or change the scheduler.

Scheduler reliability work is deferred by explicit user decision while natural GitHub scheduling is observed for recovery.
