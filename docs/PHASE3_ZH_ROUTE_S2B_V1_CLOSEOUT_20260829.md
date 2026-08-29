# Phase 3 Chinese Route S2-B v1 Closeout — 2026-08-29

## Status

**S2-B v1: CLOSED / NOT_EVALUABLE for source-level utility**

- S3: **NOT_AUTHORIZED / NOT_STARTED**
- Production: **SHADOW / NOT_READY**
- Natural Collector / Editor / article_cache / Scheduler: unchanged
- No compensating rerun, no replacement sample, no post-hoc Firecrawl budget increase.

## Frozen experiment identity

- S2-B sample-plan version: `zh-route-shadow-s2b-sample-plan-v1`
- S2-B result-contract version: `zh-route-shadow-s2b-result-contract-v1`
- Frozen S2-A cohort: 129 canonical-unique items
- Sample size: 40 article-attempt slots
- Primary plausible: 30
- Uncertainty exploration: 10
- Replacement: false
- Seed: `zh-route-shadow-s2b-20260829-v1`
- Manifest SHA-256: `7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b`
- Frozen semantic/runtime acquisition baseline: `a380c68920c1de26f1e703b721d7eb2195900002`
- Control acquisition semantics for this experiment: legacy `extract_article()` = Jina Reader first, budgeted Firecrawl fallback.

## Evidence chain

### 1. Manifest materialization

GitHub Actions run: `33241941984`

The materialization stage read only the standalone S2-A audit workbook, emitted exactly 40 deterministic rows, and did not perform article-body requests. The manifest was persisted into the standalone audit workbook and read back before body acquisition.

### 2. Bounded body acquisition

GitHub Actions run: `33242246140`

Preconditions passed before acquisition:

- frozen acquisition files matched semantic/runtime baseline;
- immutable manifest artifact downloaded from run `33241941984`;
- manifest row count = 40;
- frozen cohort row count = 129;
- manifest SHA-256 matched the frozen value;
- isolated concurrency = 2;
- isolated Firecrawl fallback cap = 3.

Observed acquisition outcome:

- article-attempt slots: 40
- actual HTTP network requests: 43
- Jina requests: 40
- Jina outcome: 40/40 `HTTP 402 Payment Required`
- Firecrawl requests actually sent: 3
- usable bodies: 3
- acquisition failed / not evaluable: 37

The remaining 37 rows were not replaced and were not retried with a larger fallback budget.

### 3. Human body review

The three usable bodies were reviewed against the pre-frozen S2-B body rubric rather than treating the Collector classifier as ground truth.

All 3/3 were classified as `body_confirmed_standard_longread`:

1. 《蒂花之秀还想当新一代年轻人的“青春好朋友”》 — 8,612 chars
2. 《厨房纸到底能不能擦吃的？》 — 9,998 chars
3. 《快乐猴开进盒马地盘大闹社区零售》 — 7,632 chars

Each had at least two substantive depth signals. This 3/3 result is descriptive only and is **not** a source-level precision estimate because acquisition censoring was extreme.

### 4. Machine validation of reviewed ledger

GitHub Actions validation run: `33242599717`

Validator output:

- `valid=true`
- sample rows = 40
- result rows = 40
- missing URLs = 0
- unexpected URLs = 0
- contract errors = 0
- network requests total = 43
- Firecrawl calls total = 3

By source:

- `jiemian-depth`: 3 usable, 16 acquisition failed; 3 confirmed standard longreads, 16 not evaluable
- `yicai`: 0 usable, 21 acquisition failed; 21 not evaluable

By primary-plausible denominator:

- `jiemian-depth`: 3 evaluable / 15 attempted
- `yicai`: 0 evaluable / 15 attempted

The frozen decision floor required at least 10/15 evaluable primary-plausible items before source-level S3 judgment. Neither source met that floor.

## Formal interpretation

### What this experiment established

1. The deterministic S2-B sample and result ledger are internally valid and fully auditable.
2. The legacy frozen acquisition chain was observable only for 3/40 rows under the execution-time Jina 402 state and Firecrawl cap=3.
3. All three usable bodies were genuine standard longreads, so the observed evidence does **not** support a conclusion that Route metadata expansion is producing low-value body content.
4. The experiment also does **not** support a positive source-level utility claim because 37/40 rows were censored by acquisition failure.

### What this experiment did not establish

It did not establish:

- Jiemian or Yicai source-level longread precision;
- weighted frozen-cohort body survival;
- fixed-32 incremental utility;
- S3 readiness;
- production readiness;
- that Jiemian/Yicai themselves caused the acquisition failures.

The observed Jina 402 pattern is cross-domain and is therefore more consistent with provider/account/quota/payment-state behavior than a source-specific access failure. That diagnosis is operational context, not a reason to rewrite the frozen S2-B v1 result.

## Decision

**S2-B v1 is CLOSED as NOT_EVALUABLE for source-level utility.**

No automatic continuation into S3 is permitted.

Any attempt to obtain a sufficiently observable body-validation window must be treated as a **new versioned experiment** with a separately frozen acquisition contract and explicit authorization. It must not overwrite or reinterpret the 37 censored v1 rows.

## Execution-surface retirement

After validation succeeded, the one-shot branch trigger files and branch-only S2-B Actions workflow were removed from the merge candidate. The repository retains only the deterministic materialization / execution / validation scripts and this closeout record for forensic reproducibility. No standing S2-B network workflow remains.
