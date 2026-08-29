# Phase 3 — S2-B v2.1 reviewed-ledger closeout contract

Date: 2026-08-29 BJT  
Status: **CLOSEOUT EVIDENCE CONTRACT**

This document records the interpretation contract used to persist and read back the S2-B v2.1 reviewed ledger after the single completed execution. It adds no network request and changes no body outcome.

## Reviewed ledger identity

Standalone workbook: `S2A_zero_new_body_audit_20260829`  
Spreadsheet ID: `1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ`

Tabs:

- `s2b_v21_results`: exactly 40 reviewed rows, one per frozen manifest ordinal 1..40;
- `s2b_v21_summary`: execution identity, machine accounting, source decisions and boundaries.

The manifest identity remains:

`7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`

No row may be replaced or added to change a source denominator.

## Mapping from acquisition evidence to review state

Raw `body_observed` rows are body-evaluable and receive one frozen human body class:

- `body_confirmed_standard_longread`
- `body_confirmed_non_target`
- `body_borderline_insufficient`

Raw `acquisition_failed` and `budget_censored` rows remain `not_evaluable` in the reviewed ledger. `budget_censored` is retained visibly as its raw measurement state rather than rewritten as content failure.

## Body-confirmed Standard Longread rule

A positive reviewed body must satisfy the already-frozen S2-B requirements:

- correct canonical standalone article identity;
- >=2,500 content characters;
- not an excluded product type;
- >=2 substantive frozen depth signals.

## Source decision calculation

Primary plausible only:

- `SUPPORTS_S3_COUNTERFACTUAL`: >=10/15 evaluable, >=5 confirmed Standard Longreads, >=2 first-surface strata;
- `DOES_NOT_SUPPORT_S3`: >=10/15 evaluable but <5 confirmed;
- `NOT_EVALUABLE`: <10/15 evaluable.

The uncertainty sample is reported separately and never enters plausible precision.

## Classifier diagnostic boundary

The artifact lacks `verification_level` provenance required for a faithful current-classifier confusion table. Therefore that diagnostic is explicitly `NOT_EVALUABLE_MISSING_VERIFICATION_LEVEL_PROVENANCE`; no synthetic level is assigned.

## Result fixed by readback

- Jiemian primary: 15/15 evaluable, 15/15 confirmed, three surfaces => `SUPPORTS_S3_COUNTERFACTUAL`.
- Jiemian uncertainty: 0/4 confirmed => no metadata-underclassification signal.
- Yicai primary: 2/15 evaluable, both observed bodies confirmed => `NOT_EVALUABLE` because the information floor fails.
- Yicai uncertainty: 0/6 evaluable.

S3 remains NOT AUTHORIZED / NOT STARTED.
