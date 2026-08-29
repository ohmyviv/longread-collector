# Phase 3 Chinese Route — S2-B v2 Acquisition Observability Decision Package

## Decision status

**DESIGN COMPLETE / EXECUTION NOT AUTHORIZED**

This document is a decision package, not an execution approval. It introduces no article-body request, no provider probe, no Firecrawl call, no live Sheet write, no natural Collector mutation, no Editor wiring and no production change.

Current upstream state remains:

- S2-B v1 = `CLOSED / NOT_EVALUABLE_FOR_SOURCE_UTILITY / ACQUISITION-CENSORED`;
- S3 = `NOT_AUTHORIZED / NOT_STARTED`;
- Production = `SHADOW / NOT_READY`;
- semantic/runtime baseline for the frozen v1 production-acquisition comparator = `a380c68920c1de26f1e703b721d7eb2195900002`;
- v1 manifest SHA-256 = `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`;
- Jina/provider observability blocker is tracked separately in Issue #148.

## 1. Why v1 cannot simply be rerun

S2-B v1 attempted a deterministic 40-item panel once under the pre-frozen legacy Control chain:

`Jina Reader -> budgeted Firecrawl fallback (global cap=3)`

Observed outcome:

- 40 article-attempt slots;
- 43 actual HTTP requests;
- 40/40 Jina requests returned `HTTP 402 Payment Required`;
- 3 Firecrawl calls were sent and all three produced usable bodies;
- 37 rows were acquisition-censored;
- the three observable bodies were all body-confirmed Standard Longreads.

The correct v1 conclusion is therefore NOT_EVALUABLE, not a low source pass rate and not a 100% precision estimate.

A second run using a different provider state or a larger fallback budget would be a **different acquisition experiment**. Quietly pooling it with v1 would erase the causal meaning of the 37 censored rows. Therefore any continuation must be versioned and must preserve v1 as immutable evidence.

## 2. First-principles correction: separate two questions

The original S2-B goal contained two different questions that v1 allowed one acquisition mechanism to couple.

### Question V — Route Body Value

> Conditional on being able to observe the article body, do the frozen Route incrementals survive into body-confirmed Standard Longreads at a density sufficient to justify a fixed-32 utility counterfactual?

This is a **content-value measurement** question. The observation path should maximize faithful body observability within a pre-frozen diagnostic budget. It must not be presented as evidence that the production acquisition chain can obtain the same bodies.

### Question F — Production Acquisition Feasibility

> Under the frozen/live production acquisition semantics and real fallback constraints, can those candidate bodies actually be acquired reliably enough to support a production path?

This is an **operational feasibility** question. Its answer must preserve the real provider, retry and fallback-budget constraints. A measurement-only rescue path cannot make this gate pass.

The two tracks may use the same frozen panel for comparability, but their denominators, acquisition versions, outputs and decisions must remain separate.

## 3. Sampling decision: reuse the already-randomized frozen 40-item panel

### Recommendation

For a future v2 **Route Body Value** experiment, reuse the exact v1 40-item panel rather than draw a new sample.

Rationale:

1. the 40 rows were selected deterministically from the frozen 129-item S2-A universe before any body outcome was observed;
2. 37 rows are missing because of an acquisition-provider censoring event, not because of body-quality-based selection;
3. redrawing after observing the first three bodies would introduce avoidable post-outcome sample drift;
4. keeping the exact panel makes v1/v2 differences attributable to the observation/acquisition version rather than sample composition.

Hard rules:

- manifest SHA remains `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`;
- no replacement;
- no new S1 rows enter the panel;
- no known miss or attractive title is forced in;
- v1 acquisition/body rows remain immutable;
- v2 creates new result rows under a new acquisition/measurement version;
- v1 and v2 numerators/denominators are never silently pooled.

If a future decision instead asks for a new forward-looking source-precision estimate, that would require a separately frozen new sample. It is not the purpose of v2 described here.

## 4. Provider-readiness gate before sample requests

The v1 failure mode should not be rediscovered by spending 40 sample requests.

A future execution must define and run a **provider-readiness gate before the first panel-body request**.

Recommended gate semantics:

- use fixed, non-sample public canary URLs whose identities are frozen in the execution PR before authorization;
- canaries must be independent of Jiemian/Yicai and must have a stable expectation of public accessibility;
- actual HTTP requests/retries count toward an explicit diagnostic-preflight budget, but not toward the 40 article-attempt denominator;
- provider-level authentication/quota/payment outcomes such as systematic 401/402/429 produce `PROVIDER_NOT_READY`;
- on `PROVIDER_NOT_READY`, the Production Acquisition Feasibility track stops before any sample-body request;
- no automatic credential, billing or quota mutation is allowed;
- canary failure cannot be rewritten as a Route/source failure.

Exact canary identities and readiness thresholds must be frozen before a future execution authorization. This document deliberately does not send any canary request.

## 5. Track V — recommended measurement-only body-observability chain

### Objective

Obtain faithful bodies for the locked 40-item panel so that the already-frozen body-product rubric can be applied without making provider availability the dominant missingness mechanism.

### Recommended acquisition version

A new measurement-only chain should be explicitly versioned, for example:

`zh-route-shadow-s2b-body-observability-v2`

Recommended logical sequence:

1. **direct first-party HTML extraction** with the same body-usability gate used by the current collector measurement stack;
2. **Jina Reader** only when the provider-readiness gate says Jina is available;
3. **Firecrawl fallback** only when prior paths do not yield a usable body;
4. final terminal state remains explicit if all paths fail.

This is intentionally **not** the v1 legacy Control chain and must never be labeled production-equivalent.

Why this sequence is preferred over a Firecrawl-only rerun:

- direct HTML can provide free first-party observability for many pages;
- a provider-wide Jina failure no longer consumes one request per panel item;
- Firecrawl remains a bounded fallback rather than the universal first path;
- every extractor remains separately observable for body fidelity and failure analysis.

Why this sequence is preferred over simply increasing v1's shared Firecrawl cap:

- increasing only the global cap would preserve order bias: early rows can consume the whole rescue budget;
- v1 already demonstrated that a shared cap of three made the source result depend on deterministic execution order rather than source/body quality;
- v2 must allocate observability opportunity by the frozen panel structure, not by who happens to be processed first.

## 6. Fallback-budget allocation must be source/role reserved, not first-come shared

A future Track V execution may have a maximum paid-fallback budget, but it must be reserved against the frozen panel before requests begin.

Recommended maximum reservation for the full panel:

- Jiemian primary plausible: 15 fallback slots;
- Yicai primary plausible: 15 fallback slots;
- Jiemian uncertainty exploration: 4 fallback slots;
- Yicai uncertainty exploration: 6 fallback slots;
- total maximum paid-fallback reservation: 40.

This is a **maximum reservation**, not an instruction to issue 40 Firecrawl calls. Direct/Jina success should reduce actual paid fallback use.

If the user later authorizes a smaller cost envelope, the design must pre-freeze source/role-specific quotas before execution. A global first-come cap is not acceptable because it can mechanically censor one source more than another.

For source-level S3-information inference, the primary-plausible denominator remains the key denominator. A cost envelope that cannot in principle give each source at least 10/15 evaluable primary items should be labeled as insufficient for the existing source-decision floor before execution begins.

## 7. No replacement and no outcome-driven stopping

Article-level acquisition failure still does **not** trigger replacement.

Recommended stopping rules:

- provider-readiness failure: stop before panel requests and report `PROVIDER_NOT_READY`;
- hard execution-integrity failure (wrong manifest/hash, production-isolation breach, request-ledger corruption): stop and invalidate the run;
- article-level 4xx/5xx/body-unusable outcome: record the row and continue according to its pre-frozen acquisition path/budget;
- do not stop because the observed longread rate looks high or low;
- do not increase provider/fallback budget after seeing early body outcomes;
- do not substitute rows to reach an evaluability target.

If the pre-authorized total diagnostic budget is exhausted, remaining rows become explicit budget-censored rows. The source decision then uses the frozen evaluability rule; it is never backfilled.

## 8. Body review contract stays frozen

The existing S2-B v1 product rubric should remain unchanged for v2 to avoid changing both acquisition and product criteria at once.

`body_confirmed_standard_longread` still requires:

- correct canonical standalone article/body;
- content chars >=2500;
- not academic paper/primary document, corporate promotion, event recap, digest/roundup/quick update, brief/shallow news, listing/non-article or other frozen non-target class;
- at least two frozen substantive depth signals.

Acquisition status and body-product class remain separate.

Where operationally feasible, human/body review should be performed without exposing v1 outcome or acquisition path until after the body class is fixed. Source/title cannot always be hidden, but prior v1 classification must not be used as a label shortcut.

## 9. Track V decision floor

Reuse the already-frozen source-level information floor for comparability:

For each source's 15 primary-plausible rows:

- >=10 body-evaluable;
- >=5 body-confirmed Standard Longreads;
- confirmed supply across >=2 first-surface strata.

Only then may Track V state `SUPPORTS_S3_COUNTERFACTUAL` for that source.

Other possible states remain:

- `SOURCE_OR_SURFACE_RESTRICTED_REVIEW`;
- `DOES_NOT_SUPPORT_S3`;
- `NOT_EVALUABLE`.

Passing this floor does **not** authorize S3, production, route promotion or Editor wiring. It only establishes that a separately authorized fixed-32 counterfactual would be information-bearing.

## 10. Track F — Production Acquisition Feasibility must remain a separate comparator

Track F must preserve the actual production-equivalent acquisition semantics being evaluated at that future time.

For the current frozen v1 comparator, that identity is:

`legacy extract_article(): Jina Reader -> budgeted Firecrawl fallback`

with its real provider constraints and fallback budget.

A future Track F execution should occur only after its provider-readiness gate passes. Its results answer acquisition feasibility only:

- provider readiness;
- acquisition success / usable-body rate;
- actual request and retry counts;
- fallback demand and budget exhaustion;
- source/domain-specific acquisition failures after provider-wide failure is ruled out.

A Track V direct-HTML/expanded-fallback success must **not** be copied into Track F as production acquisition success.

Conversely, Track F acquisition failure must not be copied into Track V as body non-target quality.

## 11. Separate ledgers and version identities

Recommended standalone audit surfaces:

- `s2b_v2_provider_readiness`
- `s2b_v2_value_results`
- `s2b_v2_feasibility_results`
- `s2b_v2_summary`

Each row should retain:

- immutable manifest ordinal and canonical URL;
- source / first_surface / metadata class / sampling role;
- experiment track (`VALUE` or `FEASIBILITY`);
- acquisition version and code commit;
- provider readiness state inherited by the run;
- every logical extractor attempt;
- every actual HTTP request/retry count;
- Firecrawl calls/credits where exposed;
- usable-body fingerprint;
- content chars / truncation;
- terminal acquisition status;
- body product class and frozen depth signals where evaluable;
- censoring reason where not evaluable.

The validator must reject:

- manifest drift;
- row replacement;
- mixed v1/v2 result identity;
- v2 Track V rows mislabeled as production-equivalent;
- missing actual request telemetry;
- global fallback allocation that violates pre-frozen source/role reservation;
- body labels on non-usable rows;
- source-level rate calculations whose evaluability denominator is below the frozen floor.

## 12. Reporting rules

Always report three layers separately:

### A. Observability

- attempted panel rows;
- body-evaluable rows;
- acquisition-censored rows and reasons;
- source/role/surface distribution of censoring.

### B. Body value among evaluable rows

- confirmed Standard Longreads;
- non-target;
- borderline insufficient;
- source/first-surface breakdown;
- unweighted sample diagnostic with uncertainty;
- design-weighted frozen-cohort projection only when the required strata remain estimable.

### C. Production acquisition feasibility

- production-equivalent acquisition success;
- fallback demand;
- provider/system failures;
- request/credit cost;
- no body-quality inference from failed acquisition.

Never calculate one blended `S2-B success rate` across these layers.

## 13. Authorization matrix

### Already authorized/completed

- S2-A metadata-only audit;
- S2-B v1 one-time execution;
- v1 closeout and audit infrastructure;
- this design-only v2 decision package;
- Issue #148 operational tracking.

### Not authorized by this document

- Jina billing/account/credential change;
- canary/provider-readiness network probe;
- any v2 panel-body request;
- direct-HTML/Jina/Firecrawl v2 execution;
- Firecrawl fallback reservation/cost budget;
- Track F rerun;
- S3 fixed-32 counterfactual;
- source/host cap changes;
- live Route parser changes;
- natural 32-body budget change;
- production article_cache consumption;
- 07:35 Editor wiring;
- v06_primary / auto-promotion;
- Scheduler changes.

## 14. Recommended next user decision

When the user returns, the narrow decision should be:

> **Authorize or decline S2-B v2 Track V body-observability execution on the exact locked 40-item panel, under a separately approved provider-readiness gate and explicit maximum paid-fallback budget.**

If authorized, implementation should first freeze:

1. exact provider canaries and readiness thresholds;
2. exact `zh-route-shadow-s2b-body-observability-v2` acquisition path;
3. maximum paid fallback budget and source/role reservations;
4. total actual-request safety cap including retries;
5. isolated output workbook/tabs;
6. fail-closed validator;
7. no-replacement / no-pooling-with-v1 rules.

Only after those are materialized, reviewed and read back should the first v2 sample-body request be allowed.

Track F and S3 should remain separate later decisions.

## 15. Repository hygiene note

During preparation of this design package, a placeholder file was accidentally created on main and immediately removed. The two commits change no final repository content and have no runtime/config/workflow/data side effect. The feature branch for this package starts from the restored content-equivalent main state. This is retained here for audit transparency rather than silently omitted.
