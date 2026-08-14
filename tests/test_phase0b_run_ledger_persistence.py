from __future__ import annotations

import asyncio
from datetime import datetime
import multiprocessing
from types import SimpleNamespace
from zoneinfo import ZoneInfo


class RunWorksheet:
    def __init__(self) -> None:
        self.rows: list[list[object]] = []

    def append_row(self, row, value_input_option=None) -> None:
        self.rows.append(list(row))


class Book:
    def __init__(self) -> None:
        self.run_sheet = RunWorksheet()

    def worksheet(self, name: str):
        assert name == "collector_runs"
        return self.run_sheet


class Store:
    def __init__(self) -> None:
        self.book = Book()

    def load_queries(self, group_id=None):
        return []

    def load_source_registry(self, language=None):
        return []

    def count_firecrawl_scrapes_today(self, query_group=None):
        return 0

    def append_collector_run(self, values) -> None:
        # This is deliberately not the final sink in the real v0.5.6b path.
        # The regression test proves that the direct GoogleSheetStore sink is
        # still decorated by Phase 0B when v0.5.6b bypasses outer wrappers.
        raise AssertionError("unexpected instance-level final sink")


def _runtime():
    return SimpleNamespace(
        native_freshness_policy_enabled=True,
        native_freshness_max_per_run=6,
        native_source_scans_per_run=8,
        native_freshness_sources_by_group={
            "pre_report": (
                "wired",
                "newyorker",
                "restofworld",
                "quanta",
                "atlantic",
                "propublica",
            )
        },
    )


def _allocation():
    return SimpleNamespace(
        daily_limit=3,
        total_used=0,
        remaining=3,
        group_cap=1,
        group_used=0,
    )


def _schedule(started, queries, group_id):
    return {
        "scheduled_at_bj": "2026-08-14 03:57:00",
        "start_delay_seconds": 0,
    }


def _sources():
    return [
        {"source_id": "restofworld", "source_name": "Rest of World", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-12 04:37:00", "parser_config_json": "{}"},
        {"source_id": "quanta", "source_name": "Quanta", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-12 04:37:00", "parser_config_json": "{}"},
        {"source_id": "propublica", "source_name": "ProPublica", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-12 04:37:00", "parser_config_json": "{}"},
        {"source_id": "wired", "source_name": "WIRED", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-13 00:43:00", "parser_config_json": "{}"},
        {"source_id": "newyorker", "source_name": "The New Yorker", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-13 05:48:00", "parser_config_json": "{}"},
        {"source_id": "atlantic", "source_name": "The Atlantic", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-14 00:36:00", "parser_config_json": "{}"},
        {"source_id": "war-on-the-rocks", "source_name": "War on the Rocks", "priority_tier": "explore", "enabled": True, "last_scanned_at_bj": "2026-08-12 04:37:00", "parser_config_json": "{}"},
        {"source_id": "aeon", "source_name": "Aeon", "priority_tier": "explore", "enabled": True, "last_scanned_at_bj": "2026-08-13 00:43:00", "parser_config_json": "{}"},
    ]


def _exercise_scheduled_v06_path() -> None:
    # Import release modules only inside a spawned child process. Several legacy
    # modules intentionally install process-global compatibility hooks at import
    # time; isolating this integration regression prevents test-order pollution.
    from longread_collector import (
        pipeline_phase0b,
        pipeline_v05,
        pipeline_v051,
        pipeline_v055,
        pipeline_v056e,
    )
    from longread_collector.sheets import RUN_HEADERS
    from longread_collector.v06.shadow.pipeline import ParallelShadowCollectorPipeline

    runtime = _runtime()
    allocation = _allocation()

    pipeline_phase0b.load_collector_runtime_config = lambda store: runtime
    pipeline_v051.load_collector_runtime_config = lambda store: runtime
    pipeline_v055.load_collector_runtime_config = lambda store: runtime
    pipeline_v056e.load_collector_runtime_config = lambda store: runtime
    pipeline_v051.allocate_fallback_budget = lambda store, cfg, group: allocation
    pipeline_v055.allocate_fallback_budget = lambda store, cfg, group: allocation
    pipeline_v056e.allocate_fallback_budget = lambda store, cfg, group: allocation
    pipeline_v051.scheduled_run_metrics = _schedule
    pipeline_v056e.scheduled_run_metrics = _schedule

    async def fake_base_collect(self, group_id=None, query_file=None):
        selected = pipeline_v05.select_sources_for_run(
            _sources(),
            started=datetime(2026, 8, 14, 4, 26, 12),
            max_sources=8,
        )
        values = {
            "collector_run_id": "COL-TEST-PHASE0B-PERSISTENCE",
            "started_at_bj": "2026-08-14 04:26:12",
            "completed_at_bj": "2026-08-14 04:27:00",
            "mode": "shadow",
            "query_group": "pre_report",
            "sources_scanned": len(selected),
            "final_status": "success",
            "notes": "base",
        }
        self.store.append_collector_run(values)
        return dict(values)

    pipeline_v05.NativeCollectorPipeline.collect = fake_base_collect

    pipeline = ParallelShadowCollectorPipeline.__new__(ParallelShadowCollectorPipeline)
    pipeline.store = Store()
    pipeline.settings = SimpleNamespace(max_urls_per_run=32, firecrawl_fallback_daily_limit=3)
    pipeline.tz = ZoneInfo("Asia/Shanghai")
    pipeline._v06_acquired_pairs = []
    pipeline._v06_runner = SimpleNamespace(
        run=lambda *args, **kwargs: SimpleNamespace(
            as_dict=lambda: {"discovery_snapshot_count": 0, "items": []}
        )
    )
    pipeline._historical_dedupe_count = 0
    pipeline._historical_dedupe = SimpleNamespace(
        reset=lambda: None,
        load_count=0,
        load_error="",
    )

    original_direct_sink = pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN
    original_selector = pipeline_v05.select_sources_for_run

    result = asyncio.run(pipeline.collect(group_id="pre_report"))

    assert pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN is original_direct_sink
    assert pipeline_v05.select_sources_for_run is original_selector
    assert len(pipeline.store.book.run_sheet.rows) == 1

    persisted = dict(zip(RUN_HEADERS, pipeline.store.book.run_sheet.rows[0]))
    notes = str(persisted["notes"])
    assert notes.count("source_selection_policy_version=") == 1
    assert "source_selection_policy_version=deadline-freshness-reserve-v0.6-phase0b.1" in notes
    assert "source_selection_policy_enabled=TRUE" in notes
    assert "source_selection_group=pre_report" in notes
    assert "source_selection_freshness=restofworld|quanta|propublica|wired|newyorker|atlantic" in notes
    assert "restofworld:freshness_reserve:" in notes
    assert "atlantic:freshness_reserve:" in notes
    assert "war-on-the-rocks:coverage_rotation:" in notes
    assert "aeon:coverage_rotation:" in notes

    audit = result["source_selection_audit"]
    assert result["source_selection_policy_enabled"] is True
    assert result["freshness_sources_selected"] == 6
    assert len(audit["selected"]) == 8
    assert sum(item["selection_reason"] == "freshness_reserve" for item in audit["selected"]) == 6
    assert sum(item["selection_reason"] == "coverage_rotation" for item in audit["selected"]) == 2
    assert all(item["scan_age_hours"] is not None for item in audit["selected"])


def test_scheduled_v06_path_persists_phase0b_marker_through_v056b_direct_sink() -> None:
    process = multiprocessing.get_context("spawn").Process(
        target=_exercise_scheduled_v06_path
    )
    process.start()
    process.join(timeout=30)
    if process.is_alive():
        process.terminate()
        process.join()
        raise AssertionError("isolated Phase 0B integration regression timed out")
    assert process.exitcode == 0
