# Collector Foundation Contracts v1

Date: 2026-08-30  
Status: **DESIGN CONTRACT / NON-PRODUCTION**  
Scope: Collector only. This document does not define the 07:35 Editor, user personalization, final daily recommendation portfolio, Scheduler replacement, or Production promotion.

## 1. First-principles mission

The Collector exists to convert a large, noisy public-web opportunity space into a smaller, auditable candidate-evidence layer under explicit resource constraints.

The optimization problem is therefore not `maximize URLs discovered` and not `maximize raw recall at any cost`.

Given:
- an intended cutoff;
- a bounded discovery/network budget;
- a hard body-attempt budget;
- bounded paid fallback;
- public-access-only constraints;

Collector should maximize the quantity and quality of **body-confirmed, product-scope, evidence-backed candidate articles made available to downstream editorial systems**, while preserving measurement integrity and operational durability.

### Non-goals
Collector does not decide:
- the user's final daily reading set;
- personal topic preference;
- final cross-topic reading-time allocation;
- the final recommendation order.

Collector may assess article form, freshness, substance, source relationship, acquisition sufficiency and expected acquisition value because those decisions are necessary to spend Collector resources intelligently.

## 2. Collector North Star and guardrails

The primary outcome family is **qualified yield under fixed resource budget**.

Recommended headline metric:

`body_confirmed_qualified_candidates / fixed_body_attempt_budget`

This is not yet a Production KPI and must not be optimized before measurement coverage is adequate.

Required guardrail families remain separate:
1. **Coverage** — important/reference articles discovered before the relevant cutoff;
2. **Value density** — share of acquired/evaluable items that are genuine target longreads;
3. **Marginal utility** — incremental qualified yield after a route/source competes inside the same fixed body budget;
4. **Acquisition economics** — usable/evaluable body yield per request and paid fallback;
5. **Measurement integrity** — frozen denominator, replay fidelity, provenance completeness;
6. **Operational reliability** — on-time creation, stage completion, durability and reconciliation.

Do not compress these into one weighted readiness score. A scalar can hide a fatal weakness on one axis.

## 3. CandidateEvidenceBundle contract

Collector's conceptual output unit is a `CandidateEvidenceBundle`, not a final recommendation.

A bundle should eventually expose five independent evidence groups:

### A. Identity evidence
- `canonical_identity_url`;
- `raw_runtime_url`;
- duplicate/cluster identity;
- hosting source;
- canonical/original publisher;
- source relationship.

### B. Discovery evidence
- source identity;
- route/surface identity;
- endpoint/query;
- observed rank/ordinal;
- observed timestamp;
- discovery method;
- overlap with other routes/control.

### C. Acquisition evidence
- transport URL actually requested;
- provider/extractor;
- attempt ordinal;
- HTTP/transport outcome;
- latency/cost/credits;
- body size/hash;
- body-usability verdict;
- fallback reason;
- terminal acquisition state.

### D. Canonical/editorial evidence
- page surface;
- content medium;
- editorial genre;
- publication-time evidence and confidence;
- body-confirmed target/non-target/borderline state;
- depth/substance evidence;
- promotional/template/transcript/primary-document risks.

### E. Policy evidence
- acquisition-gate decision and reason;
- selection score components;
- cap state;
- first/reserve stage;
- action emitted by Collector policy;
- exact version/config fingerprints used.

A downstream consumer must be able to distinguish `not observed`, `observed failure`, `unknown`, and `negative editorial judgment`.

## 4. Source × Route × Transport contract

These are separate entities and must not be collapsed into one domain string.

### Source Identity
Who is editorially responsible for the content.

Examples: Jiemian, Yicai, FT.

### Route / Surface
Where/how Collector discovers candidate identities.

Examples: a medicine section, consumer section, RSS feed, sitemap, curator page, archive page, open-web query.

A route is the appropriate unit for measuring incremental discovery yield and route-specific noise.

### Transport Profile
How a canonical identity is technically retrieved.

May include:
- canonical request host;
- alternative first-party transport host;
- direct HTML;
- Jina Reader;
- Firecrawl;
- source-specific public API where permitted.

The Yicai forensic establishes why this separation is necessary: canonical identity and healthy transport host may differ.

### Promotion rule
No `Source = good` shortcut. Evidence should be attached to the narrowest causal unit supported by data:
- source-level editorial prior;
- route-level discovery yield;
- transport-level acquisition health.

## 5. Multi-axis readiness matrix

A source/route capability and the Collector runtime must be evaluated on independent axes.

### V — Value readiness
- `V0 UNOBSERVED`
- `V1 ROUTE_TECHNICALLY_REPEATABLE`
- `V2 METADATA_FRESHNESS_VALIDATED`
- `V3 BODY_VALUE_CONFIRMED`
- `V4 FIXED_BUDGET_MARGINAL_UTILITY_POSITIVE`

### A — Acquisition readiness
- `A0 UNOBSERVED`
- `A1 MEASUREMENT_BODY_OBSERVABLE`
- `A2 TRANSPORT_PROVIDER_MECHANISM_UNDERSTOOD`
- `A3 PRODUCTION_EQUIVALENT_SHADOW_STABLE`
- `A4 PRIMARY_ACQUISITION_READY`

### M — Measurement integrity
- `M0 NON_REPLAYABLE_OR_DENOMINATOR_UNKNOWN`
- `M1 DENOMINATOR_AND_PROVENANCE_FROZEN`
- `M2 DETERMINISTIC_REPLAY_VALID`
- `M3 ARTIFACT_FINGERPRINT_READBACK_COMPLETE`

### O — Operational reliability
- `O0 UNSTABLE_OR_UNOBSERVED`
- `O1 STAGE_LEVEL_OBSERVABILITY`
- `O2 DURABILITY_IDEMPOTENCY_RECONCILED`
- `O3 INTENDED_CUTOFF_RELIABILITY_ACCEPTED`

Production readiness is a conjunction of the required V/A/M/O levels. Strong V evidence cannot compensate for weak A/O evidence.

S1/S2/S3 labels remain valid historical experiment names; they are not the long-term global maturity model.

## 6. Run-state and partial-durability contract

A Collector run is a state machine, not a single success boolean.

Minimum conceptual stages:
1. `run_intent_created`
2. `preflight_complete`
3. `discovery_complete`
4. `snapshot_append_attempted`
5. `snapshot_appended`
6. `snapshot_verified`
7. `acquisition_complete`
8. `article_cache_persisted`
9. `extraction_log_persisted`
10. `run_finalized`

Every stage should be able to represent at least:
- `not_started`;
- `in_progress`;
- `completed_unverified`;
- `completed_verified`;
- `failed_before_side_effect`;
- `failed_after_possible_side_effect`.

Critical invariant:

> Failure to verify an append must never be serialized as observed zero persistence.

The 2026-08-30 Sheets 429 run is the reference failure: snapshot and article-cache writes occurred even though subsequent readback/log persistence failed.

Retries cannot substitute for truthful state modeling.

## 7. Replay Fingerprint contract

For every natural run, future observability should make exact historical decisions reconstructable without guessing runtime state.

Persist or derive stable fingerprints for:
- git/runtime semantic version;
- effective config;
- query configuration;
- source/route registry;
- `raw_runtime_url` and `canonical_identity_url` separately;
- freshness evidence;
- score components;
- bucket/group/cap state;
- first-stage position;
- first-stage terminal result;
- second-stage input/order/promotion reason;
- acquisition attempts;
- classification/judge version.

Counterfactual invariant:

> Freeze every historical layer that is not the treatment variable. Recompute only the layer necessary to introduce the treatment.

Canonicalization is an identity operation and must not silently replace a runtime value used by path-sensitive policy.

## 8. Collector Evidence Registry schema

The Canonical Handoff is a state/navigation document, not the raw experiment database.

A future lightweight Evidence Registry should maintain one row per versioned evidence object with at least:
- `evidence_id`;
- `question`;
- `evidence_type` (natural, replay, forensic, experiment, regression);
- `frozen_cohort_or_manifest`;
- `manifest_hash`;
- `semantic_baseline_sha`;
- `execution_sha`;
- `actions_run_id`;
- `artifact_id_or_uri`;
- `artifact_digest`;
- `denominator`;
- `decision_state`;
- `readiness_axis_effect`;
- `supersedes` / `superseded_by`;
- `production_effect`;
- `authorization_boundary`;
- `created_at`.

Handoff should point to this registry and summarize current decision state; it should not duplicate every row-level observation.

## 9. Source/route portfolio inventory contract

Before new sources are admitted to the live registry, maintain an isolated Future Source Inventory.

Minimum fields:
- source identity and language;
- original / curator / aggregator role;
- candidate discovery route(s);
- update cadence;
- longread density estimate;
- likely unique discovery contribution;
- overlap with existing Collector;
- RSS/sitemap/API availability;
- timestamp observability;
- public body accessibility;
- paywall/access constraints;
- transport/provider feasibility;
- expected Collector role.

Suggested roles:
- `core_editorial`;
- `breadth_safety`;
- `vertical_specialist`;
- `longread_curator`;
- `discovery_only`;
- `timestamp_enrichment`;
- `noise_control`.

Curators/aggregators may be discovery intelligence surfaces without becoming canonical editorial sources.

Admission sequence should be:
`inventory -> isolated route test -> metadata-only shadow -> timestamp/overlap measurement -> body value -> fixed-budget counterfactual -> reviewed promotion decision`.

## 10. Fixed body budget as scarce capital

The 32-attempt ceiling is an experimental and operational constraint, not a target to relax when a new route looks promising.

Collector selection should eventually estimate expected qualified yield and information gain using evidence such as:
- route/source prior;
- freshness confidence;
- probability of successful acquisition;
- metadata depth signals;
- uncertainty/exploration value;
- request/paid cost.

No model is authorized by this contract. First accumulate calibrated evidence.

The v0.6 `24 + 4 + 4` concept remains a valid shadow hypothesis:
- exploitation;
- adaptive recovery;
- stratified exploration.

It must be compared against legacy `24 + 8` on shared evidence under the same max-32 constraint.

## 11. Engineering namespace governance

Audit/replay/experiment code is evidence infrastructure and should not become indistinguishable from active runtime code.

Long-term desired namespace separation:
- active runtime;
- v0.6 shadow runtime;
- reusable audit/replay;
- versioned experiments/forensics;
- frozen legacy compatibility.

Do not perform a mass move now. Any future directory migration must be mechanical, tested and behavior-neutral.

One-shot network workflows must continue to be branch-only and removed before merge.

## 12. First implementation sequence

### P0 — close current evidence chains
- S3-B exact four-item evidence completion;
- Sheets #159 remediation design;
- passive Scheduler evidence;
- authenticated Jina Track F kept separate;
- #53 body-usability regression design;
- #40 source-relationship regression design.

### P1 — foundation contracts
This document completes the design-level P1 vocabulary. Runtime schemas are not changed by it.

### P2 — reliability foundation
Before source expansion:
- reduce structural Sheets reads;
- make partial durability truthful;
- add run-scoped immutable config/registry snapshots;
- improve replay fingerprints;
- validate by natural scheduled evidence.

### P3 — source/route portfolio
Build the isolated source inventory and promote only gap-filling routes through the evidence ladder.

### P4 — acquisition platform
Body usability, transport normalization, provider health and production-equivalent acquisition evidence.

### P5 — fixed-budget selection economics
Compare candidate allocation policies on shared evidence with max-32 fixed.

### P6 — Collector-primary review
Only after required V/A/M/O thresholds are pre-registered and satisfied.

Collector-primary does **not** imply Editor connection.

## 13. Explicit invariants

This design does not authorize:
- v0.7;
- Production source/route changes;
- Yicai host normalization in Production;
- increased max-32 or Firecrawl budget;
- database migration;
- Scheduler replacement;
- v06 primary;
- automatic promotion;
- 07:35 Editor connection;
- user preference logic inside Collector.

Current Production posture remains **SHADOW / NOT_READY**.
