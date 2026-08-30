# Phase 3 — S4 Shadow-selection admission contract

Date: 2026-08-30 BJT  
Status: **PREREGISTERED DESIGN / S4 NOT AUTHORIZED**

## 1. Purpose

S4 is the first phase in which a route Treatment could participate in a real Collector **Shadow selection** rather than only offline counterfactual replay. This contract freezes the admission gate before S3 utility outcomes are complete so that a favorable result cannot lower the promotion threshold after the fact.

S4 is not Production and does not feed the 07:35 Editor.

## 2. Required evidence before S4 may even be reviewed

A source/route may receive `SUPPORTS_S4_SHADOW_SELECTION_REVIEW` only when all conditions below are true for its preregistered S3 cohort:

1. **Historical simulator validity** — Control-only replay reproduces exact historical attempt identity/order for every frozen run under the accepted replay version.
2. **Real fixed-budget entry** — qualified Treatment enters the same fixed max-32 portfolio on at least two distinct intended schedule dates; no extra quota or capacity is granted.
3. **Utility evidence completeness** — all Treatment and displaced-Control outcomes required to determine the aggregate comparison are observed, or any remaining unknowns are mathematically incapable of flipping the sign.
4. **Positive utility sign** — aggregate body-confirmed Standard Longread delta is strictly positive under the frozen comparison rule.
5. **Breadth, not one-off dependence** — positive effect is not explained by a single article identity or a single intended schedule date.
6. **Budget integrity** — max article attempts remains <=32 in every replay; source/host caps remain the historical frozen caps.
7. **Product-scope integrity** — academic journal assets and other known non-target classes remain excluded by the same product contract.
8. **Acquisition interpretation separation** — Route Body Value and Production Acquisition Feasibility are reported separately; measurement-only acquisition success may not be presented as production feasibility.
9. **No unresolved denominator drift** — frozen S1/S2/S3 denominators and identities remain auditable and are not retroactively expanded after outcomes are seen.
10. **No critical observability defect** — replay/telemetry gaps capable of changing the result are either resolved or explicitly bounded so they cannot flip the decision.

Failure of any required condition yields `S4_REVIEW_NOT_SUPPORTED` or `S4_REVIEW_NOT_EVALUABLE`, not an exception process.

## 3. S4 Shadow execution contract — future, separately authorized

If S4 is later explicitly authorized, its Treatment may participate only in an isolated Shadow selection path that:

- uses the natural run's actual Control discovery pool;
- applies the approved route candidates at the same metadata boundary proven in S3;
- preserves the live source cap, host cap and max-32 attempt budget;
- computes a Treatment selection plan without changing the Control plan used by Production/legacy Shadow behavior;
- records all Treatment entries and Control displacements;
- does not consume Production `article_cache` as an Editor input;
- does not modify the 07:35 Editor payload;
- does not change `V06_PRIMARY_ENABLED`, `AUTO_PROMOTE_WHEN_READY`, or `EDITOR_0735_CONNECTED`;
- does not silently reuse measurement-only paid/provider fallbacks as Production acquisition semantics.

Treatment failure must never degrade or suppress the Control run.

## 4. Prospective S4 evidence window

The S4 evidence window, if authorized, must be defined prospectively by **eligible natural exposures / intended dates**, not by stopping when a desired number of wins is observed.

At minimum the later authorization must freeze:

- start boundary;
- eligible run definition;
- intended-date counting rule;
- technical validity gate;
- minimum independent intended-date exposure count;
- treatment utility and harm metrics;
- stopping / abort conditions.

No manual rerun may be used solely to fabricate prospective evidence.

## 5. S4 outcome vocabulary

Possible future S4 states should remain narrow:

- `SHADOW_TECHNICALLY_VALID` — isolation and telemetry contracts hold, without claiming utility;
- `SHADOW_UTILITY_POSITIVE` — prospective evidence supports positive incremental utility under the frozen attention budget;
- `SHADOW_NO_CLEAR_GAIN` — technically valid but no stable positive incremental utility;
- `SHADOW_HARM_SIGNAL` — Treatment measurably worsens candidate utility or systematically displaces better Control supply;
- `SHADOW_NOT_EVALUABLE` — insufficient or corrupted prospective evidence.

None of these states is Production authorization.

## 6. Separate Production promotion gate

Even a future `SHADOW_UTILITY_POSITIVE` result must lead to a separate Production review. That later review must explicitly address at least:

- production acquisition reliability and cost;
- failure isolation;
- operational latency;
- source concentration / portfolio diversity;
- Editor compatibility;
- rollback semantics;
- observability completeness;
- Scheduler independence;
- final product/editorial review.

No automatic S4 -> Production transition exists.

## 7. Current state

At the time this contract is preregistered:

- S4 execution: **NOT AUTHORIZED**;
- Production: **SHADOW / NOT_READY**;
- Editor wiring: unchanged;
- Scheduler design: unchanged;
- source/host caps and max-32 budget: unchanged.
