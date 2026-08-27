from __future__ import annotations

from types import SimpleNamespace

import pytest
from gspread.exceptions import WorksheetNotFound

from longread_collector import recall_instrumentation as recall
from longread_collector.models import DiscoveredURL
from longread_collector.recall_instrumentation import CapturedDiscovery, SnapshotCaptureState
from longread_collector.v06.shadow import snapshot_persistence_phase0a as phase0a
from longread_collector.v06.shadow import snapshot_persistence_v0738 as pr738
from longread_collector.v06.shadow.snapshot_persistence_v0735 import (
    SNAPSHOT_OVERFLOW_HEADERS,
    SNAPSHOT_OVERFLOW_SHEET,
)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeSheetError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"sheet error {status_code}")
        self.response = FakeResponse(status_code)


class FakeWorksheet:
    def __init__(self, header: list[str]) -> None:
        self.rows: list[list[object]] = [list(header)]
        self.row_values_calls = 0
        self.col_values_calls = 0
        self.append_rows_calls = 0
        self.row_failures: list[BaseException] = []
        self.col_failures: list[BaseException] = []
        self.append_failure: BaseException | None = None

    def row_values(self, index: int):
        self.row_values_calls += 1
        if self.row_failures:
            raise self.row_failures.pop(0)
        return list(self.rows[index - 1]) if 1 <= index <= len(self.rows) else []

    def col_values(self, index: int):
        self.col_values_calls += 1
        if self.col_failures:
            raise self.col_failures.pop(0)
        return [row[index - 1] if len(row) >= index else "" for row in self.rows]

    def append_row(self, row, **kwargs):
        self.rows.append(list(row))

    def append_rows(self, rows, **kwargs):
        self.append_rows_calls += 1
        if self.append_failure is not None:
            raise self.append_failure
        self.rows.extend(list(row) for row in rows)

    def freeze(self, rows: int) -> None:
        return None


class FakeBook:
    def __init__(self) -> None:
        self.sheets: dict[str, FakeWorksheet] = {}
        self.lookup_failures: dict[str, list[BaseException]] = {}
        self.worksheet_calls: dict[str, int] = {}
        self.add_calls: list[str] = []

    def worksheet(self, title: str):
        self.worksheet_calls[title] = self.worksheet_calls.get(title, 0) + 1
        failures = self.lookup_failures.get(title, [])
        if failures:
            raise failures.pop(0)
        if title not in self.sheets:
            raise WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, *, title: str, rows: int, cols: int):
        self.add_calls.append(title)
        header = (
            recall.SNAPSHOT_HEADERS
            if title == "collector_discovery_snapshot"
            else SNAPSHOT_OVERFLOW_HEADERS
        )
        ws = FakeWorksheet(header=[])
        self.sheets[title] = ws
        return ws


class FakeStore:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(timezone="Asia/Shanghai")
        self.book = FakeBook()


def _disable_sleep(monkeypatch) -> None:
    monkeypatch.setattr("longread_collector.sheets.time.sleep", lambda _: None)


def test_snapshot_lookup_429_retries_without_false_sheet_creation(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()
    ws = FakeWorksheet(recall.SNAPSHOT_HEADERS)
    store.book.sheets["collector_discovery_snapshot"] = ws
    store.book.lookup_failures["collector_discovery_snapshot"] = [FakeSheetError(429)]

    resolved = phase0a._ensure_snapshot_sheet_with_retry(store)

    assert resolved is ws
    assert store.book.worksheet_calls["collector_discovery_snapshot"] == 2
    assert store.book.add_calls == []


def test_overflow_lookup_503_retries_without_false_sheet_creation(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()
    ws = FakeWorksheet(SNAPSHOT_OVERFLOW_HEADERS)
    store.book.sheets[SNAPSHOT_OVERFLOW_SHEET] = ws
    store.book.lookup_failures[SNAPSHOT_OVERFLOW_SHEET] = [FakeSheetError(503)]

    resolved = phase0a._ensure_overflow_sheet_with_retry(store)

    assert resolved is ws
    assert store.book.worksheet_calls[SNAPSHOT_OVERFLOW_SHEET] == 2
    assert store.book.add_calls == []


def test_only_true_worksheet_absence_creates_snapshot_sheet(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()

    ws = phase0a._ensure_snapshot_sheet_with_retry(store)

    assert ws is store.book.sheets["collector_discovery_snapshot"]
    assert store.book.add_calls == ["collector_discovery_snapshot"]
    assert ws.rows[0] == recall.SNAPSHOT_HEADERS


def test_nontransient_lookup_error_propagates_without_creation(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()
    store.book.lookup_failures["collector_discovery_snapshot"] = [FakeSheetError(400)]

    with pytest.raises(FakeSheetError):
        phase0a._ensure_snapshot_sheet_with_retry(store)

    assert store.book.worksheet_calls["collector_discovery_snapshot"] == 1
    assert store.book.add_calls == []


def test_header_and_durable_readback_retry_transient_errors(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()
    ws = FakeWorksheet(recall.SNAPSHOT_HEADERS)
    ws.row_failures = [FakeSheetError(429)]
    ws.col_failures = [FakeSheetError(503)]
    row = [""] * len(recall.SNAPSHOT_HEADERS)
    row[1] = "RUN-READBACK"
    ws.rows.append(row)
    store.book.sheets["collector_discovery_snapshot"] = ws

    assert phase0a._ensure_snapshot_sheet_with_retry(store) is ws
    assert ws.row_values_calls == 2
    assert phase0a._persisted_run_row_count(ws, "RUN-READBACK") == 1
    assert ws.col_values_calls == 2


def test_snapshot_append_only_write_is_not_blindly_retried(monkeypatch) -> None:
    _disable_sleep(monkeypatch)
    store = FakeStore()
    ws = FakeWorksheet(recall.SNAPSHOT_HEADERS)
    ws.append_failure = FakeSheetError(503)
    store.book.sheets["collector_discovery_snapshot"] = ws

    state = SnapshotCaptureState(
        query_group="zh_evening",
        discoveries=[
            CapturedDiscovery(
                item=DiscoveredURL(
                    url="https://example.com/story",
                    title="Story",
                    discovery_method="rss",
                ),
                prefilter_status="accepted_for_extraction",
            )
        ],
    )

    monkeypatch.setattr(recall, "_ensure_snapshot_sheet", phase0a._ensure_snapshot_sheet_with_retry)
    monkeypatch.setattr(pr738, "_POST_PERSISTENCE_VERIFIER", None)

    with pytest.raises(FakeSheetError):
        pr738.hardened_append_snapshot_rows(
            store,
            run_id="RUN-APPEND-AMBIGUOUS",
            pair_list=[],
            state=state,
        )

    assert ws.append_rows_calls == 1
