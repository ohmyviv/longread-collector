# Phase 3 — Chinese Route S2-B bounded body-validation contract v1

Date: 2026-08-29 BJT  
Status: **DESIGN FROZEN / EXECUTION NOT AUTHORIZED / ZERO BODY REQUESTS SO FAR**  
Scope: **Jiemian-depth + Yicai only**  
Contract version: `zh-route-shadow-s2b-body-validation-contract-v1`

## 1. First-principles question

S2-A established that Route expansion produces more than extra URLs: after v2 freshness, Control-overlap removal, negative-control removal and canonical dedupe, 71 article identities remain `plausible_standard_longread`, while 38 are `insufficient_evidence`.

S2-B asks only:

> **When a bounded, pre-specified sample of these Treatment-only identities is inspected at body level, does useful Standard Longread supply survive?**

S2-B is not ranking, fixed-32 displacement, production integration or an attempt to maximize successful acquisitions.

Primary evidence object:

- source-specific body survival of the S2-A `plausible_standard_longread` cohort.

Secondary evidence object:

- hidden Standard Longread yield among S2-A `insufficient_evidence` items.

The secondary group calibrates metadata uncertainty; it never enters the primary plausible denominator.

## 2. Frozen universe

The only eligible universe is the completed S2-A canonical cohort in:

`S2A_zero_new_body_audit_20260829`

Spreadsheet ID:

`1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ`

| Source | Plausible | Insufficient | Obvious out-of-scope | Total |
| --- | ---: | ---: | ---: | ---: |
| Jiemian-depth | 28 | 13 | 5 | 46 |
| Yicai | 43 | 25 | 15 | 83 |
| **Total** | **71** | **38** | **20** | **129** |

`obvious_out_of_scope` never receives S2-B body budget.

The deterministic selector must fail closed unless the input remains the exact frozen 129-item cohort, including exact source/class and eligible source/class/first-surface denominators. Later S1 accumulation may not perturb this experiment; a later cohort needs a new version.

## 3. Body-attempt cap and estimands

Frozen maximum:

- **30 primary plausible targets**: 15 Jiemian + 15 Yicai;
- **10 uncertainty-exploration targets**: 4 Jiemian + 6 Yicai;
- **40 total article-attempt slots**;
- **no replacement** after acquisition failure.

The design balances the main sample across sources because the decision is source-specific. It also deliberately preserves small route surfaces. Therefore the stratified sample is **not perfectly self-weighting**.

S2-B must report two different rates and never conflate them:

1. **Audit-sample rate** — the simple observed confirmation rate in the frozen sample. This is the direct experimental diagnostic. Report 80% and 95% Wilson intervals for the unweighted sample rate.
2. **Design-weighted frozen-cohort projection** — weight each first-surface stratum by its frozen S2-A denominator `N_h` and its sampled quota `n_h`. This is a descriptive point estimate of body survival in the current frozen cohort, not a precise future-source PPV. Do not attach an ordinary Wilson interval to the weighted estimate.

For attempted-denominator projection:

`sum_h N_h * confirmed_h / n_h  /  sum_h N_h`

For evaluable-only projection, use the corresponding ratio estimator:

`sum_h N_h * confirmed_h / n_h  /  sum_h N_h * evaluable_h / n_h`

The experiment is diagnostic, not a prevalence study. It must not claim a precise PPV for future Jiemian/Yicai output.

## 4. Frozen stratification and quotas

`first_surface` from S2-A is the attribution key. Additional qualifying surfaces remain provenance.

### Jiemian-depth

| Metadata class | First surface | Frozen N | S2-B quota |
| --- | --- | ---: | ---: |
| plausible | `jiemian_medicine` | 16 | **8** |
| plausible | `jiemian_consumer` | 11 | **6** |
| plausible | `jiemian_health_face` | 1 | **1** |
| insufficient | `jiemian_medicine` | 4 | **1** |
| insufficient | `jiemian_consumer` | 9 | **3** |

Total: **19 targets**.

### Yicai

| Metadata class | First surface | Frozen N | S2-B quota |
| --- | --- | ---: | ---: |
| plausible | `yicai_kechuang` | 22 | **7** |
| plausible | `yicai_finance` | 14 | **5** |
| plausible | `yicai_news_breadth` | 5 | **2** |
| plausible | `yicai_auto` | 2 | **1** |
| insufficient | `yicai_finance` | 15 | **3** |
| insufficient | `yicai_kechuang` | 5 | **1** |
| insufficient | `yicai_news_breadth` | 4 | **1** |
| insufficient | `yicai_auto` | 1 | **1** |

Total: **21 targets**.

No quota may borrow from another stratum after results are seen.

## 5. Deterministic sample selection

Selection must be complete before the first body request.

Frozen selector:

- implementation: `zh_route_shadow_s2b_sample_plan_v1.py`;
- version: `zh-route-shadow-s2b-sample-plan-v1`;
- seed: `zh-route-shadow-s2b-20260829-v1`;
- ranking: SHA-256 of `seed | source | metadata_class | first_surface | canonical_url`;
- select the lowest ranks within each frozen stratum;
- canonical URLs must be unique;
- exact 129-item frozen-universe assertions must pass;
- a changed source/class/stratum denominator fails closed;
- no cross-stratum substitution;
- no known miss, favorite article or attractive title is force-included.

The selected 40-row manifest must be persisted to an isolated S2-B audit ledger and read back **before** network acquisition begins.

## 6. Acquisition contract

S2-B introduces new body/network work only after separate execution authorization.

Execution must:

1. use the **same existing Control body-acquisition semantics** as the frozen runtime rather than an S2-B-specific success-maximizing chain;
2. retain runtime semantic baseline `a380c68920c1de26f1e703b721d7eb2195900002`; later measurement/docs-only changes do not alter that boundary;
3. record exact code commit and acquisition fingerprint; if the Control acquisition path materially changed, stop for re-review;
4. attempt at most the **40 sampled article slots**;
5. perform no replacement after acquisition failure, blocked/wrong-shell or non-evaluable outcome;
6. use only fallbacks already present in the current Control acquisition path; no new direct-HTML, retry, Firecrawl or usable-body rule may be added to improve S2-B yield;
7. record network request count, extraction path, fallback/Firecrawl use if applicable, terminal status, body character count and body fingerprint;
8. keep S2-B attempts separate from the natural Collector 32-body budget;
9. write no S2-B result/body into production `article_cache`, Editor input or live selection state;
10. persist only to an isolated audit ledger.

Acquisition failure is evidence and must not be repaired away by replacement sampling.

## 7. Body-level outcome model

Acquisition quality and product eligibility are separate axes.

### 7.1 Acquisition status

Exactly one terminal state per target:

- `usable_body`
- `acquisition_failed`
- `wrong_or_shell_body`
- `duplicate_or_noncanonical_body`

Only `usable_body` is body-product evaluable. Other states remain in the attempted denominator.

### 7.2 Reviewed body product class

For a usable body:

- `body_confirmed_standard_longread`
- `body_confirmed_non_target`
- `body_borderline_insufficient`

`body_confirmed_standard_longread` requires all of:

1. correct canonical standalone article identity;
2. at least **2,500 content characters**, matching the current default formal-candidate longform threshold;
3. not an academic paper, primary document, press release/corporate promotion, event recap, digest/roundup, brief update, listing or other non-target format;
4. at least **two** substantive depth signals:
   - multi-source reporting or substantive interview evidence;
   - quantitative/documentary evidence interpreted beyond a bare announcement;
   - causal, explanatory, strategic or mechanism-level analysis;
   - meaningful historical, competitive, regulatory or policy context;
   - original field, investigative or primary-source reporting beyond routine company copy.

Length is necessary but insufficient. Long corporate copy remains non-target.

`body_borderline_insufficient` is not counted positive or negative in the evaluable-plausible confirmation rate; it must remain visible as uncertainty.

### 7.3 Parallel current-classifier diagnostic

For every usable body also record current Collector classifier outputs: `candidate_disposition`, `content_type`, `reason`, `verification_level`, `content_chars`.

Human reviewed body class and current classifier output are separate. Disagreement is a diagnostic result, not something to harmonize after seeing outcomes.

## 8. Frozen reporting denominators

For every source and first-surface stratum report:

- sampled targets;
- usable bodies;
- acquisition failures / wrong-shell / noncanonical;
- body-confirmed Standard Longreads;
- body-confirmed non-targets;
- borderline/insufficient;
- simple confirmation rate among evaluable plausible items;
- simple confirmation rate among all attempted plausible items;
- 80% and 95% Wilson intervals for the **unweighted** evaluable-plausible sample rate;
- design-weighted attempted and evaluable frozen-cohort projections using `N_h/n_h`;
- non-target reason distribution;
- acquisition-path distribution;
- current-classifier vs reviewed-body confusion table.

For `insufficient_evidence`, report hidden confirmed-longread yield separately, including stratum counts; never pool it into plausible precision.

A pooled Jiemian+Yicai percentage may be shown descriptively but may not replace source-specific denominators.

## 9. Decision rule after S2-B

S2-B does not authorize S3; it prepares a source-specific decision.

### `SUPPORTS_S3_COUNTERFACTUAL`

Minimum information floor:

- at least **10 of 15** plausible targets are body-evaluable;
- at least **5 body-confirmed Standard Longreads** survive among the 15 plausible targets;
- confirmed supply spans at least **two first-surface strata**.

This floor asks only whether a fixed-32 counterfactual would contain enough real Treatment supply to be informative. It is not a production precision threshold.

### `SOURCE_OR_SURFACE_RESTRICTED_REVIEW`

Use when useful supply survives but is concentrated in one surface family, or one surface shows a dominant non-target pattern. Any later S3 proposal must then be restricted to supported strata.

### `DOES_NOT_SUPPORT_S3`

Use when at least 10 plausible targets are evaluable but fewer than 5 are body-confirmed Standard Longreads.

### `NOT_EVALUABLE`

Use when fewer than 10 of 15 plausible targets are evaluable because acquisition/body-identity failure blocks a reliable source-level conclusion.

No replacement may be used to escape `NOT_EVALUABLE`.

## 10. Secondary uncertainty signal

The 10 `insufficient_evidence` targets only measure whether metadata review leaves meaningful value behind.

If either source yields **two or more** body-confirmed Standard Longreads from its insufficient sample, mark:

`METADATA_UNDERCLASSIFICATION_SIGNAL`

This does not relabel S2-A retrospectively and does not enter the primary PPV. It triggers a separate metadata-classification analysis.

## 11. Explicit non-goals / frozen boundaries

This contract does **not** authorize:

- any body/network request;
- execution of the 40-target manifest;
- S3 / fixed-32 counterfactual;
- Route Portfolio, source registry, source cap, host cap or natural 32-body budget change;
- live timestamp-parser changes;
- production article_cache writes;
- 07:35 Editor wiring;
- `V06_PRIMARY_ENABLED` or auto-promotion;
- Caixin/EEO S2 work;
- Scheduler reliability design or Scheduler changes.

Production remains **SHADOW / NOT_READY**.

## 12. Next user decision

After this contract passes CI and is merged, the narrow next authorization is:

> **Authorize S2-B execution for the frozen 40-target deterministic manifest under this contract.**

Before the first network request, execution must materialize/read back the exact 40-row manifest and confirm runtime/acquisition fingerprint compatibility with the frozen baseline.
