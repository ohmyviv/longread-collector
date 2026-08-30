# Phase 3 — Yicai acquisition forensic v1

Date: 2026-08-30 BJT  
Status: **AUTHORIZED / ISOLATED FORENSIC / PRODUCTION UNCHANGED**  
Version: `yicai-acquisition-forensic-v1`

## 1. Question

S2-B v2.1 left Yicai `NOT_EVALUABLE`: only 2/15 primary plausible targets became body-evaluable. The observed acquisition pattern was 21/21 direct first-party `ConnectTimeout`, 21/21 unauthenticated Jina HTTP 422, and 2/10 successful primary Firecrawl logical calls.

This forensic asks only:

> Can a small, pre-frozen diagnostic isolate whether hostname identity/redirect behavior, Jina URL acceptance, or Firecrawl provider behavior explains a material part of the Yicai acquisition censoring?

It does not re-estimate Yicai content utility and does not supplement the S2-B denominator.

## 2. Frozen diagnostic set

Universe: the exact Yicai `primary_plausible` rows in the already-frozen S2-B 40-item manifest.

Selection is deterministic and does not use acquisition outcomes:

- seed: `yicai-acquisition-forensic-v1-20260830`;
- strata: `yicai_auto`, `yicai_finance`, `yicai_kechuang`, `yicai_news_breadth`;
- select exactly one URL per stratum;
- rank by SHA-256 of `seed | first_surface | canonical_url`;
- choose the lowest digest in each stratum;
- exact count = 4; canonical URLs unique.

No sample replacement after results are observed.

## 3. Frozen request matrix

For each of the four selected article paths, test two hostname forms:

1. persisted canonical `https://yicai.com/...`;
2. first-party `https://www.yicai.com/...` with the same path/query.

### Direct first-party HTTP

- one GET per host variant;
- no retry;
- `follow_redirects=true`;
- browser-like headers matching the current direct-HTML path;
- connect/read timeout recorded separately;
- record DNS resolution, status, final URL, redirect history, latency, response bytes and a body fingerprint when any body is returned.

Maximum direct HTTP: **8**.

### Jina Reader

- unauthenticated Reader only; no Authorization header;
- one GET per host variant;
- no retry;
- >=3.1 seconds between Jina requests;
- record status, latency, returned bytes and Jina `URL Source` when available.

Maximum Jina HTTP: **8**.

### Firecrawl

- only the four persisted canonical URLs;
- one raw `/v2/scrape` POST per URL;
- no client retry;
- no host-variant expansion;
- record terminal HTTP status, latency, `creditsUsed` if returned and markdown characters on success.

Maximum Firecrawl HTTP/logical calls: **4**.

Total hard actual HTTP cap: **20** (contract safety cap **25**). DNS resolver calls are logged separately and do not add hidden HTTP retries.

## 4. Decision rules

The forensic may emit multiple diagnostic signals; a signal is not a Production fix.

### `HOST_IDENTITY_EXPLAINS_DIRECT_FAILURE`

Use only if at least 3/4 `www` direct variants become HTTP-successful while the corresponding canonical host variants fail at connection/transport level, with consistent redirect/host evidence.

### `JINA_HOST_NORMALIZATION_SIGNAL`

Use only if at least 3/4 paired URLs differ materially by host form in Jina acceptance (e.g. one host consistently 2xx and the other 4xx), under identical no-auth pacing.

### `FIRECRAWL_PROVIDER_INSTABILITY_SIGNAL`

Use when fewer than 2/4 single-attempt Firecrawl probes succeed and failures are dominated by retryable 408/5xx provider responses.

### `NO_SINGLE_CAUSE_ISOLATED`

Use when no pre-frozen rule above is met or multiple mechanisms remain entangled.

### `NOT_EVALUABLE`

Use when the diagnostic itself is blocked by missing credentials, network-wide runner failure, manifest drift, or the actual HTTP cap.

## 5. Interpretation boundary

This forensic does not prove intentional publisher blocking. It must not infer a Production adapter from one small diagnostic.

Any source-specific adapter proposal requires a separate review after this evidence is closed. No change may rewrite S2-B v2.1 acquisition outcomes or its `2/15` evaluability denominator.

## 6. Explicit non-goals

Not authorized here:

- compensating S2-B rerun;
- Yicai S3 admission;
- Production Jina/direct/Firecrawl changes;
- source/host/body-budget changes;
- article_cache or Editor writes;
- Track F;
- Scheduler work.

Production remains **SHADOW / NOT_READY**.
