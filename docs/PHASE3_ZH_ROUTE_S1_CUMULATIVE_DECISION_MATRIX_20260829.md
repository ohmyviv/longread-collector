# Phase 3 — Chinese Route S1 cumulative decision matrix

Date: 2026-08-29 BJT

Status: EVIDENCE LEDGER / SHADOW ONLY / NO PRODUCTION DECISION

## Purpose

Replace raw-run counting with a source-level evidence maturity ledger. A new natural run matters only when it changes one or more source-level evidence cells. This matrix does not authorize S2 execution, route promotion, source/cap/budget changes, Editor wiring, or production consumption.

The frozen S1 contract defines maturity **per source/surface**, not as one all-or-nothing four-source gate. Therefore `portfolio-wide S1 incomplete` and `a specific source is S2-ready for review` may both be true.

## Current eligible-exposure ledger

| Source | Eligible exposures | Independent intended dates | Execution repeatability | Timestamp measurement | Incremental coverage evidence | Technical/noise evidence | Fixed-32 value evidence | Current state |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| Jiemian-depth | 4 | 2 (2026-08-27, 2026-08-28) | **Established across intended dates** | Strongest of current S1 sources; all 292 persisted item rows have exact/high listing evidence; v2 replay separates 180 fresh / 112 stale | **Repeated non-zero incrementals** on all four surfaces/exposures; `jiemian_medicine` recovered the known gene-therapy clean miss in 4/4 eligible exposures with Control overlap FALSE in 4/4 | Requests/parsing stable in all four exposures; 16/16 source-surface exposures report zero explicit noise | Not yet measured | **S2_READY_FOR_REVIEW / S2 NOT STARTED** |
| Yicai | 4 | 2 (2026-08-27, 2026-08-28) | **Established across intended dates** | Live persisted association is systemically contaminated, but v2 now supplies fail-closed source-level interpretation: 297 fresh / 6 conflict / 125 unknown | Core/breadth surfaces repeatedly contribute non-zero `treatment_unique_count`; current persisted `recent_item_count` is invalid for this purpose, so any S2 cohort must use v2 freshness | Negative controls are explicitly role-separated; commercial control repeatedly exposes commercial noise while core/breadth rows have no explicit noise flags in current observations | Not yet measured | **S2_READY_FOR_REVIEW on v2-fresh non-control incrementals / S2 NOT STARTED** |
| Caixin | 1 | 1 | Not established | **Material conflict**: 72 core rows carry persisted date-only values around Aug 1–2 while first-party URL paths encode later dates. v2 correctly marks conflict instead of stale | Not yet reliable | Promotion control cleanly exposes commercial noise; core route measurement is contaminated | Not yet measured | **NOT S2-READY / ACCUMULATE + MEASUREMENT-BLOCKED** |
| EEO | 1 | 1 | Not established | Mixed but interpretable under v2: compact `/YYYY/MMDD/` paths expose current items; legacy RSS paths expose genuine 2011 staleness | Not established | First exposure technically weak: request failures, date-unknown rows and an empty/parse problem; current RSS evidence contains large genuinely stale blocks | Not yet measured | **NOT S2-READY / ACCUMULATE + TECHNICAL-HEALTH UNCERTAIN** |

## Evidence maturity rules

The matrix deliberately separates five questions:

1. **Execution repeatability** — when the source is naturally selected, does metadata-only Treatment execute and persist cleanly on independent intended dates?
2. **Timestamp measurability** — can freshness be interpreted without relying on known-bad timestamp association?
3. **Incremental coverage** — does the route repeatedly expose article identity that Control did not expose?
4. **Noise / displacement risk** — what share of incremental supply is commercial, micro-market, stale, non-article or otherwise low-value?
5. **Fixed-budget value** — under the unchanged 32-body-attempt ceiling, would the route rescue useful articles without displacing better Control candidates?

A source does **not** advance merely because its raw exposure count increases.

The frozen acceptance contract's `S2-ready` vocabulary is narrower than product approval: route identity and freshness must be interpretable, and incremental metadata supply must be repeatable enough to justify a lightweight product-scope / eligibility audit. It does **not** mean body acquisition, fixed-32 displacement, production route adoption or promotion has passed.

## Current source-level decisions

### Jiemian-depth — S2_READY_FOR_REVIEW

Execution repeatability is established across two independent intended dates. All four active surfaces have repeated non-zero Treatment-unique metadata supply and zero explicit noise in the current observation ledger. Timestamp evidence is fully interpretable under v2.

`jiemian_medicine` repeatedly exposes the known clean miss `首个国产基因疗法的商业困局：打五折仍零处方`; the item appears in all four eligible exposures and has `control_overlap=FALSE` in all four. This is strong route-capability evidence that the previous Jiemian scope omitted a meaningful medicine/commercialization surface.

Boundary: S1 activated after the article was originally published, so this is not retrospective proof that the original 2026-08-25 report cutoff would have been met. It is route-capability evidence, not timely-recall counterfactual proof.

Under the frozen S1 contract, Jiemian now satisfies the descriptive source-level definition `S2-ready`: it may be proposed for lightweight product-scope / eligibility auditing. **No S2 execution is started by this classification.**

### Yicai — S2_READY_FOR_REVIEW with v2-only freshness

Execution repeatability is established. The live persisted timestamp association remains unsuitable for utility interpretation: across the current four-exposure ledger, 167 Yicai item rows carry explicit `N分钟前/N小时前` evidence and 136 rows carry `昨天 HH:MM` evidence, while the live parser leaves most unbound and repeatedly binds a small number incorrectly.

Timestamp Measurement v2 changes the decision boundary without changing live telemetry: source-level replay gives 297 fresh / 6 conflict / 125 unknown. Meanwhile the core/breadth surfaces repeatedly show non-zero Treatment-unique supply in every eligible exposure. Explicit negative controls are already separated by `surface_role`; the commercial control repeatedly identifies commercial content rather than silently contaminating core editorial supply.

Therefore Yicai is no longer `measurement-blocked` for the *question of whether a lightweight S2 audit is justified*. It is `S2_READY_FOR_REVIEW` **only for v2-fresh, non-control, Control-incremental metadata rows**. Conflict/unknown/stale/boundary rows and noise-control surfaces must not enter that future S2 cohort. Current persisted `within_freshness` remains invalid for this decision.

### Caixin — NOT S2-ready

One eligible exposure is insufficient for repeatability. More importantly, the first exposure cannot be described as simply `stale_surface`: 72 core rows have persisted date-only evidence that conflicts with their first-party URL-path date. The correct current classification is timestamp-evidence conflict. Route quality remains unresolved.

### EEO — NOT S2-ready

One eligible exposure is insufficient for repeatability. The first exposure already distinguishes two route families: current compact-date article paths on `technology_plus`, versus finance/industry RSS rows whose URL paths are genuinely from 2011. This is useful technical diagnosis, but not enough to change the route portfolio.

## Portfolio-level decision

**Portfolio-wide S1 remains INCOMPLETE; source-specific S2 readiness is split.**

- Jiemian-depth: `S2_READY_FOR_REVIEW / S2 NOT STARTED`.
- Yicai: `S2_READY_FOR_REVIEW on v2-fresh non-control incrementals / S2 NOT STARTED`.
- Caixin: `NOT S2-READY`.
- EEO: `NOT S2-READY`.

What is now established:
- Day-0 evidence validity passed;
- Yicai and Jiemian execution-layer cross-intended-date repeatability is established;
- Timestamp Measurement v2 provides an explicit fail-closed interpretation layer without rewriting live telemetry;
- Jiemian has repeated structural incremental-coverage evidence;
- Yicai has repeated non-control incremental metadata supply and sufficient v2 measurement coverage to justify a bounded eligibility review.

What remains open:
- Caixin and EEO need later independent intended-date exposures;
- no S2 audit has been executed or authorized;
- fixed-32 displacement/value replay has not yet been performed;
- no source has production admission, body-budget entitlement or promotion from this matrix.

## Frozen boundaries

No change to Control, live Treatment parser, route portfolio, source registry, source/host caps, 32-body budget, Acquisition, L4/L5/L6, article_cache production consumption, 07:35 Editor, `v06_primary`, or auto-promotion.

Scheduler reliability design is explicitly **deferred by user decision** at this checkpoint. Continue observing natural scheduling behavior; do not design or implement a scheduler replacement in this work package.
