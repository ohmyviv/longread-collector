"""Phase 0A durable Discovery-snapshot persistence invariant.

PR-7.3.8 made every individual snapshot cell losslessly writable under Google
Sheets' cell-size ceiling. Phase 0A adds a control-plane readback invariant on
top of that frozen writer: after the batch append returns, the persisted Sheet
must contain exactly the expected number of rows for the current collector run.

This module changes no Discovery, Acquisition, L4, L5 or L6 semantics. It adds
only persistence verification and audit state used by the scheduled shadow
control plane.
"""

from __future__ import annotations

from typing import Any

from ... import recall_instrumentation as _recall
from ...models import DiscoveredURL, ExtractedArticle
from .snapshot_persistence_v0738 import (
    hardened_append_snapshot_rows as _pr738_append_snapshot_rows,
)

SNAPSHOT_PERSISTENCE_VERSION = "snapshot-persistence-v0.6-phase0a"
_INSTALLED = False


class SnapshotPersistenceInvariantError(RuntimeError):
    """Raised when durable snapshot readback does not match the captured input."""


def _persisted_run_row_count(ws: Any, run_id: str) -> int:
    """Count durable snapshot rows for one collector run from the run-id column."""

    values = ws.col_values(2)
    return sum(str(value).strip() == run_id for value in values[1:])


def verified_append_snapshot_rows(
    store: Any,
    *,
    run_id: str,
    pair_list: list[tuple[DiscoveredURL, ExtractedArticle]],
    state: _recall.SnapshotCaptureState,
) -> int:
    """Persist with PR-7.3.8, then fail closed on durable readback mismatch."""

    expected_rows = len(state.discoveries)
    # These attributes are intentionally sidecar-only and do not alter the
    # persisted Sheet schema or the historical SnapshotCaptureState contract.
    state.snapshot_readback_performed = True
    state.snapshot_persisted_rows = 0

    written = _pr738_append_snapshot_rows(
        store,
        run_id=run_id,
        pair_list=pair_list,
        state=state,
    )
    if written != expected_rows:
        raise SnapshotPersistenceInvariantError(
            "snapshot writer count mismatch: "
            f"run_id={run_id} expected={expected_rows} writer_returned={written}"
        )

    ws = _recall._ensure_snapshot_sheet(store)
    persisted_rows = _persisted_run_row_count(ws, run_id)
    state.snapshot_persisted_rows = persisted_rows
    if persisted_rows != expected_rows:
        raise SnapshotPersistenceInvariantError(
            "snapshot durable readback mismatch: "
            f"run_id={run_id} expected={expected_rows} persisted={persisted_rows}"
        )
    return persisted_rows


def install_snapshot_persistence_invariant() -> None:
    """Install Phase 0A verification over the frozen PR-7.3.8 writer."""

    global _INSTALLED
    if _INSTALLED:
        return
    _recall._append_snapshot_rows = verified_append_snapshot_rows
    _INSTALLED = True


__all__ = [
    "SNAPSHOT_PERSISTENCE_VERSION",
    "SnapshotPersistenceInvariantError",
    "install_snapshot_persistence_invariant",
    "verified_append_snapshot_rows",
]
