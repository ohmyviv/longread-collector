# Phase 3 — Chinese Route S1 cumulative decision matrix

Date: 2026-08-29 BJT

Status: EVIDENCE LEDGER / SHADOW ONLY / NO PRODUCTION DECISION

## Purpose

Replace raw-run counting with a source-level evidence maturity ledger. A new natural run matters only when it changes one or more source-level evidence cells. This matrix does not authorize S2, route promotion, source/cap/budget changes, Editor wiring, or production consumption.

## Current eligible-exposure ledger

| Source | Eligible exposures | Independent intended dates | Execution repeatability | Timestamp measurement | Incremental coverage evidence | Technical/noise evidence | Fixed-32 value evidence | Current state |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| Jiemian-depth | 4 | 2 (2026-08-27, 2026-08-28) | **Established across intended dates** | Strongest of current S1 sources; all 292 persisted item rows have exact/high listing evidence; v2 replay separates 180 fresh / 112 stale | **Strong structural signal**: `jiemian_medicine` recovered the known gene-therapy clean miss in 4/4 eligible exposures with Control overlap FALSE in 4/4 | Requests/parsing stable in all four exposures; no comparable commercial-control concentration observed | Not yet measured | **PROMISING / eligible for later fixed-32 utility replay after measurement contract closure** |
| Yicai | 4 | 2 (2026-08-27, 2026-08-28) | **Established across intended dates** | Current persisted parser is systemically contaminated. v2 exposes large card-local time evidence plus explicit conflicts rather than treating most rows as date-unknown | Not safely quantifiable from current persisted `proven_recent` counts | Noise controls work directionally; commercial control remains commercial; core/news surfaces repeatedly return substantial metadata | Not yet measured | **MEASUREMENT-BLOCKED for utility; execution layer repeatable** |
| Caixin | 1 | 1 | Not established | **Material conflict**: 72 core rows carry persisted date-only values around Aug 1–2 while first-party URL paths encode later dates. v2 correctly marks conflict instead of stale | Not yet reliable | Promotion control cleanly exposes commercial noise; core route measurement is contaminated | Not yet measured | **ACCUMULATE + MEASUREMENT-BLOCKED** |
| EEO | 1 | 1 | Not established | Mixed but interpretable under v2: compact `/YYYY/MMDD/` paths expose current items; legacy RSS paths expose genuine 2011 staleness | Not established | First exposure technically weak: request failures, date-unknown rows and an empty/parse problem; current RSS evidence contains large genuinely stale blocks | Not yet measured | **ACCUMULATE / TECHNICAL-HEALTH UNCERTAIN** |

## Evidence maturity rules

The matrix deliberately separates five questions:

1. **Execution repeatability** — when the source is naturally selected, does metadata-only Treatment execute and persist cleanly on independent intended dates?
2. **Timestamp measurability** — can freshness be interpreted without relying on known-bad timestamp association?
3. **Incremental coverage** — does the route repeatedly expose article identity that Control did not expose?
4. **Noise / displacement risk** — what share of incremental supply is commercial, micro-market, stale, non-article or otherwise low-value?
5. **Fixed-budget value** — under the unchanged 32-body-attempt ceiling, would the route rescue useful articles without displacing better Control candidates?

A source does **not** advance merely because its raw exposure count increases.

## Current source-level decisions

### Jiemian-depth

Execution repeatability is now established across two independent intended dates. `jiemian_medicine` repeatedly exposes the known clean miss `首个国产基因疗法的商业困局：打五折仍零处方`; the item appears in all four eligible exposures and has `control_overlap=FALSE` in all four. This is strong route-capability evidence that the previous Jiemian scope omitted a meaningful medicine/commercialization surface.

Boundary: S1 activated after the article was originally published, so this is not retrospective proof that the original 2026-08-25 report cutoff would have been met. It is route-capability evidence, not timely-recall counterfactual proof.

### Yicai

Execution repeatability is established, but utility interpretation remains blocked by timestamp measurement. Across the current four-exposure ledger, 167 Yicai item rows carry explicit `N分钟前/N小时前` evidence and 136 rows carry `昨天 HH:MM` evidence. The live parser leaves most of these unbound and has repeatedly attached a small number to clearly incompatible persisted timestamps. Utility claims based on current persisted `within_freshness` are therefore invalid.

### Caixin

One eligible exposure is insufficient for repeatability. More importantly, the first exposure cannot be described as simply `stale_surface`: 72 core rows have persisted date-only evidence that conflicts with their first-party URL-path date. The correct current classification is timestamp-evidence conflict. Route quality remains unresolved.

### EEO

One eligible exposure is insufficient for repeatability. The first exposure already distinguishes two route families: current compact-date article paths on `technology_plus`, versus finance/industry RSS rows whose URL paths are genuinely from 2011. This is useful technical diagnosis, but not enough to change the route portfolio.

## Overall S1 decision

**S1 overall: NOT_READY for S2 admission.**

What is now established:
- Day-0 evidence validity passed;
- Yicai and Jiemian execution-layer cross-intended-date repeatability is established;
- Jiemian medicine has repeated structural incremental-coverage evidence;
- current timestamp association is a systemic measurement defect, especially for Yicai/Caixin.

What remains open:
- Caixin and EEO need later independent intended-date exposures;
- timestamp measurement must be made interpretable before source utility is compared;
- fixed-32 displacement/value replay has not yet been performed;
- no source has S2 admission merely from the current matrix.

## Frozen boundaries

No change to Control, live Treatment parser, route portfolio, source registry, source/host caps, 32-body budget, Acquisition, L4/L5/L6, article_cache production consumption, 07:35 Editor, `v06_primary`, or auto-promotion.

Scheduler reliability design is explicitly **deferred by user decision** at this checkpoint. Continue observing natural scheduling behavior; do not design or implement a scheduler replacement in this work package.
