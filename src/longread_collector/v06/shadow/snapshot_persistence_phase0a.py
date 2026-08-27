"""Phase 0A durable Discovery-snapshot persistence invariant.

PR-7.3.8 made every individual snapshot cell losslessly writable under Google
Sheets' cell-size ceiling. Phase 0A adds a control-plane readback invariant on
top of that frozen writer: after the batch append returns, the persisted Sheet
must contain exactly the expected number of rows for the current collector run.

This module changes no Discovery, Acquisition, L4, L5 or L6 semantics. It adds
only persistence verification and audit state used by the scheduled shadow
control plane. The installed recall writer remains the PR-7.3.8 function itself;
Phase 0A attaches an opt-in post-persistence verifier so historical writer
identity/version contracts remain intact.

Phase 3 reliability hardening also routes the snapshot sheet's idempotent
lookup/header/readback operations through the shared bounded 429/503 retry
helper. Sheet creation and append-only snapshot writes remain single-attempt so
an ambiguous response can never be replayed into duplicate evidence.
"""

from __future__ import annotations

from typing import Any

from gspread.exceptions import WorksheetNotFound

from ... import recall_instrumentation as _recall
from ...models import DiscoveredURL, ExtractedArticle
from ...sheets import _retry_sheet_call
from . import snapshot_persistence_v0738 as _pr738
from .snapshot_persistence_v0735 import (
    SNAPSHOT_OVERFLOW_HEADERS,
    SNAPSHOT_OVERFLOW_SHEET,
)

SNAPSHOT_PERSISTENCE_VERSION = "snapshot-persistence-v0.6-phase0a"
_INSTALLED = False


class SnapshotPersistenceInvariantError(RuntimeError):
    """Raised when durable snapshot readback does not match the captured input."""


def _read_header_with_retry(ws: Any) -> list[Any]:
    """Read a worksheet header with bounded retry for transient Sheets errors."""

    return list(_retry_sheet_call(lambda: ws.row_values(1)))


def _ensure_snapshot_sheet_with_retry(store: Any) -> Any:
    """Resolve the main snapshot sheet without treating transient errors as absence."""

    try:
        ws = _retry_sheet_call(
            lambda: store.book.worksheet("collector_discovery_snapshot")
        )
    except (WorksheetNotFound, KeyError):
        # gspread raises WorksheetNotFound; small mapping-style adapters and
        # historical test doubles use KeyError for the same missing-title
        # condition. No other exception is converted into sheet absence.
        # Creation is deliberately single-attempt: retrying an ambiguous create
        # could produce a duplicate worksheet with the same intended identity.
        ws = store.book.add_worksheet(
            title="collector_discovery_snapshot",
            rows=10000,
            cols=len(_recall.SNAPSHOT_HEADERS),
        )
        ws.append_row(_recall.SNAPSHOT_HEADERS, value_input_option="RAW")
        ws.freeze(rows=1)

    header = _read_header_with_retry(ws)
    if header != _recall.SNAPSHOT_HEADERS:
        raise ValueError(
            "collector_discovery_snapshot header mismatch: "
            f"expected {len(_recall.SNAPSHOT_HEADERS)} columns, got {len(header)}"
        )
    return ws


def _ensure_overflow_sheet_with_retry(store: Any) -> Any:
    """Resolve the overflow sheet without converting 429/503 into false absence."""

    try:
        ws = _retry_sheet_call(lambda: store.book.worksheet(SNAPSHOT_OVERFLOW_SHEET))
    except (WorksheetNotFound, KeyError):
        # Keep the same narrow missing-sheet compatibility as the main snapshot
        # resolver; transient API errors have already been handled by retry.
        # As above, keep non-idempotent creation/header append single-attempt.
        ws = store.book.add_worksheet(
            title=SNAPSHOT_OVERFLOW_SHEET,
            rows=20000,
            cols=len(SNAPSHOT_OVERFLOW_HEADERS),
        )
        ws.append_row(SNAPSHOT_OVERFLOW_HEADERS, value_input_option="RAW")
        ws.freeze(rows=1)

    header = _read_header_with_retry(ws)
    if header != SNAPSHOT_OVERFLOW_HEADERS:
        raise ValueError(
            f"{SNAPSHOT_OVERFLOW_SHEET} header mismatch: "
            f"expected {len(SNAPSHOT_OVERFLOW_HEADERS)} columns, got {len(header)}"
        )
    return ws


def _persisted_run_row_count(ws: Any, run_id: str) -> int:
    """Count durable snapshot rows for one collector run from the run-id column."""

    values = _retry_sheet_call(lambda: ws.col_values(2))
    return sum(str(value).strip() == run_id for value in values[1:])


def _verify_persisted_snapshot(
    *,
    store: Any,
    run_id: str,
    state: _recall.SnapshotCaptureState,
    written_rows: int,
) -> int:
    """Fail closed unless writer count and durable readback equal capture count."""

    expected_rows = len(state.discoveries)
    state.snapshot_readback_performed = True
    state.snapshot_persisted_rows = 0

    if written_rows != expected_rows:
        raise SnapshotPersistenceInvariantError(
            "snapshot writer count mismatch: "
            f"run_id={run_id} expected={expected_rows} writer_returned={written_rows}"
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


def verified_append_snapshot_rows(
    store: Any,
    *,
    run_id: str,
    pair_list: list[tuple[DiscoveredURL, ExtractedArticle]],
    state: _recall.SnapshotCaptureState,
) -> int:
    """Direct helper used by regression tests; production uses the PR-7.3.8 hook."""

    written = _pr738.hardened_append_snapshot_rows(
        store,
        run_id=run_id,
        pair_list=pair_list,
        state=state,
    )
    return _verify_persisted_snapshot(
        store=store,
        run_id=run_id,
        state=state,
        written_rows=written,
    )


def install_snapshot_persistence_invariant() -> None:
    """Install PR-7.3.8 persistence plus durable, retry-safe Phase 0A reads."""

    global _INSTALLED
    if _INSTALLED:
        return
    _pr738.install_snapshot_persistence_hardening()
    _recall._ensure_snapshot_sheet = _ensure_snapshot_sheet_with_retry
    _pr738._ensure_overflow_sheet = _ensure_overflow_sheet_with_retry
    _pr738.install_post_persistence_verifier(_verify_persisted_snapshot)
    _INSTALLED = True


__all__ = [
    "SNAPSHOT_PERSISTENCE_VERSION",
    "SnapshotPersistenceInvariantError",
    "install_snapshot_persistence_invariant",
    "verified_append_snapshot_rows",
]
