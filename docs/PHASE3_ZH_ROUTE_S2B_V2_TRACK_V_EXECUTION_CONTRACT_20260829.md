# Phase 3 Chinese Route — S2-B v2 Track V Execution Contract

## Authorization

**AUTHORIZED 2026-08-29 / TRACK V ONLY**

The user explicitly authorized S2-B v2 Track V body-observability execution on the exact frozen 40-item panel, including a provider-readiness canary contract and a bounded paid Firecrawl fallback budget.

This authorization does **not** authorize Track F, S3, Production, Editor wiring, Route/source/cap changes, natural Collector body-budget changes, Scheduler changes, Jina billing/account mutation, or automatic promotion.

## Frozen identity

- v1/v2 panel manifest SHA-256: `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`
- panel size: 40
- Jiemian-depth: 19 rows = 15 primary plausible + 4 uncertainty exploration
- Yicai: 21 rows = 15 primary plausible + 6 uncertainty exploration
- no replacement
- no new S1 rows
- v1 results immutable and never pooled into v2 denominators
- standalone audit workbook: `1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ`

## Provider-readiness canary contract

Canaries are fixed public non-sample URLs, independent of Jiemian/Yicai:

1. `https://www.iana.org/help/example-domains`
2. `https://www.python.org/about/`
3. `https://www.gnu.org/philosophy/free-sw.en.html`

The canary tests **Jina Reader provider readiness only**. No Firecrawl request is used for canarying.

For each canary, success requires:

- Jina request returns successfully with HTTP 2xx;
- returned readable body length >= 300 characters.

Gate:

- `READY`: >=2/3 canaries succeed and fewer than 2 canaries terminate with provider auth/quota/payment status in `{401,402,403,429}`.
- `PROVIDER_NOT_READY`: >=2 canaries terminate with provider auth/quota/payment status in `{401,402,403,429}`.
- otherwise: `INDETERMINATE`.

`PROVIDER_NOT_READY` or `INDETERMINATE` is fail-closed: **zero panel-body requests** are allowed.

No credential, billing, quota or provider configuration is automatically changed in response to canary failure.

The canary request budget is at most 9 actual HTTP requests because Jina may make up to 3 attempts on retryable statuses.

## Track V acquisition version

Version identity:

`zh-route-shadow-s2b-body-observability-v2`

Logical sequence for each frozen panel row:

1. direct first-party HTML GET and deterministic text extraction;
2. Jina Reader, only because the run-level canary gate is `READY`, if direct HTML does not yield a sufficiently usable body;
3. Firecrawl only if prior paths do not yield a sufficiently usable body **and** the row is within the pre-authorized source/role paid fallback reservation;
4. explicit terminal/censoring state otherwise.

This chain is measurement-only and **must never be labeled production-equivalent**.

The existing `content_quality_reason()` gate remains the common readable-body usability check. A path is considered sufficient to stop further fallback when it passes the body-quality gate and has at least the frozen `MIN_BODY_CHARS=1200`. The final best observed candidate is still retained even if it is shorter so that short-but-correct articles can be reviewed as body non-target rather than silently converted into acquisition failures.

## Paid Firecrawl budget

Maximum paid Firecrawl panel calls: **20**.

Source/role reservations:

- Jiemian-depth `primary_plausible`: maximum 10 Firecrawl calls;
- Yicai `primary_plausible`: maximum 10 Firecrawl calls;
- Jiemian uncertainty exploration: 0 paid Firecrawl calls;
- Yicai uncertainty exploration: 0 paid Firecrawl calls.

Within each source, the reserved pool is consumed only by primary rows that actually need fallback, in frozen manifest ordinal order. Unused source reservation is **not transferable** across sources or into uncertainty rows.

This structure is intentionally aligned to the existing source-level information floor: each source can in principle obtain up to 10/15 primary rows through paid rescue if free/direct/Jina observability is poor.

## Network safety cap

All actual HTTP requests/retries must be counted.

Hard Track V safety cap including canary + panel requests: **230 actual HTTP requests**.

The cap covers worst-case bounded behavior under:

- <=9 Jina canary requests;
- <=40 direct first-party GETs;
- <=120 panel Jina requests under retryable status behavior;
- <=60 Firecrawl HTTP attempts for at most 20 logical paid fallback calls.

The execution wrapper must raise before sending request 231.

## Isolation

The execution may read the standalone S2 audit workbook and use GitHub Actions secrets needed for acquisition. It must not:

- write live `article_cache`;
- write the live Collector Sheet;
- consume or mutate natural Collector's daily Firecrawl ledger;
- enter candidate selection;
- change natural 32-body budget;
- connect the 07:35 Editor;
- change source/host caps;
- change Route discovery/parser semantics;
- change Scheduler configuration.

The run writes only an immutable GitHub Actions artifact during acquisition. Reviewed result ledgers are persisted later to isolated S2 audit tabs after artifact readback.

## Body-review contract

The v1 body-product rubric remains unchanged.

`body_confirmed_standard_longread` requires:

- correct canonical standalone article/body;
- content chars >=2500;
- not academic paper/primary document, corporate promotion, event recap, digest/roundup/quick update, brief/shallow news, listing/non-article or other frozen non-target class;
- at least two frozen substantive depth signals.

Acquisition status and body-product class remain separate.

## Source decision floor

For each source's 15 primary-plausible rows:

- >=10 body-evaluable;
- >=5 body-confirmed Standard Longreads;
- confirmed supply across >=2 first-surface strata.

Possible Track V source states:

- `SUPPORTS_S3_COUNTERFACTUAL`
- `SOURCE_OR_SURFACE_RESTRICTED_REVIEW`
- `DOES_NOT_SUPPORT_S3`
- `NOT_EVALUABLE`

Passing Track V does not authorize S3.

## Execution stopping rules

- canary not READY -> stop before panel requests;
- manifest/hash drift -> invalidate before panel requests;
- network safety cap -> stop and record explicit safety censoring;
- production-isolation breach -> invalidate immediately;
- article-level acquisition failure -> record and continue only according to pre-frozen path/budget;
- no replacement;
- no early stopping based on observed longread rate;
- no budget increase after seeing outcomes;
- no pooling with v1.
