# 2026-08-13 Phase 0A natural acceptance

Phase 0A's durable Discovery snapshot invariant is naturally accepted on the first scheduled Collector run after PR #86 merged.

## Natural run

```text
GitHub Actions run: 31692575791
workflow schedule: 2026-08-13 17:50:00 BJT
collector_run_id: COL-20260813-184710-BJT-zh_evening
started_at_bj: 2026-08-13 18:47:10
completed_at_bj: 2026-08-13 18:51:11
workflow start delay: ~57 minutes
main head: 7819a91bfcc4ef3f98df7d9427c397f1f08e5d13
query_group: zh_evening
```

The delayed workflow start is not a Phase 0A failure. It becomes an explicit Phase 0B scheduling-freshness dimension and must be separated from per-source rotation/rescan freshness.

## Acceptance gate

All required Phase 0A conditions passed in `collector-result.json`:

```text
final_status=success

discovery_snapshot_status=success

discovery_snapshot_readback_performed=true

discovery_snapshot_rows=152

discovery_snapshot_persisted_rows=152

v06_shadow.snapshot_persistence_version=snapshot-persistence-v0.6-phase0a

v06_shadow.full_snapshot_invariant=true
```

The scheduled workflow's explicit `Verify durable Discovery snapshot` step passed.

Central persistence was independently reconciled in the live workbook:

```text
collector_runs row 72:
  collector_run_id=COL-20260813-184710-BJT-zh_evening
  final_status=success
  notes include:
    snapshot_persistence_status=success
    snapshot_expected_rows=152
    snapshot_persisted_rows=152
    snapshot_readback_performed=TRUE

collector_discovery_snapshot:
  exact collector_run_id matches=152
  contiguous rows=6783..6934
```

Therefore:

```text
Phase 0A = NATURAL ACCEPTED / DONE
Phase 0B = READY TO START
```

This acceptance changes no Editorial/Promotion gate:

```text
Transport Gate: READY
Editorial Gate: NOT_READY
Promotion Gate: SHADOW
```

## Phase 0B measurement split

Phase 0B must separate two clocks:

```text
A. workflow execution freshness
   scheduled_at -> collector started_at

B. source rotation freshness
   source last_attempt / last_success
   article published_at -> next source scan
   source last_success -> editorial/report cutoff
```

Do not attribute GitHub scheduler delay to source rotation, and do not attribute source-rotation gaps to GitHub scheduler delay. Measure both before changing cadence or route logic.

Phase 0B remains measurement-first. It does not authorize L4/L5/L6 changes, Acquisition/network-budget expansion, Collector promotion, or a new generic crawler.