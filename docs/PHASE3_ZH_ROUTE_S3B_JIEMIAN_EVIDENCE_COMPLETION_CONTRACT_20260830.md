# Phase 3 — Jiemian S3-B minimal evidence-completion contract

Date: 2026-08-30 BJT  
Status: **DESIGN FROZEN / BODY EXECUTION NOT AUTHORIZED**  
Proposed version: `zh-route-shadow-s3b-jiemian-evidence-completion-v1`

## 1. Question

S3-A v1.1 has already established that the historical Control simulator is exact for all four frozen runs and that qualified Jiemian Treatment candidates enter the same fixed 32-attempt portfolio on three intended dates. The remaining structural ambiguity is caused by exactly four first-stage Treatment identities whose body outcomes were not observed before S3.

S3-B asks only:

> What are the terminal body/product outcomes of those four mechanically identified blockers, and after substituting those frozen outcomes back into S3-A v1.1, what is the sign of the fixed-32 body-confirmed Standard Longread utility delta?

S3-B is not a new source-quality sample and must not reopen S2-B denominators.

## 2. Exact immutable manifest

No sampling remains. The manifest is the exact unique blocker set emitted by S3-A v1.1:

1. `https://jiemian.com/article/14977759.html` — 白云山转型半年：创新投入增长、王牌仍在下滑 — `jiemian_medicine`;
2. `https://jiemian.com/article/14997276.html` — 从“长寿”到“健康长寿”，抗衰开始走进整个生活 — `jiemian_consumer`;
3. `https://jiemian.com/article/14998723.html` — ST香雪“保壳”命悬一线 — `jiemian_medicine`;
4. `https://jiemian.com/article/15018993.html` — 衰老干预技术的高价困局，瑞拓龄能否打破成本壁垒 — `jiemian_medicine`.

Rules:

- exactly 4 article-attempt slots;
- no replacement;
- no attractive-title substitution;
- no later natural Jiemian exposure may enter this manifest;
- canonical identity fixed before any S3-B body outcome is observed.

## 3. Existing-evidence gate

Before any network request, re-check exact canonical identities against:

- frozen S2-B reviewed ledger;
- Production `article_cache` as read-only evidence only;
- historical `extraction_log`;
- immutable prior experiment artifacts.

If comparable body evidence already exists for an identity by execution time, reuse it and do not re-request that article. The currently observed state on 2026-08-30 is 0/4 reusable bodies.

This gate reduces unnecessary acquisition but may not change the four-item denominator.

## 4. Provider-readiness gate

Because this is an acquisition-dependent measurement, the execution must first run the same fixed, non-sample unauthenticated Jina Reader readiness canaries validated in S2-B v2.1.

- canary requests are not sample attempts;
- Jina Authorization header must not be sent;
- free-tier pacing must remain at least 3.1 seconds between actual Jina Reader GETs;
- if the provider gate is not READY, stop before any of the four article requests;
- do not compensate by expanding Firecrawl use when the provider-wide gate fails.

## 5. Bounded acquisition path

If later separately authorized, use the already-observed measurement-only acquisition semantics that worked for Jiemian in S2-B v2.1:

1. direct first-party HTML where already implemented by the isolated measurement runner;
2. unauthenticated, paced Jina Reader;
3. bounded Firecrawl fallback only after earlier paths fail.

Frozen limits for this four-item completion:

- article-attempt slots: 4;
- no replacement;
- Firecrawl logical fallback cap: **2**;
- actual-network hard safety cap, including canaries/retries: **40**;
- no Production `article_cache` writes;
- no Editor writes;
- no live Collector selection writes;
- isolated audit persistence only.

Acquisition failure is evidence and must not be hidden through replacement.

## 6. Body/product rubric

Reuse the frozen S2-B Standard Longread rubric without modification.

`body_confirmed_standard_longread` requires all:

1. correct canonical standalone article;
2. usable body >=2500 content chars;
3. not an academic paper, primary document, PR/corporate promotion, event recap, digest/roundup, brief update, listing or other product-scope non-target;
4. at least two depth signals among substantive interviews/multi-source reporting, interpreted quantitative/documentary evidence, causal/strategic/mechanism analysis, historical/competitive/regulatory context, or original field/investigative/primary-source reporting beyond routine company copy.

Other frozen terminal product classes remain:

- `body_confirmed_non_target`;
- `body_borderline_insufficient`;
- non-usable acquisition -> `not_evaluable`.

Length is necessary, not sufficient.

## 7. Replay integration

After all four identities have immutable terminal outcomes, do not rerank or resample anything.

Instead:

1. feed those exact outcomes into the already-frozen S3-A v1.1 structural replay;
2. rerun the same four historical fixed-32 counterfactuals;
3. identify final Treatment entrants and displaced Control identities;
4. use existing Control body/historical outcomes where comparable;
5. if a displaced Control identity lacks enough comparable evidence to sign the aggregate body-confirmed utility delta, emit a new minimal **Control-side** evidence-completion manifest before any additional body request.

The four Treatment results may not be used to redesign selection rules before the fixed-32 comparison is closed.

## 8. Decision states

S3-B itself may produce:

### `FIXED32_UTILITY_SIGN_POSITIVE`

Comparable evidence is sufficient and aggregate body-confirmed Standard Longread delta is >0 across the frozen four-run cohort.

### `FIXED32_UTILITY_SIGN_NONPOSITIVE`

Comparable evidence is sufficient and aggregate delta is <=0.

### `FIXED32_UTILITY_NEEDS_CONTROL_EVIDENCE`

Treatment blocker evidence is complete but displaced-Control uncertainty can still flip the aggregate sign.

### `NOT_EVALUABLE_ACQUISITION`

Too many of the four mechanically required Treatment blockers remain not evaluable to determine downstream schedule/utility.

None of these states automatically authorizes S4 or Production.

## 9. Explicit non-goals

This contract does not authorize:

- the four body requests themselves;
- S4 Shadow selection;
- source registry changes;
- source/host-cap changes;
- max-32 budget changes;
- Production acquisition changes;
- Editor connection;
- Track F changes;
- Scheduler changes;
- automatic promotion.

Production remains **SHADOW / NOT_READY**.
