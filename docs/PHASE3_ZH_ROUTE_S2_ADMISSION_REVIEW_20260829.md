# Phase 3 — Chinese Route source-specific S2 admission review

Date: 2026-08-29 BJT

Status: DECISION PREPARATION ONLY / S2 NOT STARTED / NO BODY REQUESTS

## Question

After S1 Day-0 acceptance, four eligible natural exposures, cross-intended-date repeatability for Yicai/Jiemian, and the fail-closed Timestamp Measurement v2 replay, which sources now satisfy the **frozen descriptive definition** of `S2-ready`?

Frozen contract definition:

> `S2-ready` means route identity and freshness are interpretable and incremental metadata supply is repeatable enough to justify lightweight product-scope / eligibility auditing.

It does **not** mean production adoption, fixed-32 success, body-acquisition entitlement, Editor wiring or promotion.

## Evidence reconciliation

### Jiemian-depth — S2_READY_FOR_REVIEW

Evidence:

- 4 eligible exposures across 2 independent intended dates;
- 4/4 active surfaces execute and persist consistently;
- 292/292 current frozen replay rows have exact/high listing timestamp evidence;
- v2 freshness: 180 fresh / 112 stale, no timestamp conflicts/unknowns in the frozen four-exposure set;
- every surface/exposure has non-zero `treatment_unique_count`;
- all 16 source-surface exposure rows have `noise_item_count=0`;
- `jiemian_medicine` exposes the known gene-therapy clean miss in 4/4 exposures with `control_overlap=FALSE` in 4/4.

Decision: route identity, freshness measurability, repeatability and non-zero incremental supply are all sufficiently established for the next *lightweight eligibility-review* question.

### Yicai — S2_READY_FOR_REVIEW with strict cohort restriction

Evidence:

- 4 eligible exposures across 2 independent intended dates;
- core/breadth surfaces repeatedly return non-zero Treatment-unique metadata;
- v2 replay converts the source-level timestamp picture from mostly `date_unknown` to 297 fresh / 6 conflict / 125 unknown;
- the 6 explicit conflicts remain fail-closed and are excluded;
- negative-control surfaces are role-separated; commercial-control noise is repeatedly visible rather than hidden inside core editorial rows.

Decision: the source is no longer measurement-blocked for deciding whether an S2 eligibility audit is warranted. Any future S2 cohort must be restricted to:

1. v2 `fresh` rows only;
2. non-`noise_control` surfaces only;
3. `control_overlap=FALSE` rows only;
4. canonical article identity deduped across exposures;
5. no `conflict`, `unknown`, `boundary_unknown` or `stale` rows.

### Caixin — NOT S2-ready

Evidence is insufficient and contradictory:

- only 1 eligible exposure;
- 72 core rows have explicit persisted date-only vs first-party URL calendar-date conflicts;
- no cross-intended-date repeatability.

Decision: continue natural accumulation; no S2 cohort yet.

### EEO — NOT S2-ready

Evidence:

- only 1 eligible exposure;
- first exposure has request/parse weakness;
- v2 distinguishes 9 current compact-date fresh items from 40 genuinely stale legacy-RSS items plus 7 unknowns;
- no cross-intended-date repeatability.

Decision: continue natural accumulation; no S2 cohort yet.

## What a later S2 should mean

If separately authorized, start with **S2-A: zero-new-body eligibility audit**, not body extraction.

S2-A would operate only on already-persisted metadata and derived v2 states. It would:

- build canonical unique Treatment-incremental cohorts for Jiemian and Yicai using the restrictions above;
- classify only what metadata can support at high confidence: plausible standard-longread article identity, obvious non-article/commercial/market-snapshot contamination, or `insufficient_evidence`;
- preserve source/surface provenance;
- report denominators by source and surface;
- never infer final editorial value from title alone;
- never write back to production tables or alter live S1 telemetry.

A later **S2-B body audit** would require separate authorization because it would introduce new Treatment-side body/network work. It is not part of this review.

## Relationship to S3

S3 remains the fixed-32 displacement counterfactual. It should not begin merely because a source is S2-ready.

The evidence order remains:

S1 source-specific readiness → authorized S2-A eligibility audit → only if useful incremental supply survives, consider a separately reviewed fixed-32 S3 counterfactual.

This avoids spending extraction budget on routes whose apparent incrementals are mostly non-article/noise and avoids using fixed-32 ranking to compensate for unresolved measurement defects.

## Current recommendation for user decision

When the user next reviews this track, the narrow decision is:

- whether to authorize **S2-A zero-new-body eligibility audit for Jiemian + Yicai only**.

No decision is needed for Caixin/EEO yet; continue natural exposure accumulation.

## Explicitly not authorized by this document

- no S2 execution;
- no body extraction / Firecrawl / new network request;
- no source registry, route, cap or budget change;
- no live timestamp-parser modification;
- no S3/fixed-32 execution;
- no 07:35 Editor/article_cache production wiring;
- no `v06_primary` or auto-promotion;
- no scheduler reliability design or scheduler change.
