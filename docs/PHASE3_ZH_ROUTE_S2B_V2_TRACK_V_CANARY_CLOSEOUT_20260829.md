# Phase 3 Chinese Route — S2-B v2 Track V Canary Closeout

## Formal status

**CANARY-BLOCKED / NOT_EVALUABLE_PROVIDER_NOT_READY**

This record closes the single explicitly authorized S2-B v2 Track V attempt made on 2026-08-29. It does not authorize a re-canary, Jina account/billing/credential mutation, Track F, S3, Production, Editor wiring, Route/source/cap changes, natural Collector body-budget changes, or Scheduler changes.

## 1. Frozen experiment identity

- experiment track: `VALUE`
- acquisition version: `zh-route-shadow-s2b-body-observability-v2`
- frozen panel size: 40
- frozen manifest SHA-256: `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`
- panel composition remained exactly the pre-outcome v1/v2 panel:
  - Jiemian-depth: 15 primary plausible + 4 uncertainty exploration
  - Yicai: 15 primary plausible + 6 uncertainty exploration
- paid Firecrawl authorization: max 20 logical fallback calls
  - Jiemian primary reservation: 10
  - Yicai primary reservation: 10
  - uncertainty rows: 0 paid fallback reservation
- actual-request safety cap: 230
- no replacement and no v1/v2 pooling.

Execution evidence:

- GitHub Actions run: `33253218617`
- execution commit: `96ffc19128ab33f1aaac7af1ee4e910392f472a0`
- immutable artifact: `s2b-v2-track-v-33253218617`
- artifact id: `9715007457`
- GitHub artifact digest: `sha256:850cfa4a591086b077bac7761318ada8d0479e24415e3759a741f774880a3320`

## 2. Provider-readiness gate

The gate used three pre-frozen public non-sample URLs, independent of Jiemian and Yicai:

1. `https://www.iana.org/help/example-domains`
2. `https://www.python.org/about/`
3. `https://www.gnu.org/philosophy/free-sw.en.html`

Readiness required at least 2/3 successful Jina reads with HTTP 2xx and at least 300 returned body characters, while fewer than two canaries could terminate in provider auth/quota/payment status `{401,402,403,429}`.

Observed:

| Canary | Jina result | Body chars |
| --- | ---: | ---: |
| IANA example domains | HTTP 402 | 0 |
| Python About | HTTP 402 | 0 |
| GNU Free Software | HTTP 402 | 0 |

Aggregate:

- success = `0/3`
- provider failure = `3/3`
- Jina API key present = `TRUE`
- gate verdict = `PROVIDER_NOT_READY`

The provider-level gate therefore failed before any sample request was allowed.

## 3. Fail-closed execution result

The execution wrapper behaved according to the frozen contract:

- `panel_requests_started = FALSE`
- panel article-body requests = `0/40`
- actual HTTP requests = `3`, all Jina canaries
- Firecrawl logical calls = `0`
- paid Firecrawl credits consumed by Track V = `0` where observable
- authorized Firecrawl cap 20 = completely unused
- body-evaluable panel rows = `0`
- live Sheet writes = `0`
- `article_cache` writes = `0`
- Editor writes = `0`
- Production changes = `0`

This is a successful execution-integrity outcome even though the body-value experiment itself is not evaluable: the canary prevented an invalid second acquisition-censored panel run.

## 4. Causal interpretation

The canaries deliberately used unrelated public domains. All three still received Jina `HTTP 402 Payment Required`, and the execution environment reported that a Jina API key was configured.

This strengthens, but does not overclaim, the current classification:

`JINA_PROVIDER_ACCOUNT_QUOTA_PAYMENT_STATE / CROSS_DOMAIN_PROVIDER_NOT_READY`

Supported:

- the failure is not specific to Jiemian or Yicai;
- it is not explained simply by absence of a configured Jina API key;
- the problem occurs before Route body value can be measured.

Not established:

- whether the provider's internal cause is billing state, quota exhaustion, account tier, key entitlement, provider policy, or another account-level restriction;
- whether Production-equivalent acquisition is feasible under another provider state;
- whether the frozen 40-item panel has sufficient body-confirmed Route value.

## 5. What this run does NOT say

Do not infer any of the following:

- `0/40` body quality;
- low Jiemian or Yicai longread precision;
- Track V failure caused by Route design;
- Firecrawl budget insufficiency;
- Production acquisition feasibility;
- S3 readiness.

There were zero panel-body requests, so there is no new panel numerator or denominator beyond the canary-level provider evidence.

S2-B v1 remains separately immutable as:

`CLOSED / NOT_EVALUABLE_FOR_SOURCE_UTILITY / ACQUISITION-CENSORED`

Its three observable bodies remain v1 evidence and are not pooled into v2.

## 6. Isolated persistence

The standalone S2 audit workbook now contains:

- `s2b_v2_provider_readiness`
- `s2b_v2_summary`

Readback fixed the following facts:

- `execution_status = PROVIDER_NOT_READY`
- `canary_success_count = 0`
- `canary_provider_failure_count = 3`
- `jina_api_key_present = TRUE`
- `panel_requests_started = FALSE`
- `panel_article_requests = 0`
- `actual_http_requests_total = 3`
- `firecrawl_logical_calls = 0`
- `body_evaluable_count = 0`
- `track_v_decision = NOT_EVALUABLE_PROVIDER_NOT_READY`
- Track F = `NOT_AUTHORIZED / NOT_STARTED`
- S3 = `NOT_AUTHORIZED / NOT_STARTED`
- Production = `SHADOW / NOT_READY`.

Issue #148 contains the provider-blocker evidence and the v2 canary follow-up.

## 7. Next decision boundary

The next meaningful decision is **not** to rerun the 40-item panel and not to enlarge Firecrawl automatically.

It is:

`JINA_PROVIDER_ACCOUNT_QUOTA_PAYMENT_REMEDIATION`

Before any remediation, separately decide whether to inspect/change Jina billing, quota, account entitlement or credentials. A subsequent canary, if authorized after remediation, must be recorded as a new provider-readiness observation; it must not erase this 2026-08-29 `PROVIDER_NOT_READY` result.

Until then:

- no re-canary;
- no panel request;
- no Firecrawl paid fallback use;
- no Track F;
- no S3;
- no Production/Editor change;
- no Scheduler change.
