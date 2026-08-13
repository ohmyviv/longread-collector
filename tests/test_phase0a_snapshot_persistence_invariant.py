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


def test_verified_writer_records_exact_durable_readback(monkeypatch: pytest.MonkeyPatch) -> None:
    ws = _FakeWorksheet()
    store = _FakeStore(ws)
    state = _state(2)
    run_id = "COL-PHASE0A-SUCCESS"

    def fake_pr738(store, *, run_id, pair_list, state):
        for index in range(len(state.discoveries)):
            row = [""] * len(SNAPSHOT_HEADERS)
            row[0] = f"snapshot-{index}"
            row[1] = run_id
            store.book.ws.rows.append(row)
        return len(state.discoveries)

    monkeypatch.setattr(phase0a, "_pr738_append_snapshot_rows", fake_pr738)

    written = phase0a.verified_append_snapshot_rows(
        store,
        run_id=run_id,
        pair_list=[],
        state=state,
    )

    assert written == 2
    assert state.snapshot_readback_performed is True
    assert state.snapshot_persisted_rows == 2


def test_verified_writer_raises_when_durable_rows_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = _FakeWorksheet()
    store = _FakeStore(ws)
    state = _state(2)
    run_id = "COL-PHASE0A-MISSING"

    def fake_pr738(store, *, run_id, pair_list, state):
        row = [""] * len(SNAPSHOT_HEADERS)
        row[0] = "snapshot-only-one"
        row[1] = run_id
        store.book.ws.rows.append(row)
        # Simulate an API path that reports the expected writer count although
        # durable readback can see only one row.
        return len(state.discoveries)

    monkeypatch.setattr(phase0a, "_pr738_append_snapshot_rows", fake_pr738)

    with pytest.raises(
        phase0a.SnapshotPersistenceInvariantError,
        match=r"expected=2 persisted=1",
    ):
        phase0a.verified_append_snapshot_rows(
            store,
            run_id=run_id,
            pair_list=[],
            state=state,
        )

    assert state.snapshot_readback_performed is True
    assert state.snapshot_persisted_rows == 1


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
