# Phase 3 — Jiemian-only S3 fixed-32 counterfactual contract v1

Date: 2026-08-30 BJT  
Status: **AUTHORIZED / OFFLINE FIRST / PRODUCTION UNCHANGED**  
Scope: **Jiemian-depth only**  
Contract version: `zh-route-shadow-s3-jiemian-fixed32-v1`

## 1. Question

S2-B v2.1 established that the frozen Jiemian metadata-plausible sample contains body-confirmed Standard Longreads: 15/15 primary plausible items were evaluable and 15/15 were confirmed, spanning consumer, health-face and medicine surfaces.

S3 asks a different question:

> If qualified Jiemian Treatment incrementals had competed inside the same historical Collector selection mechanism, with the same source/host caps and the same maximum 32 body-attempt slots, would they actually enter the bounded portfolio, and what Control supply would they displace?

S3 is **not** extra capacity for Jiemian. It is a fixed-budget counterfactual.

## 2. Frozen primary cohort

To avoid post-outcome sample-window expansion, the primary S3 cohort inherits the exact S2-A/S2-B frozen evidence window:

1. `COL-20260827-224813-BJT-zh_midday`
2. `COL-20260828-040117-BJT-zh_evening`
3. `COL-20260828-234148-BJT-zh_midday`
4. `COL-20260829-050025-BJT-zh_evening`

The only Treatment identities eligible for the primary counterfactual are the exact **28 Jiemian-depth `plausible_standard_longread` canonical identities** frozen in `S2A_zero_new_body_audit_20260829`.

Later natural Jiemian exposures, including `COL-20260829-182701-BJT-zh_midday` and `COL-20260829-224251-BJT-zh_evening`, are external repeatability evidence only. They may not enter the primary S3 denominator.

## 3. Per-run Treatment eligibility

A frozen plausible identity may enter a particular run only when that run itself contains a Jiemian Route item that is:

- `source_id=jiemian-depth`;
- on a non-noise-control surface;
- same-run `control_overlap=FALSE`;
- Timestamp Measurement v2 `fresh` for that exact row/run;
- canonical-identical to one of the frozen 28 plausible identities.

Freshness or eligibility observed in another run may not be borrowed across runs.

Canonical duplicates across multiple Jiemian surfaces in one run collapse to one candidate while retaining all route provenance. The frozen S2-A `first_surface` is preferred when present in that run; otherwise the deterministic lowest `(surface_id, item_ordinal, url)` representative is used.

## 4. Runtime semantics to replay

The structural counterfactual must preserve the historical selection semantics:

- prefilter: `page-freshness-prefilter-v0.5.6m`;
- ranking: `editorial-resolved-ranking-v0.5.6g4`;
- profile adjustment: `narrative-profile-priority-v0.5.6g`;
- initial editorial threshold: **49**;
- selection allocator: `quality-portfolio-reserve-v0.5.6g`;
- native source cap: **4**;
- absolute host cap: **4**;
- first-stage capacity: **24**;
- staged reserve: `staged-reserve-v0.5.6m`;
- maximum article attempts: **32**.

Treatment does not receive an extra quota, reserved source slot, host-cap exception or body-attempt budget.

## 5. Treatment metadata boundary

The persisted Route item ledger contains URL/title/timestamp/surface provenance but no article description. Therefore Treatment candidates must be ranked using only metadata that actually existed in the Route ledger.

Specifically:

- no web/body fetch to enrich description before selection;
- no post-hoc snippet or article-body text injected into ranking;
- `description=""` for Treatment replay candidates;
- listing `published_at` is retained only as persisted; Timestamp Measurement v2 eligibility does not silently rewrite the production freshness scorer;
- Route provenance is retained in `metadata` for audit.

This deliberately tests the real information boundary of the proposed Route admission.

## 6. S3-A — structural fixed-32 replay

S3-A is zero-new-body / zero-new-network.

### 6.1 Control self-replay gate

Before Treatment is added, every frozen run must reproduce its historical Control extraction schedule.

The replay must:

1. reconstruct Control discoveries from `collector_discovery_snapshot`;
2. rerun the frozen prefilter/ranking/threshold/selection semantics;
3. split the first stage with the frozen 24-slot contract;
4. inject the persisted historical extraction/classification terminal status for replayed first-stage Control URLs;
5. run `staged-reserve-v0.5.6m` for stage two;
6. compare the canonical attempt identity and `actual_extraction_order` with the persisted historical snapshot.

If any run mismatches, the primary S3 result is:

`NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH`

Treatment effects may not be interpreted on a simulator that fails this gate.

### 6.2 Treatment first-stage uncertainty

A Treatment URL has a known first-stage usability outcome only when immutable pre-S3 body evidence exists for that same canonical identity.

For the current frozen evidence chain, S2-B v2.1 reviewed labels may be used but may not be changed after S3 selection is observed.

If an unreviewed Treatment identity enters first stage, S3-A must not assume it is usable. The engine reports two explicit bounds:

- `unknown_treatment_usable`;
- `unknown_treatment_failed`.

If the two bounds differ in downstream final-attempt identity, exact final structural effect is marked:

`STRUCTURAL_EFFECT_NEEDS_EVIDENCE`

and the engine emits a minimal deterministic evidence-completion manifest containing only the blocking Treatment first-stage identities. No replacement or attractive-title substitution is allowed.

If no Treatment identity enters selection, use `STRUCTURAL_NO_EFFECT`.

If structural entry occurs and all first-stage Treatment outcomes needed for stage-two scheduling are already known, use `STRUCTURAL_EFFECT_BODY_EVIDENCE_COMPLETE`.

## 7. S3-B — utility overlay

S3-B is downstream of a valid S3-A structural replay.

First use already-persisted evidence only. The utility audit must distinguish:

1. **historical system outcome** — extraction/eligibility/disposition already persisted for Control;
2. **human Standard Longread outcome** — frozen body-review rubric used in S2-B;
3. **unknown** — never imputed from title, metadata class or source reputation.

If a utility-relevant Treatment entrant or displaced Control identity lacks comparable body evidence, create a pre-frozen minimal evidence-completion manifest before any new body request. New body/network work, if needed, must be a separate bounded version and must not rewrite S2-B v2.1.

## 8. S3 decision vocabulary

S3 may prepare, but does not authorize, a later Shadow-selection phase.

### `SUPPORTS_S4_SHADOW_SELECTION_REVIEW`

Requires all of:

- Control self-replay PASS for all four frozen runs;
- Treatment final-attempt entry on at least two distinct intended schedule dates;
- utility-relevant Treatment entrants and displaced Control outcomes sufficiently observed that remaining unknowns cannot flip the sign of the aggregate comparison;
- aggregate body-confirmed Standard Longread delta is positive;
- source/host caps and the 32-attempt maximum remain satisfied.

### `NO_CLEAR_FIXED32_GAIN`

Use when the evidence is sufficiently complete and the aggregate net utility is zero/mixed without a stable positive direction.

### `DOES_NOT_SUPPORT_S4`

Use when sufficiently complete evidence shows a negative fixed-32 utility delta.

### `NOT_EVALUABLE`

Use when Control replay fails or utility evidence is too incomplete for the sign of the result to be determined.

No S4/Production change follows automatically from any S3 state.

## 9. Explicit non-goals / frozen boundaries

This authorization does **not** change:

- natural Collector routes or source registry;
- source cap / host cap / 32-body budget;
- Production `article_cache` consumption;
- 07:35 Editor wiring;
- `V06_PRIMARY_ENABLED`;
- automatic promotion;
- Yicai S2-B denominator;
- Track F production-acquisition feasibility;
- Scheduler design or triggers.

Production remains **SHADOW / NOT_READY**.
