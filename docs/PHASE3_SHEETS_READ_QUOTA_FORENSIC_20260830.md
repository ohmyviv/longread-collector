# Phase 3 — Google Sheets read-quota forensic — 2026-08-30

## Status

`ROOT_CAUSE_RESOLVED / PRODUCTION_REMEDIATION_NOT_AUTHORIZED`

This note explains the natural failure of Collector run `COL-20260830-060231-BJT-pre_report` / GitHub Actions run `33277548009`. It is a reliability forensic only. It does not change source selection, ranking, route portfolio, freshness, body-attempt caps, Editor wiring, Scheduler semantics, or Production promotion state.

## Durable truth

The failed `collector_runs` row reported:

- `snapshot_expected_rows=197`
- `snapshot_persisted_rows=0`
- `snapshot_readback_performed=TRUE`
- final status `failed`
- terminal Sheets error: `429 Read requests per minute per user`

Post-hoc durable readback proves the snapshot append itself succeeded:

- `collector_discovery_snapshot`: exactly **197/197** rows are present for the run, at rows 19496–19692;
- `article_cache`: **32** rows carry the same `discovery_run_id`;
- `extraction_log`: **0** rows exist in the 06:xx BJT attempt window.

Therefore the correct state is not “snapshot persistence = zero”. The run entered a **partial-durability** state: snapshot and article-cache writes completed, post-append verification exhausted read quota, then extraction-log persistence also failed before completion.

## Exact failure sequence

The Actions log establishes this order:

1. scheduled workflow executes `longread-collector doctor` immediately before the collector;
2. collector performs discovery and extraction work and appends the 197-row Discovery snapshot;
3. Phase 0A post-persistence verifier re-resolves `collector_discovery_snapshot` through `Spreadsheet.worksheet()`;
4. that metadata read receives Sheets API 429 for the per-user/per-project read quota;
5. current bounded retry delays are only `1s, 2s, 4s`;
6. the retry window therefore ends while the minute-level quota window is still exhausted;
7. execution continues far enough to call `append_extraction_logs`;
8. resolving the `extraction_log` worksheet again receives the same 429 and terminates the run.

No same-repository concurrent Actions workflow was present in the relevant window. External users of the same service account cannot be globally ruled out, but concurrency is not required to explain the event.

## First-principles read-budget reconstruction

The relevant Sheets limit is **60 read requests per minute per user per project**. A conservative static lower bound for the current scheduled path is already above that ceiling.

### Preflight `doctor`

Approximate lower bound: **15 reads**.

Major contributors:

- open spreadsheet / metadata;
- `book.worksheets()` inventory;
- `health_check()` performs another worksheet inventory;
- four separate `load_queries(group)` calls;
- two separate `load_source_registry(language)` calls;
- each loader requires worksheet resolution plus a data read.

### Collector through extraction-log persistence

Approximate lower bound: **50 reads** before/at the failing `extraction_log` worksheet lookup.

Major contributors:

- a new process creates a new `GoogleSheetStore`, so the doctor’s reads are not reused;
- inherited pipeline wrappers independently reload runtime config and query data;
- source selection and discovery reload source registry/config state;
- fallback-budget accounting repeatedly queries extraction-log state;
- source-run coverage, historical dedupe and cache-state reads add further requests;
- repeated `Spreadsheet.worksheet()` calls fetch spreadsheet metadata;
- snapshot persistence resolves/header-checks the snapshot sheet and then re-resolves it for durable readback.

### Conservative total

`15 + 50 = 65 reads`

This is deliberately a lower bound and excludes some optional/fail-open telemetry reads. The observed workflow consumed the preflight and collection path within roughly one minute, so a structural quota breach is expected without any external collision.

## Root-cause classification

`STRUCTURAL_SHEETS_READ_AMPLIFICATION + QUOTA_WINDOW_INADEQUATE_RETRY + PARTIAL_DURABILITY_STATE_MODEL`

It is **not** classified as:

- snapshot data loss;
- service-account credential failure;
- a general Google Sheets outage;
- Scheduler root cause;
- source-specific acquisition failure.

## Remediation hierarchy

The system should reduce demand before relying on retry.

1. **Remove or radically cheapen scheduled preflight.** A full doctor immediately before every scheduled run duplicates the same Sheets reads and consumes a material fraction of the minute quota.
2. **Introduce run-scoped read reuse.** Worksheet handles, runtime config, scheduled-group query rows and source-registry rows should be read once per run and reused across wrapper layers where semantics allow.
3. **Separate worksheet identity from repeated metadata discovery.** Repeated `Spreadsheet.worksheet(title)` calls should not incur a fresh full sheet-metadata fetch when the workbook topology is unchanged during a run.
4. **Make 429 semantics quota-aware.** The `1s → 2s → 4s` policy is useful for short transient faults but is not a credible recovery strategy for an exhausted one-minute quota window. Any quota-specific wait is a safety net, not the primary fix.
5. **Represent persistence uncertainty correctly.** `readback_failed_after_append` / `persistence_unverified` must be distinguishable from a proven `persisted_rows=0` state.
6. **Retain single-attempt append semantics.** An ambiguous write response must never be blindly replayed and create duplicate evidence.
7. **Add partial-durability reconciliation tests.** A run with snapshot/article-cache success and later extraction-log failure must remain auditable and repairable without rewriting historical evidence.

## Acceptance contract for any future runtime patch

Before a Production-impacting change can be considered:

- deterministic read-budget instrumentation must show the scheduled path comfortably below 60 reads/min without depending on quota refill timing;
- post-append 429 cannot be represented as observed zero persistence;
- ambiguous snapshot append remains non-retried;
- full-snapshot fail-closed semantics remain intact;
- no source/ranking/freshness/cap/32-body/Editor/auto-promotion/Scheduler semantic change is bundled into the reliability patch;
- tests must cover partial durability and quota-window behavior;
- Production merge requires separate review/authorization.

## Current engineering state

- Issue: `#159`
- branch: `phase3/sheets-read-quota-hardening-v2`
- this branch may contain measurement/read-budget helpers and candidate remediation code for review;
- **no Production runtime fix is authorized or merged by this forensic.**
