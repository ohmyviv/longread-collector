# Phase 3 Yicai Acquisition Forensic v1 Closeout — 2026-08-30

## Status

`COMPLETED / DIAGNOSTIC ROOT CAUSE RESOLVED`

This closes the single authorized Yicai acquisition-forensic execution. It does **not** rewrite S2-B v2.1 denominators or outcomes, and it does **not** authorize a Production acquisition change.

## Immutable execution evidence

- workflow run: `33283813581`
- execution head: `da7dd8b15f21552627beebdaefbecef5da270554`
- artifact: `yicai-acquisition-forensic-v1-33283813581`
- artifact id: `9723863698`
- artifact ZIP digest: `sha256:8707b8f43586fb6cc650ff7114394f67a86f48eb3a0b56723b8ad7c041b23b93`
- manifest digest: `b605f7999db3f86e24796bf929b40da3bd3cca79994bed3a13c3ad6a80cabebb`
- manifest count: 4
- actual HTTP requests: 20
- theoretical HTTP count: 20
- hard cap: 25
- Jina Authorization header sent: `false`
- Sheet writes: 0
- Production mutations: 0
- article_cache writes: 0
- Editor writes: 0

The one-shot run completed successfully and the result contract passed.

## Frozen diagnostic panel

Exactly one URL was selected deterministically from each frozen Yicai first-surface stratum:

1. `yicai_auto` — `https://yicai.com/news/103335887.html`
2. `yicai_finance` — `https://yicai.com/news/103337023.html`
3. `yicai_kechuang` — `https://yicai.com/news/103335587.html`
4. `yicai_news_breadth` — `https://yicai.com/news/103337397.html`

Each URL received exactly five no-retry probes:

- direct canonical host (`yicai.com`)
- direct `www` host (`www.yicai.com`)
- unauthenticated Jina canonical host
- unauthenticated Jina `www` host
- one raw Firecrawl canonical-host scrape

## Observed probe matrix

| Path | 4-URL result | Interpretation |
|---|---:|---|
| Direct `yicai.com` | 0/4 usable; 4/4 `ConnectTimeout` | canonical-host transport path is not reliable in this runner environment |
| Direct `www.yicai.com` | 4/4 HTTP 200 | the underlying pages are directly reachable when the host identity is normalized to `www` |
| Jina + `yicai.com` | 0/4 usable; 4/4 HTTP 422 | Jina does not normalize this canonical host into a usable target |
| Jina + `www.yicai.com` | 4/4 HTTP 200 with article payload | the Jina path is viable when given the `www` host explicitly |
| Firecrawl + `yicai.com` | 0/4 usable; 3x HTTP 408, 1x HTTP 500 | Firecrawl is unstable/unusable for this exact canonical-host diagnostic and cannot be treated as a reliable rescue path |

DNS evidence was also consistent across all four samples:

- `yicai.com` resolved to `203.107.60.192`;
- `www.yicai.com` resolved to a separate CDN address set (`163.181.246.188`–`163.181.246.195`).

## Causal conclusion

The earlier Yicai acquisition failure is **not evidence that Yicai article bodies are inherently unavailable**.

The bounded forensic establishes two reproducible mechanisms:

1. **Host-identity / transport mismatch**: `yicai.com` and `www.yicai.com` are operationally non-equivalent in the acquisition environment. The canonical host timed out while the `www` host succeeded 4/4.
2. **Provider URL-normalization mismatch**: unauthenticated Jina returned 422 for `yicai.com` but 200 for the corresponding `www.yicai.com` target 4/4.

Firecrawl simultaneously showed provider-path instability and should not be used to obscure the primary mechanism.

Therefore the source-specific diagnostic state is:

`YICAI_ACQUISITION_MECHANISM_RESOLVED_HOST_NORMALIZATION`

with secondary signal:

`FIRECRAWL_PROVIDER_INSTABILITY_SIGNAL`.

## What this does and does not prove

This proves that a narrow, deterministic host normalization from article identity host `yicai.com` to acquisition request host `www.yicai.com` is sufficient to make all four sampled URLs directly reachable and Jina-readable in the diagnostic environment.

It does **not** prove:

- Yicai article quality;
- Yicai S2-B precision;
- portfolio-wide S2 readiness;
- that Firecrawl should be removed globally;
- that Production should immediately change acquisition semantics;
- that canonical identity URLs should be rewritten to `www`.

Canonical identity and acquisition-request identity must remain separate concepts.

## Safest next engineering step

If a Yicai remediation is later authorized, the narrowest admissible change is source-specific acquisition-host normalization:

- keep canonical identity as the existing canonical article identity;
- for Yicai article-body acquisition only, derive/request the `www.yicai.com` transport variant before treating direct/Jina failure as terminal;
- do not change ranking, source selection, route registry, source/host caps, freshness, S2 denominators, or product classification;
- add regression fixtures requiring canonical identity stability and acquisition-host normalization separation;
- validate offline/Shadow before any Production use.

No Production remediation is authorized by this closeout.

## Execution hygiene

The one-shot forensic workflow and trigger are retired after artifact capture. The merged surface must contain only the frozen diagnostic implementation/tests/docs and this closeout, with no standing forensic execution workflow.
