from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from longread_collector.source_run_coverage import (
    SOURCE_RUN_COVERAGE_HEADERS,
    SOURCE_RUN_COVERAGE_SHEET,
    build_source_run_coverage_rows,
    persist_source_run_coverage_fail_open,
    upsert_source_run_coverage,
)

TZ = ZoneInfo("Asia/Shanghai")
STARTED = datetime(2026, 8, 18, 4, 11, 49, tzinfo=TZ)


def _source(source_id: str = "ft") -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_name": "Financial Times" if source_id == "ft" else source_id,
        "language": "en",
        "_selection_reason": "coverage_rotation",
        "_selection_scan_age_hours": 29.5,
    }


def _item(
    source_id: str,
    published_at: str,
    *,
    purpose: str = "native_source_scan",
):
    return SimpleNamespace(
        published_at=published_at,
        query_or_source=f"source:{source_id}",
        metadata={"source_id": source_id, "purpose": purpose},
    )


def _native_log(
    source_id: str = "ft",
    *,
    success: bool = True,
    results_count: int = 2,
    attempts=None,
):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "success": success,
        "selected_method": "rss" if success else "",
        "selected_endpoint": "https://example.com/feed" if success else "",
        "results_count": results_count,
        "fallback_needed": not success,
        "attempts": attempts or [],
    }


def _fallback_log(source_id: str, *, success: bool, results_count: int):
    return {
        "query_id": f"source:{source_id}",
        "purpose": "directed_source_scan",
        "success": success,
        "results_count": results_count,
    }


def test_native_dated_observations_establish_lower_bound_coverage() -> None:
    rows = build_source_run_coverage_rows(
        run_id="COL-TEST",
        query_group="pre_report",
        started=STARTED,
        selected_sources=[_source()],
        native_logs=[_native_log()],
        native_items=[
            _item("ft", "2026-08-17 08:00:00+08:00"),
            _item("ft", "2026-08-18 01:00:00+08:00"),
        ],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=STARTED,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["route_status"] == "native_covered"
    assert row["coverage_confidence"] == "lower_bound"
    assert row["native_results_count"] == 2
    assert row["dated_observation_count"] == 2
    assert row["oldest_observed_published_at"] == "2026-08-17 08:00:00"
    assert row["newest_observed_published_at"] == "2026-08-18 01:00:00"
    assert row["observed_horizon_hours"] == 20.197
    assert row["selection_reason"] == "coverage_rotation"
    assert row["scan_age_hours"] == 29.5


def test_native_success_without_dates_does_not_create_coverage_horizon() -> None:
    rows = build_source_run_coverage_rows(
        run_id="COL-TEST",
        query_group="pre_report",
        started=STARTED,
        selected_sources=[_source()],
        native_logs=[_native_log(results_count=1)],
        native_items=[_item("ft", "")],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=STARTED,
    )

    row = rows[0]
    assert row["route_status"] == "native_success_date_unknown"
    assert row["observed_horizon_hours"] == ""
    assert row["coverage_confidence"] == "unknown"


def test_native_zero_results_is_distinct_from_native_failure() -> None:
    rows = build_source_run_coverage_rows(
        run_id="COL-ZERO",
        query_group="pre_report",
        started=STARTED,
        selected_sources=[_source()],
        native_logs=[
            _native_log(
                success=False,
                results_count=0,
                attempts=[{"method": "rss", "http_status": 200, "results_count": 0}],
            )
        ],
        native_items=[],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=STARTED,
    )

    row = rows[0]
    assert row["native_status"] == "zero_results"
    assert row["route_status"] == "native_zero_results"


def test_fallback_capture_never_manufactures_native_coverage() -> None:
    source_id = "reuters-special"
    rows = build_source_run_coverage_rows(
        run_id="COL-FALLBACK",
        query_group="intl_early",
        started=STARTED,
        selected_sources=[_source(source_id)],
        native_logs=[
            _native_log(
                source_id,
                success=False,
                results_count=0,
                attempts=[
                    {
                        "method": "sitemap",
                        "endpoint": "https://example.com/sitemap.xml",
                        "error_type": "HTTPStatusError",
                    }
                ],
            )
        ],
        native_items=[],
        firecrawl_logs=[_fallback_log(source_id, success=True, results_count=4)],
        firecrawl_items=[
            _item(
                source_id,
                "2026-08-17 12:00:00+08:00",
                purpose="directed_source_scan",
            )
        ],
        persisted_at=STARTED,
    )

    row = rows[0]
    assert row["native_status"] == "failed"
    assert row["fallback_status"] == "success"
    assert row["route_status"] == "fallback_only"
    assert row["raw_observation_count"] == 1
    assert row["dated_observation_count"] == 0
    assert row["observed_horizon_hours"] == ""
    assert row["coverage_confidence"] == "unknown"


class WorksheetNotFound(Exception):
    pass


class FakeWorksheet:
    def __init__(self) -> None:
        self.values: list[list[object]] = []

    def get_all_values(self):
        return [list(row) for row in self.values]

    def append_row(self, row, value_input_option=None):
        self.values.append(list(row))

    def append_rows(self, rows, value_input_option=None):
        self.values.extend([list(row) for row in rows])

    def update(self, range_name, values, value_input_option=None):
        start = range_name.split(":", 1)[0]
        row_no = int("".join(char for char in start if char.isdigit()))
        while len(self.values) < row_no:
            self.values.append([])
        self.values[row_no - 1] = list(values[0])


class FakeBook:
    def __init__(self) -> None:
        self.sheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, name):
        if name not in self.sheets:
            raise WorksheetNotFound(name)
        return self.sheets[name]

    def add_worksheet(self, title, rows, cols):
        ws = FakeWorksheet()
        self.sheets[title] = ws
        return ws


class FakeStore:
    def __init__(self) -> None:
        self.book = FakeBook()


def test_upsert_is_idempotent_per_run_source() -> None:
    store = FakeStore()
    row = build_source_run_coverage_rows(
        run_id="COL-IDEMPOTENT",
        query_group="pre_report",
        started=STARTED,
        selected_sources=[_source()],
        native_logs=[_native_log()],
        native_items=[_item("ft", "2026-08-17 08:00:00+08:00")],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=STARTED,
    )[0]

    first = upsert_source_run_coverage(store, [row])
    changed = dict(row)
    changed["raw_observation_count"] = 9
    second = upsert_source_run_coverage(store, [changed])

    ws = store.book.worksheet(SOURCE_RUN_COVERAGE_SHEET)
    assert first == {"inserted": 1, "updated": 0, "total": 1}
    assert second == {"inserted": 0, "updated": 1, "total": 1}
    assert ws.values[0] == SOURCE_RUN_COVERAGE_HEADERS
    assert len(ws.values) == 2
    raw_index = SOURCE_RUN_COVERAGE_HEADERS.index("raw_observation_count")
    assert ws.values[1][raw_index] == 9


def test_persistence_is_fail_open() -> None:
    broken_store = SimpleNamespace(book=SimpleNamespace())
    result = persist_source_run_coverage_fail_open(broken_store, [{"coverage_id": "x"}])

    assert result["persisted"] is False
    assert result["error"]
