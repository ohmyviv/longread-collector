# Phase 0A — durable Discovery snapshot invariant

## Trigger

The 2026-08-13 benchmark reconciliation found that the 48-hour pre-report window
contained 1,300 run-reported Discovery observations but only 1,114 persisted
`collector_discovery_snapshot` rows. The entire 186-row block for:

```text
COL-20260812-042957-BJT-pre_report
```

was absent, while 32 `article_cache` rows from the same run survived.

The historical persistence root cause is already known. PR #83 / PR-7.3.8 was
opened from that exact blocker: a non-`metadata_json` snapshot field exceeded
Google Sheets' 50,000-character single-cell ceiling. PR-7.3.8 extended the
lossless overflow mechanism to all 29 snapshot cells.

Phase 0A therefore does **not** redesign the overflow writer. It closes the
remaining control-plane defect: a snapshot persistence failure could be captured
in memory as `snapshot_error` while the Collector run row still reported
`final_status=success`, and the scheduled GitHub Actions job did not independently
verify durable Sheet persistence.

## Scope

Phase 0A is measurement/control-plane only. It changes no:

- source registry membership;
- Discovery candidates, ranking, caps or scheduling;
- Acquisition route or budget;
- L4 canonical URL/date/source/PageSurface semantics;
- L5 (`editorial-judge-v0.6-pr7.2`);
- L6 portfolio policy;
- production promotion state.

Collector remains `SHADOW`.

## Invariant

For every scheduled `v06_shadow` Collector run:

```text
expected_snapshot_rows
    = number of captured Discovery observations

persisted_snapshot_rows
    = exact count of collector_discovery_snapshot rows
      whose collector_run_id equals the current run_id

PASS iff:
    snapshot append returned expected_snapshot_rows
    AND durable readback was performed
    AND persisted_snapshot_rows == expected_snapshot_rows
    AND no snapshot persistence exception was recorded
```

The readback uses only the `collector_run_id` column. It does not reconstruct,
retry, backfill or fabricate missing historical rows.

## Failure behavior

On a write exception or durable count mismatch:

1. the existing recall hook records `snapshot_error`;
2. the Collector run ledger is projected fail-closed:
   `final_status=failed`;
3. the existing `error_message` records the snapshot persistence error;
4. `notes` receives stable audit markers without adding Sheet columns:

```text
snapshot_persistence_status
snapshot_expected_rows
snapshot_persisted_rows
snapshot_readback_performed
```

5. the returned JSON exposes:

```text
discovery_snapshot_rows
discovery_snapshot_persisted_rows
discovery_snapshot_readback_performed
discovery_snapshot_status
discovery_snapshot_error   # on failure
```

6. the scheduled workflow performs an explicit `jq` assertion after writing
   `collector-result.json`; a failed invariant makes the GitHub Actions job red,
   while the `if: always()` artifact step still archives the result JSON.

No `article_cache` rollback is attempted. Snapshot persistence is an audit
invariant, not a transaction boundary around already completed acquisition.

## Versioning

PR-7.3.8's all-cell lossless writer remains frozen and is wrapped by:

```text
snapshot-persistence-v0.6-phase0a
```

The semantic Collector runtime remains:

```text
collector-v0.6-pr7.3.9
```

This keeps measurement hardening separate from L4 semantic versioning.

## Regression coverage

Phase 0A tests verify:

- exact durable readback passes;
- a writer that reports the expected count but leaves fewer durable rows raises
  `SnapshotPersistenceInvariantError`;
- a snapshot error changes a would-be successful run to `final_status=failed`;
- matching readback preserves success;
- a legacy capture without Phase-0A readback remains `unverified` rather than
  being falsely failed solely because the new writer was not installed;
- v0.6 `full_snapshot_invariant` requires durable readback and persisted count
  equality in addition to the existing in-memory capture checks.

## Acceptance

CI is engineering evidence only. After merge, the next scheduled natural run
must show at minimum:

```text
final_status=success
discovery_snapshot_status=success
discovery_snapshot_readback_performed=true
discovery_snapshot_persisted_rows == discovery_snapshot_rows
v06_shadow.snapshot_persistence_version=snapshot-persistence-v0.6-phase0a
```

This does not by itself make the Editorial Gate ready and does not authorize
Collector promotion.
