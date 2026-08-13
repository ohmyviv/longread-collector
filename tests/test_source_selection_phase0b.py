from datetime import datetime

from longread_collector.known_source_fixes import select_sources_for_run as legacy_selector
from longread_collector.source_selection_phase0b import (
    SourceFreshnessPolicy,
    begin_source_selection,
    end_source_selection,
    select_sources_for_run,
    selection_audit_payload,
)


def src(source_id, tier="rotate", scanned="", enabled=True):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "priority_tier": tier,
        "last_scanned_at_bj": scanned,
        "enabled": enabled,
        "parser_config_json": "{}",
    }


def ids(rows):
    return [str(row.get("source_id", "")) for row in rows]


def test_disabled_policy_matches_legacy_selection():
    started = datetime(2026, 8, 13, 18, 45)
    sources = [
        src("r1", scanned="2026-08-10 10:00:00"),
        src("r2", scanned="2026-08-11 10:00:00"),
        src("r3", scanned="2026-08-12 10:00:00"),
        src("r4", scanned="2026-08-13 09:00:00"),
        src("e1", tier="explore", scanned="2026-08-09 10:00:00"),
        src("e2", tier="explore", scanned="2026-08-12 09:00:00"),
    ]
    expected = legacy_selector(sources, started=started, max_sources=4)
    token = begin_source_selection(SourceFreshnessPolicy(enabled=False))
    try:
        actual = select_sources_for_run(sources, started=started, max_sources=4)
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)
    assert ids(actual) == ids(expected)
    assert audit["enabled"] is False
    assert all(x["selection_reason"] == "coverage_rotation" for x in audit["selected"])


def test_freshness_source_bypasses_same_day_avoidance_only_for_itself():
    started = datetime(2026, 8, 13, 18, 45)
    sources = [
        src("fresh", scanned="2026-08-13 13:20:00"),
        src("ordinary_same_day", scanned="2026-08-13 11:00:00"),
        src("r1", scanned="2026-08-10 10:00:00"),
        src("r2", scanned="2026-08-11 10:00:00"),
        src("r3", scanned="2026-08-12 10:00:00"),
        src("e1", tier="explore", scanned="2026-08-10 09:00:00"),
        src("e2", tier="explore", scanned="2026-08-11 09:00:00"),
    ]
    token = begin_source_selection(SourceFreshnessPolicy(
        enabled=True, group_id="zh_evening", freshness_source_ids=("fresh",), freshness_max_sources=1
    ))
    try:
        selected = select_sources_for_run(sources, started=started, max_sources=4)
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)
    assert "fresh" in ids(selected)
    assert "ordinary_same_day" not in ids(selected)
    row = next(x for x in audit["selected"] if x["source_id"] == "fresh")
    assert row["selection_reason"] == "freshness_reserve"
    assert row["scan_age_hours"] == 5.417


def test_freshness_sources_consume_existing_tier_quota():
    started = datetime(2026, 8, 13, 4, 28)
    sources = [
        src("fresh1", scanned="2026-08-12 04:37:00"),
        src("fresh2", scanned="2026-08-12 04:38:00"),
        src("r3", scanned="2026-08-09 00:00:00"),
        src("r4", scanned="2026-08-10 00:00:00"),
        src("e1", tier="explore", scanned="2026-08-08 00:00:00"),
        src("e2", tier="explore", scanned="2026-08-09 00:00:00"),
    ]
    token = begin_source_selection(SourceFreshnessPolicy(
        enabled=True, group_id="pre_report", freshness_source_ids=("fresh1", "fresh2"), freshness_max_sources=2
    ))
    try:
        selected = select_sources_for_run(sources, started=started, max_sources=4)
    finally:
        end_source_selection(token)
    assert len(selected) == 4
    assert {"fresh1", "fresh2"}.issubset(set(ids(selected)))
    assert sum(x["priority_tier"] == "rotate" for x in selected) == 3
    assert sum(x["priority_tier"] == "explore" for x in selected) == 1


def test_cap_and_missing_configured_sources_are_explicit():
    started = datetime(2026, 8, 13, 4, 28)
    sources = [src("r1"), src("r2"), src("r3"), src("e1", tier="explore"), src("disabled", enabled=False), src("monitor", tier="monitor")]
    token = begin_source_selection(SourceFreshnessPolicy(
        enabled=True,
        group_id="pre_report",
        freshness_source_ids=("r1", "r2", "disabled", "monitor", "missing"),
        freshness_max_sources=5,
    ))
    try:
        selected = select_sources_for_run(sources, started=started, max_sources=3)
        audit = selection_audit_payload()
    finally:
        end_source_selection(token)
    assert len(selected) == 3
    assert "disabled" not in ids(selected) and "monitor" not in ids(selected)
    assert audit["missing_freshness_source_ids"] == ["disabled", "monitor", "missing"]


def test_context_resets():
    token = begin_source_selection(SourceFreshnessPolicy(enabled=True, freshness_source_ids=("x",), freshness_max_sources=1))
    end_source_selection(token)
    assert selection_audit_payload()["enabled"] is False
