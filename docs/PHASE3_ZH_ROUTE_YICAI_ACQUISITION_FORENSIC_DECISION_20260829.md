# Phase 3 — Yicai source-specific acquisition forensic decision boundary

Date: 2026-08-29 BJT  
Status: **FORENSIC SIGNAL RECORDED / REMEDIATION NOT STARTED**

## Observed v2.1 signal

The S2-B v2.1 Track V execution removed the provider-wide authenticated Jina HTTP 402 blocker by using the explicitly measurement-only no-Authorization Reader path. The fixed public canaries passed 3/3 HTTP 200 and no Jina panel request hit HTTP 429.

However, all 21 frozen Yicai panel identities remained difficult to observe:

- direct first-party HTML: 21/21 `ConnectTimeout`;
- unauthenticated Jina Reader: 21/21 HTTP 422;
- Firecrawl primary reservation: 10 logical calls, 2 terminal successes, 8 terminal failures;
- two Firecrawl successes produced body-confirmed Standard Longreads;
- Yicai primary body evaluability remained 2/15, below the frozen 10/15 information floor.

## What this does and does not establish

Observed fact:

`Yicai source-specific acquisition observability is inadequate under the frozen v2.1 measurement chain.`

Not established:

- that Yicai content quality is low;
- that Yicai intentionally blocks all acquisition;
- that the canonical hostname is wrong;
- that adding `www.` would fix the issue;
- that Jina 422 is caused by the source rather than URL identity/provider handling;
- that Firecrawl is structurally incapable of acquiring Yicai.

The exact causal mechanism remains unproven.

## Required next forensic design

Any follow-up must be a new, read-only/measurement-only forensic version and may not rewrite v2.1. It should pre-freeze a tiny non-outcome-selected diagnostic set and isolate hypotheses one at a time, for example:

1. canonical hostname/redirect identity (`yicai.com` vs the first-party resolved canonical surface) without changing article identity;
2. direct network reachability and DNS/TLS/redirect timing from the runner;
3. Jina request URL normalization/acceptance behavior on Yicai URLs;
4. Firecrawl terminal 500/408 response pattern and retry accounting;
5. only after those checks, whether a source-specific acquisition adapter is justified.

No 40-item compensating rerun, production acquisition change, Track F change, source-cap change or S3 inclusion for Yicai is authorized by this document.

## Current decision

`YICAI_S2B = NOT_EVALUABLE`

Yicai remains outside any S3 proposal until source-level body observability reaches the pre-frozen information floor or a new decision explicitly changes the evidence contract.
