# Phase 3 — Chinese Route S2-A zero-new-body eligibility audit

Date: 2026-08-29 BJT  
Status: **S2-A COMPLETED / METADATA-ONLY / S2-B NOT AUTHORIZED**  
Scope: Jiemian-depth + Yicai only  
Production promotion: **NOT AUTHORIZED**

## 1. Authorization and hard boundary

The user explicitly authorized S2-A for Jiemian + Yicai after the source-specific S2 readiness review.

S2-A used only already-persisted S1 Route Shadow metadata plus the frozen `zh-route-shadow-timestamp-measurement-v2` interpretation. It performed **zero new body acquisitions and zero new article/network requests**. It did not call Jina, Firecrawl, publisher pages, body extraction, Discovery, candidate selection or Editor.

No live Collector Sheet row was modified. The reviewed ledger was written only to a standalone audit copy:

`S2A_zero_new_body_audit_20260829`

Spreadsheet ID:

`1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ`

The live system ledger remains unchanged.

## 2. Deterministic cohort contract

The S2-A denominator is **not** the raw 428 Yicai rows plus 292 Jiemian rows. An article enters the audit cohort only when all of the following hold:

1. source is `jiemian-depth` or `yicai`;
2. Timestamp Measurement v2 classifies the row `fresh`;
3. `surface_role != noise_control`;
4. same-run `control_overlap=FALSE`;
5. canonical article identity is present;
6. repeated appearances across surfaces/exposures are canonical-deduped while provenance is retained.

The resulting frozen cohort is:

| Source | Canonical-unique S2-A cohort |
| --- | ---: |
| Jiemian-depth | **46** |
| Yicai | **83** |
| **Total** | **129** |

This is the correct eligibility denominator for the current four-exposure evidence window.

## 3. Reviewed metadata classes

S2-A intentionally uses only three classes:

- `plausible_standard_longread` — metadata contains a substantive editorial/depth signal strong enough to justify later body validation;
- `obvious_out_of_scope` — metadata itself is sufficient to identify a high-confidence non-target format, currently promotional/corporate-PR identity or quick digest/comment/roundup format;
- `insufficient_evidence` — metadata alone cannot determine Standard Longread status. This is **not a reject**.

The reviewed label is a human metadata judgment. It is not represented as deterministic model truth. The deterministic code only builds the cohort and validates exact reviewed-label coverage/counts.

## 4. Results

### Overall

| Metadata class | Count | Share of 129 |
| --- | ---: | ---: |
| `plausible_standard_longread` | **71** | **55.0%** |
| `obvious_out_of_scope` | **20** | **15.5%** |
| `insufficient_evidence` | **38** | **29.5%** |
| **Total** | **129** | **100%** |

High-confidence obvious contamination decomposes into:

- promotional / corporate-PR identity: **15 / 129 = 11.6%**;
- quick digest / comment / roundup identity: **5 / 129 = 3.9%**.

### Jiemian-depth

| Class | Count | Share of 46 |
| --- | ---: | ---: |
| plausible Standard Longread | **28** | **60.9%** |
| obvious out-of-scope | **5** | **10.9%** |
| insufficient evidence | **13** | **28.3%** |

The strongest signal remains `jiemian_medicine`. Examples of metadata-plausible longread identities include the gene-therapy commercialization piece, blood-product industry analysis, medical-company operating analyses and broader health/industry explanatory pieces.

Obvious contamination is limited and mostly identifiable from metadata: corporate collaboration/service announcements and a small quick-comment format.

**Interpretation:** Jiemian has the cleaner S2-A supply profile. More than three-fifths of canonical Treatment incrementals have a plausible Standard Longread identity before any new body budget is spent, while obvious metadata-level contamination is roughly one in nine.

### Yicai

| Class | Count | Share of 83 |
| --- | ---: | ---: |
| plausible Standard Longread | **43** | **51.8%** |
| obvious out-of-scope | **15** | **18.1%** |
| insufficient evidence | **25** | **30.1%** |

Metadata-plausible supply includes industry/market structure analysis, interviews, policy/financial-system explainers, robotics/AI analysis and company/sector operating deep dives.

The main obvious contamination families are corporate/promotional copy and recurring quick formats such as `AI进化速递` / weekly roundup-style items. A materially larger share than Jiemian remains ambiguous from listing metadata alone.

**Interpretation:** Yicai still clears the S2-A usefulness question, but with a noisier supply profile. Its later body-level test should remain restricted to the strict v2-fresh, non-control, Control-incremental cohort rather than general Yicai discovery.

## 5. What S2-A does and does not prove

S2-A establishes that the route expansions do not merely add URLs. After freshness correction, Control-overlap removal, negative-control removal and canonical dedupe, **71 independent article identities still carry metadata-level signals compatible with the Standard Longread product**.

It does **not** establish that 71 articles are body-confirmed longreads, eligible Editor candidates, or recommendation-quality articles. In particular:

- `plausible_standard_longread` still requires body-level validation before any stronger claim;
- `insufficient_evidence` must not be counted as a failure or silently promoted;
- title/listing metadata cannot establish article length, argument depth, evidence quality or editorial utility;
- no fixed-32 displacement/value conclusion has been made.

## 6. Source-specific decision

### Jiemian-depth

**S2-A RESULT: POSITIVE.**

A separately authorized bounded S2-B body audit is justified. Jiemian should be the higher-priority source because its plausible share is higher and obvious contamination lower.

### Yicai

**S2-A RESULT: POSITIVE, WITH STRONGER GUARDRAILS.**

A separately authorized bounded S2-B body audit is also justified, but only for the strict S2-A cohort and preferably stratified by source surface so promotional/quick-format displacement can be measured explicitly.

### Portfolio

This does not move Caixin or EEO. They remain outside the S2-A authorization and continue accumulating natural S1 evidence.

## 7. Next gate

S2-B is **not authorized and has not started**.

If separately authorized, the next experiment should be a bounded body-level validation of a predefined Jiemian/Yicai subset. It should answer how many metadata-plausible identities actually satisfy Standard Longread body requirements before any S3 fixed-32 displacement counterfactual is considered.

S2-B must have an explicit acquisition budget, frozen sampling/selection rule and source/surface denominators before the first body request. It must not silently turn the 71 metadata-plausible rows into a body-acquisition queue.

## 8. Frozen system boundaries

No change to:

- Control;
- live S1 Treatment parser;
- Route Portfolio;
- source registry / source cap / host cap;
- 32-body-attempt budget;
- article_cache production consumption;
- 07:35 Editor;
- `V06_PRIMARY_ENABLED`;
- auto-promotion;
- Scheduler design or triggers.

Production remains **SHADOW / NOT_READY**.
