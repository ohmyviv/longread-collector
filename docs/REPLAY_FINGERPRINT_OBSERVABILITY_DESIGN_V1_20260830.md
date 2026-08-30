# Replay Fingerprint & Counterfactual Observability Design v1

Date: 2026-08-30 BJT  
Status: **DESIGN ONLY / NO LIVE SCHEMA CHANGE AUTHORIZED**

## 1. Problem exposed by S3

The S3 v1 failure demonstrated a general replay principle: a canonical URL is an identity primitive but is not always a semantics-preserving substitute for the runtime discovery/request URL. The specific Initium `/journal/` case changed a frozen freshness classification when the trailing slash was lost during offline reconstruction.

Historical counterfactuals should therefore replay **persisted decision state**, not reconstruct more state than necessary from lossy outputs.

## 2. First-principles requirement

A durable run should contain enough immutable information to answer three different questions without ambiguity:

1. **What exactly entered the runtime?**
2. **What exact deterministic decision state did the runtime compute?**
3. **What happened after each extraction attempt?**

Identity normalization, semantic evaluation and terminal outcomes are different layers and must not be collapsed.

## 3. Proposed replay fingerprint layers

### L0 — execution identity

Persist or fingerprint:

- collector run id;
- intended schedule date/time and query group;
- runtime git SHA;
- semantic/runtime version bundle;
- Python/package lock fingerprint when relevant;
- active collector-config hash;
- query-config hash;
- source-registry hash;
- route-registry / route-portfolio version;
- environment contract version, excluding secrets.

### L1 — discovery identity

For every discovered item persist both:

- `raw_runtime_url` — exact URL presented to runtime page/freshness/route logic;
- `canonical_identity_url` — normalized identity used for dedupe/joins;
- `original_url` / redirect provenance if known;
- discovery method;
- query/source id;
- native route / endpoint;
- raw title, description and listing timestamp available **before extraction**;
- discovery ordinal/rank.

A replay must never substitute canonical identity for raw semantic input unless a policy explicitly declares that transformation semantics-preserving.

### L2 — deterministic policy outputs

Persist the exact result of each pre-extraction policy rather than only enough fields to recompute it:

- page-gate version, page type, evidence, rejection reason;
- freshness-policy version;
- resolved publication time and evidence hierarchy;
- freshness track / age / unknown-state / exception;
- ranking version;
- full score tuple and score components;
- profile adjustment;
- editorial priority;
- initial threshold and delta;
- selection bucket;
- selection group;
- source/domain rank;
- source cap and host cap state relevant at allocation time;
- global reserve rank;
- second-stage eligibility;
- capacity-recovery eligibility.

Recomputation remains useful for regression tests, but the persisted historical decision state is the authoritative counterfactual baseline.

### L3 — selection-plan fingerprint

For each run persist an immutable selection-plan object or hash covering:

- ordered first-stage identities;
- ordered deferred/reserve candidates;
- ordered reserve groups;
- max attempts;
- first-stage capacity;
- source cap / host cap;
- selection-plan version;
- per-item selected order / reserve rank;
- any force-reserve or recovery flags.

The complete plan should have a stable SHA-256 over a canonical JSON serialization.

### L4 — post-first-stage state

Because staged reserve depends on observed terminal outcomes, persist:

- actual extraction order;
- extraction status;
- usable-body state;
- candidate disposition;
- eligible-for-editor state;
- successful count by selection group after first stage;
- successful count by host after first stage;
- second-stage capacity remaining;
- exact second-stage input order;
- exact promotion / skip reason for each candidate.

This should allow a replay to prove whether divergence originates before or after acquisition outcomes.

### L5 — acquisition fingerprint

Persist separately from editorial classification:

- acquisition contract/version;
- exact requested URL;
- extractor/provider path;
- authentication mode (never secret value);
- attempt count;
- retry reason/status;
- final URL if redirect followed;
- terminal HTTP/transport state;
- content/body fingerprint;
- content character count;
- provider fallback use and explicit budget consumption.

Measurement-only acquisition and Production acquisition must have different version labels.

### L6 — product/classification fingerprint

Persist:

- classification version;
- verification level and provenance;
- content type;
- candidate disposition;
- reject reason;
- eligible-for-editor state;
- body/content fingerprint used by classification.

Human body-review labels remain a separate audit layer and must never overwrite machine output.

## 4. Recommended immutable run-level hashes

Future design should expose at least:

- `execution_contract_sha256` — L0 configuration/version identity;
- `discovery_input_sha256` — canonical serialization of pre-extraction discovery inputs including raw + canonical URL;
- `selection_plan_sha256` — L2/L3 ordered decision state;
- `attempt_schedule_sha256` — actual first+second-stage ordered identities;
- `terminal_outcome_sha256` — acquisition/classification terminal ledger.

A counterfactual can then state precisely which layers are frozen and which layer is modified.

## 5. Counterfactual design rule

The minimal-change principle should be explicit:

> Freeze every historical layer that is not the treatment variable. Recompute only the layer necessary to introduce the treatment, and validate any recomputed historical layer against its persisted fingerprint before interpreting treatment effects.

For route admission experiments, the Treatment variable is the addition of qualified Route candidates. Historical Control discovery identity and observed extraction outcomes should be frozen whenever possible.

## 6. Migration / compatibility design

No live schema mutation is authorized by this document.

If later implemented:

1. add new columns/JSON keys append-only;
2. do not rewrite old runs;
3. version the observability contract;
4. keep current `url` and `url_canonical` meanings stable;
5. backfill only derived run-level hashes where inputs are demonstrably complete;
6. mark historical runs `replay_fingerprint_partial` when required state was never persisted;
7. fail closed rather than invent missing historical state.

## 7. Acceptance tests for a future implementation

Before rollout, fixtures should prove at least:

- `/journal/` raw URL and `/journal` canonical identity remain distinguishable;
- canonical joins still dedupe those identities;
- a complete run fingerprint is stable across repeated serialization;
- changing any score component changes the selection-plan hash;
- changing first-stage terminal status changes second-stage/attempt-schedule hash;
- secrets are never included in fingerprints;
- measurement and Production acquisition versions cannot collide.

## 8. Current boundary

This is a Future Design artifact only. It does not authorize:

- new live Sheet columns;
- Production collector writes;
- runtime selection changes;
- source/cap changes;
- Editor changes;
- Scheduler changes.
