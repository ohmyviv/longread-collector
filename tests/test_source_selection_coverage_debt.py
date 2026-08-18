from __future__ import annotations

from datetime import datetime

from longread_collector.runtime_config import load_collector_runtime_config
from longread_collector.source_selection_phase0b import (
    SourceFreshnessPolicy,
    begin_source_selection,
    end_source_selection,
    select_sources_for_run,
    selection_audit_payload,
)


def src(source_id, tier="rotate", scanned="2026-08-16 00:00:00"):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "priority_tier": tier,
        "last_scanned_at_bj": scanned,
        "enabled": True,
        "parser_config_json": "{}",
    }


def test_debt_preempts_at_most_one_slot_and_preserves_one_rotation_slot() -> None:
    started = datetime(2026, 8, 18, 4, 0)
    fresh_ids = tuple(f"fresh{i}" for i in range(1, 7))
    sources = [src(source_id) for source_id in fresh_ids] + [
        src("ft", scanned="2026-08-16 22:50:00"),
        src("ordinary", tier="explore", scanned="2026-08-14 00:00:00"),
        src("other", scanned="2026-08-13 00:00:00"),
    ]
    policy = SourceFreshnessPolicy(
        enabled=True,
        group_id="pre_report",
        freshness_source_ids=fresh_ids,
        freshness_max_sources=6,
        coverage_debt_enabled=True,
        coverage_debt_source_ids=("ft", "other"),
        coverage_debt_max_sources=1,
        coverage_debt_min_rotation_slots=1,
    )
    token = begin_source_selection(policy)
    try:
        selected = select_sources_for_run(sources, started=started, max_sources=8)
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)

    assert len(selected) == 8
    assert sum(
        row["selection_reason"] == "freshness_reserve" for row in audit["selected"]
    ) == 6
    debt = [
        row for row in audit["selected"] if row["selection_reason"] == "coverage_debt"
    ]
    ordinary = [
        row
        for row in audit["selected"]
        if row["selection_reason"] == "coverage_rotation"
    ]
    assert [row["source_id"] for row in debt] == ["ft"]
    assert len(ordinary) == 1


def test_debt_source_already_in_freshness_reserve_is_not_duplicated() -> None:
    started = datetime(2026, 8, 18, 4, 0)
    sources = [
        src("ft"),
        src("fresh2"),
        src("r1"),
        src("r2"),
        src("e1", tier="explore"),
    ]
    policy = SourceFreshnessPolicy(
        enabled=True,
        group_id="pre_report",
        freshness_source_ids=("ft", "fresh2"),
        freshness_max_sources=2,
        coverage_debt_enabled=True,
        coverage_debt_source_ids=("ft",),
        coverage_debt_max_sources=1,
    )
    token = begin_source_selection(policy)
    try:
        selected = select_sources_for_run(sources, started=started, max_sources=4)
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)

    ids = [row["source_id"] for row in audit["selected"]]
    assert len(selected) == 4
    assert ids.count("ft") == 1
    ft_row = next(row for row in audit["selected"] if row["source_id"] == "ft")
    assert ft_row["selection_reason"] == "freshness_reserve"
    assert not any(
        row["selection_reason"] == "coverage_debt" for row in audit["selected"]
    )


def test_debt_disabled_does_not_change_existing_freshness_selection() -> None:
    started = datetime(2026, 8, 18, 4, 0)
    sources = [
        src("fresh"),
        src("r1", scanned="2026-08-12 00:00:00"),
        src("r2", scanned="2026-08-13 00:00:00"),
        src("e1", tier="explore", scanned="2026-08-11 00:00:00"),
    ]
    without_debt = SourceFreshnessPolicy(
        enabled=True,
        freshness_source_ids=("fresh",),
        freshness_max_sources=1,
    )
    disabled_debt = SourceFreshnessPolicy(
        enabled=True,
        freshness_source_ids=("fresh",),
        freshness_max_sources=1,
        coverage_debt_enabled=False,
        coverage_debt_source_ids=("r2",),
        coverage_debt_max_sources=1,
    )

    token = begin_source_selection(without_debt)
    try:
        first = select_sources_for_run(sources, started=started, max_sources=3)
    finally:
        end_source_selection(token)
    token = begin_source_selection(disabled_debt)
    try:
        second = select_sources_for_run(sources, started=started, max_sources=3)
    finally:
        end_source_selection(token)

    assert [row["source_id"] for row in first] == [row["source_id"] for row in second]


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return list(self.rows)


class FakeBook:
    def __init__(self, rows):
        self.rows = rows

    def worksheet(self, name):
        assert name == "collector_config"
        return FakeWorksheet(self.rows)


class FakeStore:
    def __init__(self, rows):
        self.book = FakeBook(rows)


def cfg(key, value):
    return {"config_key": key, "value": value, "status": "active"}


def test_coverage_debt_runtime_defaults_are_inert() -> None:
    runtime = load_collector_runtime_config(FakeStore([]))

    assert runtime.native_coverage_debt_policy_enabled is False
    assert runtime.native_coverage_debt_max_per_run == 1
    assert runtime.native_coverage_debt_safety_margin_hours == 2.0
    assert runtime.native_coverage_debt_min_samples == 2
    assert runtime.native_coverage_debt_recent_samples == 5
    assert runtime.native_coverage_debt_projection_hours_by_group == {}


def test_coverage_debt_runtime_parses_projection_mapping() -> None:
    runtime = load_collector_runtime_config(
        FakeStore(
            [
                cfg("native_coverage_debt_policy_enabled", "TRUE"),
                cfg("native_coverage_debt_max_per_run", 1),
                cfg("native_coverage_debt_safety_margin_hours", 1.5),
                cfg("native_coverage_debt_min_samples", 3),
                cfg("native_coverage_debt_recent_samples", 6),
                cfg(
                    "native_coverage_debt_projection_hours_by_group",
                    '{"intl_early":5.5,"pre_report":18,"bad":"x"}',
                ),
            ]
        )
    )

    assert runtime.native_coverage_debt_policy_enabled is True
    assert runtime.native_coverage_debt_max_per_run == 1
    assert runtime.native_coverage_debt_safety_margin_hours == 1.5
    assert runtime.native_coverage_debt_min_samples == 3
    assert runtime.native_coverage_debt_recent_samples == 6
    assert runtime.native_coverage_debt_projection_hours_by_group == {
        "intl_early": 5.5,
        "pre_report": 18.0,
    }
