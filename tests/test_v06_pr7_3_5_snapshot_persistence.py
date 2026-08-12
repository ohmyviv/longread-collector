from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from longread_collector.models import DiscoveredURL
from longread_collector.recall_instrumentation import (
    CapturedDiscovery,
    SNAPSHOT_HEADERS,
    SnapshotCaptureState,
)
from longread_collector.v06.shadow.snapshot_persistence_v0735 import (
    SNAPSHOT_METADATA_CHUNK_SIZE,
    SNAPSHOT_METADATA_INLINE_LIMIT,
    SNAPSHOT_OVERFLOW_HEADERS,
    SNAPSHOT_OVERFLOW_SHEET,
    SNAPSHOT_PERSISTENCE_VERSION,
    hardened_append_snapshot_rows,
)
from longread_collector.v06.shadow.snapshot_persistence_v0738 import (
    SNAPSHOT_PERSISTENCE_VERSION as CURRENT_SNAPSHOT_PERSISTENCE_VERSION,
    hardened_append_snapshot_rows as current_hardened_append_snapshot_rows,
)


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


class _FakeWorksheet:
    def __init__(self, title: str, *, fail_append: bool = False) -> None:
        self.title = title
        self.rows: list[list[object]] = []
        self.fail_append = fail_append

    def append_row(self, row, value_input_option=None):
        self.rows.append(list(row))

    def append_rows(self, rows, value_input_option=None, table_range=None):
        if self.fail_append:
            raise RuntimeError(f"append failed for {self.title}")
        self.rows.extend(list(row) for row in rows)

    def row_values(self, index: int):
        if 1 <= index <= len(self.rows):
            return list(self.rows[index - 1])
        return []

    def freeze(self, rows: int) -> None:
        return None


class _FakeBook:
    def __init__(
        self,
        *,
        fail_overflow: bool = False,
        fail_main: bool = False,
    ) -> None:
        self.sheets: dict[str, _FakeWorksheet] = {}
        self.fail_overflow = fail_overflow
        self.fail_main = fail_main

    def worksheet(self, title: str):
        if title not in self.sheets:
            raise KeyError(title)
        return self.sheets[title]

    def add_worksheet(self, *, title: str, rows: int, cols: int):
        ws = _FakeWorksheet(
            title,
            fail_append=(
                (self.fail_overflow and title == SNAPSHOT_OVERFLOW_SHEET)
                or (self.fail_main and title == "collector_discovery_snapshot")
            ),
        )
        self.sheets[title] = ws
        return ws


class _FakeStore:
    def __init__(
        self,
        *,
        fail_overflow: bool = False,
        fail_main: bool = False,
    ) -> None:
        self.settings = SimpleNamespace(timezone="Asia/Shanghai")
        self.book = _FakeBook(
            fail_overflow=fail_overflow,
            fail_main=fail_main,
        )


def _state(metadata: dict[str, object]) -> SnapshotCaptureState:
    item = DiscoveredURL(
        url="https://example.com/story/oversized",
        title="Oversized snapshot metadata",
        discovery_method="rss",
        metadata=metadata,
    )
    return SnapshotCaptureState(
        query_group="intl_early",
        discoveries=[
            CapturedDiscovery(
                item=item,
                prefilter_status="accepted_for_extraction",
            )
        ],
    )


def test_small_metadata_remains_inline_and_does_not_create_overflow_sheet() -> None:
    metadata = {"source_id": "fixture", "marker": "small"}
    store = _FakeStore()

    written = hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-SMALL",
        pair_list=[],
        state=_state(metadata),
    )

    assert written == 1
    assert SNAPSHOT_OVERFLOW_SHEET not in store.book.sheets
    main = store.book.sheets["collector_discovery_snapshot"]
    assert main.rows[0] == SNAPSHOT_HEADERS
    metadata_index = SNAPSHOT_HEADERS.index("metadata_json")
    assert main.rows[1][metadata_index] == json.dumps(
        metadata,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_oversized_metadata_is_losslessly_chunked_with_manifest_and_hash() -> None:
    metadata = {
        "source_id": "fixture",
        "large_payload": "界" * (SNAPSHOT_METADATA_INLINE_LIMIT + 55_000),
        "tail": "完整保留",
    }
    expected = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    assert len(expected) > 50_000

    store = _FakeStore()
    written = hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-OVERFLOW",
        pair_list=[],
        state=_state(metadata),
    )

    assert written == 1
    main = store.book.sheets["collector_discovery_snapshot"]
    metadata_index = SNAPSHOT_HEADERS.index("metadata_json")
    manifest_cell = str(main.rows[1][metadata_index])
    assert len(manifest_cell) < SNAPSHOT_METADATA_INLINE_LIMIT
    manifest = json.loads(manifest_cell)["_snapshot_metadata_overflow"]
    assert manifest["version"] == SNAPSHOT_PERSISTENCE_VERSION
    assert manifest["sheet"] == SNAPSHOT_OVERFLOW_SHEET
    assert manifest["chars"] == len(expected)
    assert manifest["utf16_units"] == _utf16_units(expected)
    assert manifest["sha256"] == hashlib.sha256(expected.encode("utf-8")).hexdigest()

    overflow = store.book.sheets[SNAPSHOT_OVERFLOW_SHEET]
    assert overflow.rows[0] == SNAPSHOT_OVERFLOW_HEADERS
    chunks = sorted(overflow.rows[1:], key=lambda row: int(row[4]))
    assert len(chunks) == manifest["chunks"]
    assert all(len(str(row[6])) <= SNAPSHOT_METADATA_CHUNK_SIZE for row in chunks)
    assert all(_utf16_units(str(row[6])) <= 40_000 for row in chunks)
    reconstructed = "".join(str(row[6]) for row in chunks)
    assert reconstructed == expected
    assert hashlib.sha256(reconstructed.encode("utf-8")).hexdigest() == manifest["sha256"]
    assert all(str(row[0]) == manifest["snapshot_id"] for row in chunks)
    assert all(str(row[1]) == "COL-SNAPSHOT-OVERFLOW" for row in chunks)


def test_astral_unicode_overflows_on_utf16_units_before_python_length_limit() -> None:
    metadata = {"emoji_payload": "😀" * 30_000}
    expected = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    assert len(expected) < SNAPSHOT_METADATA_INLINE_LIMIT
    assert _utf16_units(expected) > SNAPSHOT_METADATA_INLINE_LIMIT

    store = _FakeStore()
    hardened_append_snapshot_rows(
        store,
        run_id="COL-SNAPSHOT-EMOJI",
        pair_list=[],
        state=_state(metadata),
    )

    main = store.book.sheets["collector_discovery_snapshot"]
    metadata_index = SNAPSHOT_HEADERS.index("metadata_json")
    manifest = json.loads(str(main.rows[1][metadata_index]))[
        "_snapshot_metadata_overflow"
    ]
    assert manifest["utf16_units"] == _utf16_units(expected)
    overflow = store.book.sheets[SNAPSHOT_OVERFLOW_SHEET]
    chunks = sorted(overflow.rows[1:], key=lambda row: int(row[4]))
    assert "".join(str(row[6]) for row in chunks) == expected
    assert all(_utf16_units(str(row[6])) <= 40_000 for row in chunks)


def test_overflow_write_failure_propagates_and_main_snapshot_is_not_claimed() -> None:
    metadata = {"large_payload": "x" * (SNAPSHOT_METADATA_INLINE_LIMIT + 10_000)}
    store = _FakeStore(fail_overflow=True)

    with pytest.raises(RuntimeError, match="append failed"):
        hardened_append_snapshot_rows(
            store,
            run_id="COL-SNAPSHOT-FAIL",
            pair_list=[],
            state=_state(metadata),
        )

    assert "collector_discovery_snapshot" not in store.book.sheets


def test_main_write_failure_leaves_only_uncommitted_overflow_chunks() -> None:
    metadata = {"large_payload": "x" * (SNAPSHOT_METADATA_INLINE_LIMIT + 10_000)}
    store = _FakeStore(fail_main=True)

    with pytest.raises(RuntimeError, match="collector_discovery_snapshot"):
        hardened_append_snapshot_rows(
            store,
            run_id="COL-SNAPSHOT-MAIN-FAIL",
            pair_list=[],
            state=_state(metadata),
        )

    overflow = store.book.sheets[SNAPSHOT_OVERFLOW_SHEET]
    assert len(overflow.rows) > 1
    main = store.book.sheets["collector_discovery_snapshot"]
    assert main.rows == [SNAPSHOT_HEADERS]


def test_shadow_runtime_exposes_historical_and_current_snapshot_versions() -> None:
    from longread_collector import recall_instrumentation
    from longread_collector.v06.shadow.pipeline import (
        LEGACY_CONTROL_VERSION,
        PARALLEL_SHADOW_PIPELINE_VERSION,
    )

    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.9"
    assert LEGACY_CONTROL_VERSION == "collector-v0.5.6m"
    assert SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.5"
    assert CURRENT_SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.8"
    assert recall_instrumentation._append_snapshot_rows is current_hardened_append_snapshot_rows
