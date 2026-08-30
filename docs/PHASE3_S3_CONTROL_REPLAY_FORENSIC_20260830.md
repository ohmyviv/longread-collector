# Phase 3 — S3 Control replay mismatch forensic

Date: 2026-08-30 BJT  
Status: **ROOT CAUSE CONFIRMED / S3 v1 RESULT IMMUTABLE**

## 1. Scope

This forensic explains the single Control self-replay mismatch observed by the authorized Jiemian-only S3 fixed-32 v1 read-only run `33262599781`.

No Discovery, body request, network acquisition, Sheet write, Production mutation, Editor wiring, source/cap change, Scheduler change, or Treatment interpretation is performed here.

## 2. Frozen v1 result

S3 v1 returned:

`NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH`

Control-only exact replay results:

- `COL-20260827-224813-BJT-zh_midday`: PASS, 24/24 exact attempts;
- `COL-20260828-040117-BJT-zh_evening`: FAIL, 32/32 count but first identity mismatch at attempt 21;
- `COL-20260828-234148-BJT-zh_midday`: PASS, 25/25 exact attempts;
- `COL-20260829-050025-BJT-zh_evening`: PASS, 32/32 exact attempts.

The v1 artifact digest remains immutable: `sha256:9b122f8e0f5b7bb996e4c7f2e58f020ba3298a7c73e48ea245178007d573cb8f`.

## 3. Exact mismatch

Historical attempt 21 for the failing run was:

`https://theinitium.com/journal`

The persisted discovery row shows:

- raw discovery URL: `https://theinitium.com/journal/`;
- canonical identity: `https://theinitium.com/journal`;
- source: `initium`;
- discovery method: `sitemap`;
- title: empty;
- sitemap lastmod persisted in the snapshot `published_at` column: `2026-08-26T12:32:25.000Z`;
- historical freshness track: `special_document`;
- historical `freshness_score_penalty=-2`;
- historical editorial priority: `47`;
- historical global reserve rank: `18`;
- historical second-stage eligible: `TRUE`;
- historical phase: `editorial_reserve_promotion_v056m`;
- historical `actual_extraction_order=21`.

The v1 replay omitted that identity, shifted the following reserve promotions up by one position, and filled attempt 32 with `https://nfcmag.com/article/9467.html`.

## 4. Root cause

The failure is caused by **raw-URL semantic loss during offline Control reconstruction**.

`offline_replay_v056._snapshot_item()` reconstructs the `DiscoveredURL.url` as:

`url_canonical or url`

The S3 v1 normalizer therefore supplied `https://theinitium.com/journal` rather than the runtime discovery URL `https://theinitium.com/journal/`.

The frozen v0.5.6f freshness policy classifies special documents using a path expression containing:

`/(?:doi|journals?|papers?|...)/`

Consequently:

- raw path `/journal/` matches the frozen `journals?` special-document path rule;
- canonical path `/journal` does not match because the trailing `/` required by that rule is absent.

With the raw URL, the historical candidate correctly enters the independent `special_document` freshness track. With the canonical URL, the reconstructed candidate has an empty title and a short one-segment `/journal` path, so it lacks ordinary article structure and falls into `freshness_unknown_insufficient_evidence`.

This explains the exact attempt-21 divergence and the downstream one-position shift.

## 5. Classification

Root cause class:

`OFFLINE_REPLAY_RECONSTRUCTION_BUG / RAW_URL_SEMANTICS_LOST_TO_CANONICAL_IDENTITY`

This is **not** evidence of:

- Production selection drift;
- historical runtime nondeterminism;
- a changed source/host cap;
- Jiemian Treatment value;
- a need to weaken the freshness policy;
- a reason to rewrite the v1 result.

## 6. Corrective principle for v1.1

Selection policy must operate on the same URL representation available to the historical runtime.

Therefore S3 v1.1 must:

1. reconstruct Control `DiscoveredURL.url` from the persisted raw `url` column when present;
2. use canonicalized URL only for identity, deduplication, comparison and foreign-key style matching;
3. leave all frozen prefilter, ranking, source cap, host cap, initial threshold and staged-reserve semantics unchanged;
4. leave the four-run cohort and 28-item Jiemian Treatment universe unchanged;
5. rerun Control-only replay first;
6. require 4/4 exact historical attempt identity/order before any Treatment result is interpreted.

The v1 artifact and `NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH` state remain part of the permanent audit trail; v1.1 is a new replay version, not a replacement of history.

## 7. Broader design implication

Canonical URL is an identity primitive, not always a semantics-preserving substitute for the runtime request/discovery URL. Future replay fingerprints should persist and distinguish both:

- `raw_runtime_url` — used by page/freshness/route semantics when those semantics inspect path form;
- `canonical_identity_url` — used for deduplication, joins and identity comparison.

This distinction should be incorporated into future replay-observability design before any live telemetry schema change is considered.
