# Phase 3 — Chinese Route S2-B bounded body-validation contract v1

Date: 2026-08-29 BJT  
Status: **DESIGN FROZEN / EXECUTION NOT AUTHORIZED / ZERO BODY REQUESTS SO FAR**  
Scope: **Jiemian-depth + Yicai only**  
Contract version: `zh-route-shadow-s2b-body-validation-contract-v1`

## 1. First-principles question

S2-A established that Route expansion produces more than extra URLs: after v2 freshness, Control-overlap removal, negative-control removal and canonical dedupe, 71 article identities remain `plausible_standard_longread`, while 38 are `insufficient_evidence`.

S2-B must answer the next causal question and nothing broader:

> **When a bounded, pre-specified sample of these Treatment-only identities is inspected at body level, does useful Standard Longread supply survive?**

S2-B is **not** a ranking experiment, not a 32-slot displacement test, not production integration and not an attempt to maximize successful acquisitions.

Primary estimand:

- source-specific body-confirmation rate among S2-A `plausible_standard_longread` items.

Secondary estimand:

- hidden Standard Longread yield among S2-A `insufficient_evidence` items.

The secondary group calibrates whether metadata uncertainty contains meaningful false negatives; it does not count toward the primary source-quality denominator.

## 2. Frozen universe

The only eligible universe is the completed S2-A canonical cohort in:

`S2A_zero_new_body_audit_20260829`

Spreadsheet ID:

`1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ`

Frozen S2-A denominators:

| Source | Plausible | Insufficient | Obvious out-of-scope |
| --- | ---: | ---: | ---: |
| Jiemian-depth | 28 | 13 | 5 |
| Yicai | 43 | 25 | 15 |
| **Total** | **71** | **38** | **20** |

`obvious_out_of_scope` is never eligible for S2-B body budget.

No future S1 exposure may be silently appended to this S2-B cohort. A later cohort requires a separately versioned experiment.

## 3. Why the body-attempt cap is 40

S2-B needs source-specific evidence, not a pooled portfolio percentage. The design therefore balances the primary sample across sources rather than sampling strictly in proportion to 28:43.

Frozen maximum:

- **30 primary plausible targets**: 15 Jiemian + 15 Yicai;
- **10 uncertainty-exploration targets**: 4 Jiemian + 6 Yicai;
- **40 total article-attempt slots**;
- **no replacement** after acquisition failure.

This is intentionally a diagnostic sample, not a precision prevalence study. With 15 plausible targets per source, S2-B can detect catastrophic metadata overprediction, establish whether body-confirmed supply survives across multiple route surfaces, and decide whether a fixed-budget S3 counterfactual would be informative. It is not sufficient to claim a highly precise population PPV for all future articles.

Both 80% and 95% Wilson intervals should be reported for source-level body-confirmation rates; the experiment must not hide uncertainty behind a point estimate.

## 4. Frozen stratification and quotas

`first_surface` from the S2-A canonical cohort is the attribution key. Repeated appearances on additional surfaces remain provenance, but one article receives one stratum.

### Jiemian-depth

Frozen denominators:

| Metadata class | First surface | N | S2-B quota |
| --- | --- | ---: | ---: |
| plausible | `jiemian_medicine` | 16 | **8** |
| plausible | `jiemian_consumer` | 11 | **6** |
| plausible | `jiemian_health_face` | 1 | **1** |
| insufficient | `jiemian_medicine` | 4 | **1** |
| insufficient | `jiemian_consumer` | 9 | **3** |

Total: **19 targets**.

### Yicai

Frozen denominators:

| Metadata class | First surface | N | S2-B quota |
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

The quotas preserve all small primary route families while roughly reflecting larger strata. No quota may borrow from another stratum after results are seen.

## 5. Deterministic sample selection

Selection must be completed **before the first body request**.

Frozen selector:

- implementation: `zh_route_shadow_s2b_sample_plan_v1.py`;
- version: `zh-route-shadow-s2b-sample-plan-v1`;
- seed: `zh-route-shadow-s2b-20260829-v1`;
- rank key: SHA-256 of `seed | source | metadata_class | first_surface | canonical_url`;
- select the lowest deterministic ranks within each frozen stratum;
- canonical URLs must be unique;
- a stratum below quota fails closed;
- no cross-stratum substitution;
- no known miss, favorite article or manually appealing title receives forced inclusion.

This prevents cherry-picking while keeping the sample reproducible.

The selected 40-row manifest must be persisted to an isolated S2-B audit ledger and read back **before** network acquisition begins.

## 6. Acquisition contract

S2-B introduces new body/network work only if separately authorized later.

When execution is authorized, acquisition must obey all of the following:

1. Use the **same existing Control body-acquisition semantics** as the frozen runtime, not a new S2-B-specific success-maximizing chain.
2. Runtime semantic baseline remains `a380c68920c1de26f1e703b721d7eb2195900002`; later measurement/docs-only commits do not change this boundary.
3. Record the exact code commit / acquisition fingerprint at execution. If the Control acquisition path has materially changed since the frozen baseline, stop and re-review rather than silently mixing versions.
4. Maximum **40 sampled article-attempt slots**.
5. No replacement after `acquisition_failed`, blocked, wrong-shell or otherwise not-evaluable outcomes.
6. Underlying per-article fallbacks may execute only if they are already part of the current Control acquisition path. S2-B may not add a new fallback, retry policy, direct-HTML branch, Firecrawl rule or usable-body gate merely to improve audit yield.
7. Record actual network request count, extraction path, fallback use, Firecrawl use if any, terminal status, body character count and body fingerprint.
8. S2-B attempts are **separate from and do not consume or alter** the natural Collector 32-body-attempt budget.
9. No S2-B body or result is written into production `article_cache`, Editor input or live selection state.
10. Audit persistence is isolated from the live system ledger.

Acquisition failure is evidence. It must not be repaired away by replacement sampling.

## 7. Body-level outcome model

S2-B keeps acquisition quality separate from product eligibility.

### 7.1 Acquisition status

Each target receives exactly one terminal acquisition state:

- `usable_body`
- `acquisition_failed`
- `wrong_or_shell_body`
- `duplicate_or_noncanonical_body`

Only `usable_body` proceeds to product classification. All others are `not_evaluable` for body-product status and remain in the attempt denominator.

### 7.2 Body product class

For a usable body, the reviewed body class is one of:

- `body_confirmed_standard_longread`
- `body_confirmed_non_target`
- `body_borderline_insufficient`

`body_confirmed_standard_longread` requires all of the following:

1. canonical standalone article identity is correct;
2. usable article body contains at least **2,500 content characters**, matching the current default formal-candidate longform threshold;
3. it is not an academic paper, primary document, press release / corporate promotion, event recap, digest / roundup, brief update, listing page or other non-target format;
4. the body contains at least **two substantive depth signals** from this frozen list:
   - multi-source reporting or substantive interview evidence;
   - quantitative / documentary evidence interpreted beyond a bare announcement;
   - causal, explanatory, strategic or mechanism-level analysis;
   - meaningful historical, competitive, regulatory or policy context;
   - original field, investigative or primary-source reporting beyond routine company copy.

Length is necessary but not sufficient. A 2,500-character corporate release is still non-target.

`body_borderline_insufficient` is used when the correct body is present but the frozen evidence cannot confidently distinguish a substantive longread from a shallow article. Borderline is not silently counted positive or negative in the primary rate.

### 7.3 Parallel classifier diagnostic

For every usable body, also run/record the current Collector classifier result (`candidate_disposition`, `content_type`, `reason`, `verification_level`, `content_chars`).

The reviewed S2-B product class and current classifier output are separate fields. Their disagreement is a diagnostic result, not an error to be manually harmonized after review.

## 8. Frozen reporting denominators

For each source and first-surface stratum report:

- sampled targets;
- usable bodies;
- acquisition failures / wrong-shell / noncanonical;
- body-confirmed Standard Longreads;
- body-confirmed non-targets;
- borderline/insufficient;
- confirmation rate among **evaluable plausible** items;
- confirmation rate among **all attempted plausible** items;
- 80% and 95% Wilson interval for the evaluable-plausible confirmation rate;
- non-target reason distribution;
- acquisition-path distribution;
- current-classifier vs reviewed-body confusion table.

For the secondary `insufficient_evidence` sample, report hidden confirmed-longread yield separately. Never pool it into the primary plausible precision estimate.

No overall portfolio percentage may replace the source-specific denominators.

## 9. Decision rule after S2-B

S2-B does **not** authorize S3 by itself. It prepares a source-specific decision.

For each source:

### `SUPPORTS_S3_COUNTERFACTUAL`

Minimum evidence floor:

- at least **10 of 15** plausible targets are body-evaluable; and
- at least **5 body-confirmed Standard Longreads** survive among the 15 plausible targets; and
- confirmed supply is represented on at least **two first-surface strata**.

This is deliberately a floor for deciding whether a 32-slot displacement counterfactual would contain enough real Treatment supply to be informative. It is **not** a production promotion threshold and is not a claim that 5/15 is an acceptable final precision.

### `SOURCE_OR_SURFACE_RESTRICTED_REVIEW`

Use when useful body-confirmed supply exists but is concentrated in one surface family, or a specific surface shows a dominant non-target pattern. Any later S3 proposal must then be restricted to the supported surface subset rather than treating the whole source as homogeneous.

### `DOES_NOT_SUPPORT_S3`

Use when at least 10 plausible targets are evaluable but fewer than 5 are body-confirmed Standard Longreads.

### `NOT_EVALUABLE`

Use when fewer than 10 of 15 plausible targets are evaluable because acquisition/body identity failure prevents a reliable source-level conclusion.

No replacement sampling is allowed to escape `NOT_EVALUABLE`.

## 10. Secondary uncertainty signal

The 10 `insufficient_evidence` targets exist only to measure whether S2-A metadata review is leaving meaningful value behind.

If either source produces **two or more** body-confirmed Standard Longreads from its insufficient sample, mark:

`METADATA_UNDERCLASSIFICATION_SIGNAL`

This does not retroactively change S2-A labels or add those items to the primary PPV. It triggers a later, separately reviewed metadata-classification analysis.

## 11. Explicit non-goals / frozen boundaries

This contract does **not** authorize:

- any body/network request;
- execution of the 40-target manifest;
- S3 / fixed-32 counterfactual;
- Route Portfolio changes;
- source registry, source cap, host cap or natural 32-body budget changes;
- live timestamp-parser changes;
- article_cache production writes;
- 07:35 Editor wiring;
- `V06_PRIMARY_ENABLED`;
- auto-promotion;
- Caixin or EEO S2 work;
- Scheduler reliability design or Scheduler changes.

Production remains **SHADOW / NOT_READY**.

## 12. Next user decision

After this contract is reviewed and merged, the narrow next authorization is:

> **Authorize S2-B execution for the frozen 40-target deterministic manifest under this contract.**

Before the first network request, execution must materialize and read back the exact 40-row sample manifest and confirm runtime/acquisition fingerprint compatibility with the frozen baseline.
