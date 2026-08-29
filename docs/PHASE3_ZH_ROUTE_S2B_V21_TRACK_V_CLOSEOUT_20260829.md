# Phase 3 — S2-B v2.1 Track V closeout

Date: 2026-08-29 BJT  
Status: **EXECUTION COMPLETE / SOURCE-SPECIFIC DECISION RECORDED**  
Scope: **Jiemian-depth + Yicai only / measurement-only / not production-equivalent**  
Acquisition version: `zh-route-shadow-s2b-body-observability-v2.1-free-tier`

## 1. Why v2.1 existed

The first authorized Track V provider gate used the configured `JINA_API_KEY` and failed closed because all three fixed public non-sample canaries returned HTTP 402. A separate no-Authorization diagnostic repeated the same three canaries and returned 3/3 HTTP 200. v2.1 therefore changed only the isolated Track V measurement path to unauthenticated Jina Reader, with a global 3.1-second minimum interval between every actual Reader GET (including retries), below the documented 20 RPM free-tier ceiling.

No Jina billing/top-up, secret replacement, production `JinaReaderClient`, natural Collector, Track F, S3, Editor or Scheduler behavior was changed.

## 2. Frozen identity and immutable execution evidence

The pre-outcome sample was not redrawn.

- frozen panel: 40 article-attempt slots;
- manifest SHA-256: `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`;
- no replacement;
- primary plausible: Jiemian 15 + Yicai 15;
- uncertainty exploration: Jiemian 4 + Yicai 6;
- paid Firecrawl logical cap: 20, reserved Jiemian primary 10 + Yicai primary 10;
- actual HTTP safety cap: 230.

Unique execution evidence:

- Actions run: `33254126921`;
- execution commit: `9004f16bc355646fd039998baefa44ac7db6b987`;
- artifact: `s2b-v21-track-v-33254126921`;
- artifact ID: `9715820206`;
- artifact ZIP SHA-256: `8445559eda0e43c072e0f92dfbea74f2eb0e0eb17621d9e089e65d647cd71d7d`.

There was no compensating rerun.

## 3. Machine-level execution audit

The v2.1 provider gate passed:

- 3/3 fixed public canaries HTTP 200;
- `jina_auth_mode=unauthenticated_free_tier`;
- `jina_authorization_header_sent=false`;
- panel requests started = true.

Network accounting:

- actual HTTP requests: **90 <= 230**;
- `canary:jina`: 3;
- `panel:direct_html`: 40;
- `panel:jina`: 21;
- `panel:firecrawl`: 26;
- paid Firecrawl logical calls: **10 <= 20**.

The 26 Firecrawl HTTP requests came from internal retries under 10 logical calls. Terminal Firecrawl outcomes were 2 HTTP 200, 7 HTTP 500 and 1 HTTP 408. No Jina panel request returned HTTP 429.

Total body-evaluable targets: **21/40**.

No live Sheet, `article_cache`, Editor or production selection state was written.

## 4. Jiemian-depth result

Acquisition observability was complete:

- primary plausible evaluable: **15/15**;
- uncertainty evaluable: **4/4**;
- all 19 bodies obtained via direct first-party HTML;
- Jiemian consumed zero paid Firecrawl fallback.

Human review against the already-frozen body rubric classified all 15 primary plausible bodies as:

`body_confirmed_standard_longread`

Every confirmed item had >=2,500 content characters and >=2 substantive frozen depth signals. Confirmed supply spans three first-surface strata:

- `jiemian_consumer`;
- `jiemian_health_face`;
- `jiemian_medicine`.

Primary plausible audit-sample confirmation rate: **15/15 = 100%**.

- 80% Wilson interval: **90.1%–100.0%**;
- 95% Wilson interval: **79.6%–100.0%**.

Because every sampled plausible stratum was 100% confirmed, the design-weighted frozen-cohort point projection is also 100%. This is a descriptive projection for the frozen S2-A cohort, **not** a precise future-source PPV.

Frozen source decision:

`SUPPORTS_S3_COUNTERFACTUAL`

Reason: Jiemian exceeds all pre-specified information conditions (>=10/15 evaluable, >=5 confirmed, >=2 first-surface strata).

### Jiemian uncertainty sample

The four `insufficient_evidence` bodies produced:

- 0 confirmed Standard Longreads;
- 3 confirmed non-targets;
- 1 borderline/insufficient.

Therefore:

`NO_METADATA_UNDERCLASSIFICATION_SIGNAL`

This does not retrospectively relabel S2-A.

## 5. Yicai result

Yicai remains acquisition-censored:

- primary plausible evaluable: **2/15**;
- primary confirmed Standard Longreads: **2/2 evaluable**, but only 2/15 attempted;
- uncertainty evaluable: **0/6**.

The two observable primary bodies were both confirmed Standard Longreads, but the frozen information floor was not met. A 2/2 observed-positive result must not be treated as source PPV.

Frozen source decision:

`NOT_EVALUABLE`

because 2/15 < the pre-specified 10/15 source-level evaluability floor.

### Yicai acquisition forensic signal

All 21 Yicai panel identities showed the same upstream pattern:

- direct first-party HTML: **21/21 `ConnectTimeout`**;
- unauthenticated Jina Reader: **21/21 HTTP 422**;
- Jina HTTP 429: **0**;
- Yicai primary Firecrawl reservation: 10 logical calls, only 2 terminal successes;
- after the reserved 10 logical calls were consumed, later primary rows remained budget-censored by contract;
- Yicai uncertainty rows had no paid fallback allocation and therefore remained budget-censored after direct/Jina failure.

This is not evidence of poor Yicai content quality. It is a source-specific measurement acquisition blocker exposed after the provider-wide Jina 402 problem was removed. The exact cause (for example hostname/canonical-identity handling, source network behavior, or provider-specific URL acceptance) is **not established by v2.1** and must not be inferred post hoc.

Any source-specific retry or hostname/path experiment is a new forensic version; it may not rewrite or supplement the frozen v2.1 denominator.

## 6. Current-classifier diagnostic instrumentation gap

The frozen S2-B contract requested a parallel current-Collector-classifier diagnostic for each usable body. The v2.1 artifact persisted body text, title, author and publication field but did **not** persist the `verification_level` provenance needed for a faithful reconstruction of the current default longform classifier path. Current classifier logic uses `verification_level in {A, B}` together with the 2,500-character threshold for its default verified-longform disposition.

Therefore the closeout records:

`CURRENT_CLASSIFIER_DIAGNOSTIC = NOT_EVALUABLE_MISSING_VERIFICATION_LEVEL_PROVENANCE`

No blank verification value is substituted and no synthetic A/B level is invented. This is an instrumentation-completeness gap, not a body-quality failure. It does not invalidate the pre-frozen S3 admission gate, which is based on human reviewed body class, evaluability count and surface breadth rather than classifier agreement.

Any later classifier-confusion study should be offline/read-only and versioned separately.

## 7. Durable audit ledger

The standalone audit workbook `S2A_zero_new_body_audit_20260829` now contains:

- `s2b_v21_results`: 40 reviewed rows, one per frozen manifest identity;
- `s2b_v21_summary`: immutable execution identifiers, network accounting, source decisions and interpretation boundaries.

Readback confirmed all 40 reviewed rows and the source-specific summary.

The live system Sheet was not modified by this review ledger.

## 8. Interpretation and next decision boundary

The v2.1 result changes the evidence state source by source:

- **Jiemian-depth:** body value is now sufficiently observed and strongly positive under the frozen S2-B rubric. It supports a later **Jiemian-only S3 fixed-32 counterfactual**.
- **Yicai:** body value remains not evaluable because acquisition observability is inadequate, despite both observable primary bodies being positive.

This result does **not** authorize or start S3.

It also does not establish Production acquisition feasibility because v2.1 is explicitly measurement-only and uses an unauthenticated/free-tier Reader path plus direct-first-party acquisition. Track F remains separate and unauthorized.

## 9. Frozen boundaries after closeout

Unchanged:

- S3: **NOT AUTHORIZED / NOT STARTED**;
- Track F: **NOT AUTHORIZED**;
- Production: **SHADOW / NOT_READY**;
- natural Collector source/host caps and 32-body budget: unchanged;
- Editor wiring: unchanged/off;
- `article_cache` production consumption: unchanged;
- Scheduler reliability design: deferred / unchanged.

The one-shot v2.1 workflow and trigger must be removed from the PR before merge. No standing Track V network execution entrypoint may land on `main`.
