# Phase 3 Google Sheets Reliability Hardening — 2026-08-27

Status: controlled Shadow/runtime reliability change. No recommendation, source-selection, capacity, L4/L5/L6, Editor or promotion semantics are changed.

## Trigger evidence

Two distinct scheduled failures were observed in the Phase-2 evidence window:

- 2026-08-23 `zh_evening`: Google Sheets 503 during preflight; collection never started.
- 2026-08-25 `intl_early`: Google Sheets 429 per-user/per-minute quota failure after partial telemetry had already been persisted.

The previous `article_cache` upsert path amplified request pressure:

1. read article-id column;
2. read the article cache again for 30-day source identity;
3. for every existing article, issue `row_values(existing_row)`;
4. for every existing article, issue an individual `update`.

For a batch with N existing articles, this creates O(N) extra read/write requests even though the same rows can be obtained from one cache snapshot and updated in one batch request.

## v1 hardening

### 1. Remove the article-cache N+1 read pattern

`upsert_articles()` now performs one `article_cache.get_all_values()` call and derives in memory:

- `article_id -> sheet row`;
- existing row values needed to preserve `first_seen_at_bj`, `selected_run_id`, `selected_status` and `notes`;
- the 30-day canonical-source set.

It no longer calls `row_values()` for each existing article.

### 2. Batch idempotent existing-row updates

Existing article updates are emitted in one worksheet `batch_update` call rather than one `update` request per row.

New-row appends remain a single append operation and are **not blindly retried**. A 503 response can be ambiguous: the append may already be durable even if the client did not receive a success response, and blind replay could create duplicate article rows.

### 3. Bounded transient retry

A shared retry helper retries only explicit Google Sheets transient conditions:

- HTTP 429 / quota exhausted;
- HTTP 503 / service unavailable.

Default backoff is bounded at 1s, 2s, 4s. Other errors fail immediately.

The helper is used for reads and idempotent updates, including workbook open, worksheet lookup, preflight reads, cache reads and batch updates.

### 4. Duplicate-safe terminal run ledger retry

`collector_runs` is append-only evidence, so it cannot be blindly retried. After a retryable append failure:

1. wait with bounded backoff;
2. read back the run-id column;
3. if the same `collector_run_id` is already durable, treat the append as successful;
4. retry the append only when readback proves the run id is absent.

This protects terminal-run completeness without knowingly creating duplicate ledger rows.

## Snapshot / Final Recall compatibility

The change is made in the underlying `GoogleSheetStore.upsert_articles()` implementation only.

The existing recall instrumentation still wraps that same method. The wrapper continues to call the optimized underlying upsert and then persists the immutable `collector_discovery_snapshot`. Phase 0A snapshot readback remains unchanged.

Therefore this PR does **not** bypass or relax:

- discovery snapshot persistence;
- expected/persisted row equality;
- snapshot readback;
- durable-run evidence requirements in Final Recall v1.3.1.

## Acceptance tests

Regression tests require:

- only 429/503 retry;
- non-transient errors fail immediately;
- two existing article updates use one cache read, zero `row_values`, and one batch update;
- mixed new/existing batches retain a single cache read;
- historical fields preserved by the old per-row read remain preserved;
- a 503 whose append was already durable does not duplicate `collector_runs`;
- a 503 whose readback proves absence retries once and creates exactly one run row.

## Explicit non-goals

This change does not:

- alter source routes or source rotation;
- alter source/host caps or the 32-body-attempt budget;
- change ranking or classification;
- enable `v06_primary`;
- connect Collector to the 07:35 Editor;
- enable production `article_cache` consumption;
- enable automatic promotion.

Further optimization of other Sheets writers may be considered only after natural Shadow evidence shows where remaining request pressure occurs.
