from datetime import datetime

from longread_collector import pipeline_v05
from longread_collector.pipeline_phase0b import Phase0BSourceSelectionHook
from longread_collector.source_selection_phase0b import select_sources_for_run


class Worksheet:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return list(self.rows)


class Book:
    def __init__(self, rows):
        self.rows = rows

    def worksheet(self, name):
        assert name == "collector_config"
        return Worksheet(self.rows)


class Store:
    def __init__(self, rows):
        self.book = Book(rows)
        self.appended = []

    def append_collector_run(self, values):
        self.appended.append(dict(values))


class Pipeline:
    def __init__(self, rows):
        self.store = Store(rows)


def cfg(key, value):
    return {"config_key": key, "value": value, "status": "active"}


def test_enabled_hook_restores_process_and_store_state():
    pipeline = Pipeline([
        cfg("native_source_scans_per_run", 8),
        cfg("native_freshness_policy_enabled", "TRUE"),
        cfg("native_freshness_max_per_run", 1),
        cfg("native_freshness_sources_by_group", '{"pre_report":["fresh"]}'),
    ])
    old_selector = pipeline_v05.select_sources_for_run
    old_append = pipeline.store.append_collector_run
    hook = Phase0BSourceSelectionHook(pipeline, "pre_report")

    with hook:
        assert pipeline_v05.select_sources_for_run is select_sources_for_run
        selected = pipeline_v05.select_sources_for_run(
            [
                {"source_id": "fresh", "source_name": "Fresh", "priority_tier": "rotate", "enabled": True, "last_scanned_at_bj": "2026-08-13 01:00:00", "parser_config_json": "{}"},
                {"source_id": "other", "source_name": "Other", "priority_tier": "explore", "enabled": True, "last_scanned_at_bj": "2026-08-10 01:00:00", "parser_config_json": "{}"},
            ],
            started=datetime(2026, 8, 13, 4, 28),
            max_sources=2,
        )
        assert selected[0]["source_id"] == "fresh"
        pipeline.store.append_collector_run({"notes": "base"})

    assert pipeline_v05.select_sources_for_run is old_selector
    assert pipeline.store.append_collector_run == old_append
    assert hook.audit["enabled"] is True
    assert hook.audit["selected"][0]["selection_reason"] == "freshness_reserve"
    assert "source_selection_policy_version=" in pipeline.store.appended[0]["notes"]


def test_disabled_hook_has_no_selector_or_append_side_effect():
    pipeline = Pipeline([])
    old_selector = pipeline_v05.select_sources_for_run
    old_append = pipeline.store.append_collector_run
    hook = Phase0BSourceSelectionHook(pipeline, "pre_report")

    with hook:
        assert pipeline_v05.select_sources_for_run is old_selector
        assert pipeline.store.append_collector_run == old_append

    assert hook.audit["enabled"] is False
