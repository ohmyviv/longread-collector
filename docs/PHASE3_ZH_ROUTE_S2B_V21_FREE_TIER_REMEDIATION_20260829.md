# Phase 3 — S2-B v2.1 Track V free-tier remediation

Date: 2026-08-29

## Observed provider split

Authenticated Track V canary (Actions `33253218617`) used the configured `JINA_API_KEY` and returned HTTP 402 Payment Required on 3/3 fixed public non-sample canaries. The gate failed closed: panel requests 0/40, Firecrawl 0.

A separate provider-diagnosis run (Actions `33253874709`) repeated the same three fixed canaries with **no Authorization header**. Result: 3/3 HTTP 200, body sizes 2669 / 17428 / 34228 bytes, provider status `FREE_TIER_READY`.

Jina's current public Reader documentation states that basic Reader usage is available without an API key at 20 RPM, while API-key requests are tracked/charged by key. Taken together, current evidence localizes the blocker to the configured authenticated key/account/token/billing path rather than Reader service availability or GitHub-runner connectivity.

## Remediation decision

No purchase, top-up, billing mutation, credential replacement or secret exposure is performed.

Track V receives a new isolated acquisition version:

`zh-route-shadow-s2b-body-observability-v2.1-free-tier`

It intentionally does not send the configured Jina API key. It preserves the exact frozen 40-item manifest SHA `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`, no-replacement rule, direct-first-party -> Jina -> bounded Firecrawl ordering, source-reserved paid fallback cap 20, body rubric, source-level information floor and hard network safety cap 230.

## Free-tier safety contract

The no-key Reader path is paced at a global minimum interval of 3.1 seconds between every actual Jina HTTP GET, including retry attempts. This is strictly below the documented 20 RPM ceiling. Pacing applies only to `canary:jina` and `panel:jina` contexts inside this measurement runner; direct HTML and Firecrawl are unaffected.

The production `JinaReaderClient`, natural Collector, production acquisition chain, GitHub secret and Track F are unchanged.

## Execution gate

The already-authorized Track V panel may proceed only if the v2.1 runner's own fixed 3-canary gate returns `READY`. If the gate is not READY, panel requests remain zero.

One-time execution workflow/trigger, if used, must be removed before merge. No standing Track V network entrypoint may land on main.

## Boundaries

Unchanged / not authorized:
- Track F;
- S3;
- production/Editor wiring;
- natural Collector source/cap/body budget changes;
- scheduler changes;
- Jina billing/top-up/account purchase;
- silent pooling of v1, v2 canary-blocked and v2.1 results.
