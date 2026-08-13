from __future__ import annotations

from types import SimpleNamespace

import pytest

from longread_collector.models import DiscoveredURL
from longread_collector.pipeline_v051 import _snapshot_persistence_audit
from longread_collector.recall_instrumentation import (
    CapturedDiscovery,
    SNAPSHOT_HEADERS,
    SnapshotCaptureState,
)
from longread_collector.v06.shadow import snapshot_persistence_phase0a as phase0a


class _FakeWorksheet:
    def __init__(self) -> None:
        self.rows: list[list[object]] = [list(SNAPSHOT_HEADERS)]

    def col_values(self, index: int):
        return [row[index - 1] if len(row) >= index else "" for row in self.rows]

    def row_values(self, index: int):
        if 1 <= index <= len(self.rows):
            return list(self.rows[index - 1])
        return []


class _FakeBook:
    def __init__(self, ws: _FakeWorksheet) -> None:
        self.ws = ws

    def worksheet(self, title: str):
        if title != "collector_discovery_snapshot":
            raise KeyError(title)
        return self.ws


class _FakeStore:
    def __init__(self, ws: _FakeWorksheet) -> None:
        self.settings = SimpleNamespace(timezone="Asia/Shanghai")
        self.book = _FakeBook(ws)


def _state(count: int = 2) -> SnapshotCaptureState:
    discoveries = []
    for index in range(count):
        discoveries.append(
            CapturedDiscovery(
                item=DiscoveredURL(
                    url=f"https://example.com/story/{index}",
                    title=f"Story {index}",
                    discovery_method="rss",
                ),
                prefilter_status="accepted_for_extraction",
            )
        )
    return SnapshotCaptureState(query_group="pre_report", discoveries=discoveries)


def _append_run_rows(ws: _FakeWorksheet, run_id: str, count: int) -> None:
    for index in range(count):
        row = [""] * len(SNAPSHOT_HEADERS)
        row[0] = f"snapshot-{index}"
        row[1] = run_id
        ws.rows.append(row)


def test_verifier_records_exact_durable_readback() -> None:
    ws = _FakeWorksheet()
    store = _FakeStore(ws)
    state = _state(2)
    run_id = "COL-PHASE0A-SUCCESS"
    _append_run_rows(ws, run_id, 2)

    persisted = phase0a._verify_persisted_snapshot(
        store=store,
        run_id=run_id,
        state=state,
        written_rows=2,
    )

    assert persisted == 2
    assert state.snapshot_readback_performed is True
    assert state.snapshot_persisted_rows == 2


def test_verifier_raises_when_durable_rows_are_missing() -> None:
    ws = _FakeWorksheet()
    store = _FakeStore(ws)
    state = _state(2)
    run_id = "COL-PHASE0A-MISSING"
    _append_run_rows(ws, run_id, 1)

    with pytest.raises(
        phase0a.SnapshotPersistenceInvariantError,
        match=r"expected=2 persisted=1",
    ):
        phase0a._verify_persisted_snapshot(
            store=store,
            run_id=run_id,
            state=state,
            written_rows=2,
        )

    assert state.snapshot_readback_performed is True
    assert state.snapshot_persisted_rows == 1


def test_verifier_raises_when_writer_return_count_is_wrong() -> None:
    ws = _FakeWorksheet()
    store = _FakeStore(ws)
    state = _state(2)

    with pytest.raises(
        phase0a.SnapshotPersistenceInvariantError,
        match=r"expected=2 writer_returned=1",
    ):
        phase0a._verify_persisted_snapshot(
            store=store,
            run_id="COL-PHASE0A-WRITER-MISMATCH",
            state=state,
            written_rows=1,
        )

    assert state.snapshot_readback_performed is True
    assert state.snapshot_persisted_rows == 0


def test_run_audit_fails_closed_on_snapshot_error() -> None:
    state = _state(2)
    state.snapshot_readback_performed = True
    state.snapshot_persisted_rows = 1
    state.snapshot_error = (
        "SnapshotPersistenceInvariantError: durable readback mismatch: "
        "expected=2 persisted=1"
    )
    values: dict[str, object] = {
        "final_status": "success",
        "error_message": "",
        "notes": "classification_version=fixture",
    }

    audit = _snapshot_persistence_audit(values, state)

    assert audit["status"] == "failed"
    assert values["final_status"] == "failed"
    assert "SnapshotPersistenceInvariantError" in str(values["error_message"])
    assert "snapshot_persistence_status=failed" in str(values["notes"])
    assert "snapshot_expected_rows=2" in str(values["notes"])
    assert "snapshot_persisted_rows=1" in str(values["notes"])


def test_run_audit_preserves_success_only_after_matching_readback() -> None:
    state = _state(3)
    state.snapshot_readback_performed = True
    state.snapshot_persisted_rows = 3
    values: dict[str, object] = {
        "final_status": "success",
        "error_message": "",
        "notes": "",
    }

    audit = _snapshot_persistence_audit(values, state)

    assert audit == {
        "status": "success",
        "expected_rows": 3,
        "persisted_rows": 3,
        "readback_performed": True,
        "error": "",
    }
    assert values["final_status"] == "success"
    assert "snapshot_persistence_status=success" in str(values["notes"])


def test_legacy_unverified_capture_does_not_false_fail_without_known_error() -> None:
    state = _state(1)
    values: dict[str, object] = {"final_status": "success", "notes": ""}

    audit = _snapshot_persistence_audit(values, state)

    assert audit["status"] == "unverified"
    assert values["final_status"] == "success"
    assert "snapshot_persistence_status=unverified" in str(values["notes"])
