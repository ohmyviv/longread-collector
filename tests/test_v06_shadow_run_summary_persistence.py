from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.v06.shadow.run_summary_persistence import (
    SHADOW_RUN_SUMMARY_HEADERS,
    SHADOW_RUN_SUMMARY_SHEET,
    SHADOW_RUN_SUMMARY_VERSION,
    build_shadow_run_summary,
    persist_shadow_run_summary_from_payload_fail_open,
    upsert_shadow_run_summary,
)

TZ = ZoneInfo("Asia/Shanghai")
COMPLETED = datetime(2026, 8, 18, 18, 14, 12, tzinfo=TZ)


class WorksheetNotFound(Exception):
    pass


class FakeWorksheet:
    def __init__(self, values: list[list[object]] | None = None) -> None:
        self.values = [list(row) for row in (values or [])]
        self.updates: list[tuple[str, list[list[object]]]] = []

    def get_all_values(self):
        return [list(row) for row in self.values]

    def append_row(self, row, value_input_option=None):
        self.values.append(list(row))

    def update(self, *, range_name, values, value_input_option=None):
        self.updates.append((range_name, [list(row) for row in values]))
        row_no = int(range_name.split(":", 1)[0][1:])
        self.values[row_no - 1] = list(values[0])


class FakeBook:
    def __init__(self) -> None:
        self.sheets: dict[str, FakeWorksheet] = {}

    def worksheet(self, title: str):
        if title not in self.sheets:
            raise WorksheetNotFound(title)
        return self.sheets[title]

    def add_worksheet(self, *, title: str, rows: int, cols: int):
        ws = FakeWorksheet()
        self.sheets[title] = ws
        return ws


class FakeStore:
    def __init__(self) -> None:
        self.book = FakeBook()


class BrokenBook:
    def worksheet(self, title: str):
        raise RuntimeError("sheet backend unavailable")


class BrokenStore:
    def __init__(self) -> None:
        self.book = BrokenBook()


def _success_payload() -> dict[str, object]:
    return {
        "version": "full-parallel-shadow-v0.6-pr7",
        "pipeline_version": "collector-v0.6-pr7.3.9",
        "control_version": "collector-v0.5.6m",
        "source_selection_policy_version": "deadline-freshness-reserve-v0.6-phase0b.1",
        "snapshot_persistence_version": "snapshot-persistence-v0.6-pr7.3.5",
        "snapshot_capture_error": "",
        "status": "success",
        "run_id": "COL-20260818-181236-BJT-zh_evening",
        "group_id": "zh_evening",
        "discovery_snapshot_count": 144,
        "control_discovery_snapshot_count": 144,
        "persisted_discovery_snapshot_count": 144,
        "snapshot_readback_performed": True,
        "capture_gap_count": 0,
        "full_snapshot_invariant": True,
        "control_acquired_count": 32,
        "shared_body_count": 31,
        "body_fingerprint_mismatches": 0,
        "zero_duplicate_network_invariant": True,
        "shadow_request_count": 0,
        "shadow_firecrawl_request_count": 0,
        "shadow_incremental_cost": 0.0,
        "v06_selected_count": 3,
        "v06_source_chase_count": 2,
        "gate_action_counts": {"acquire": 20, "defer": 120, "hard_reject": 4},
        "v06_policy_action_counts": {
            "select_standard": 3,
            "source_chase": 2,
            "defer": 139,
        },
        "difference_tag_counts": {"policy_action_disagreement": 5},
        "event_count": 10,
        "event_digest_sha256": "a" * 64,
        "items": [
            {"v06_editorial_verdict": "recommend"},
            {"v06_editorial_verdict": "recommend"},
            {"v06_editorial_verdict": "consider"},
            {"v06_editorial_verdict": "low_value"},
            {"v06_editorial_verdict": "reject"},
            {"v06_editorial_verdict": "insufficient_evidence"},
            {"v06_editorial_verdict": ""},
        ],
        "events": [
            {"stage": "discovery", "technical_status": "success", "flow_status": "pass"},
            {"stage": "canonical", "technical_status": "success", "flow_status": "pass"},
            {"stage": "canonical", "technical_status": "success", "flow_status": "reject"},
            {"stage": "editorial", "technical_status": "success", "flow_status": "pass"},
            {"stage": "editorial", "technical_status": "success", "flow_status": "defer"},
            {"stage": "editorial", "technical_status": "success", "flow_status": "reject"},
            {"stage": "selection", "technical_status": "success", "flow_status": "pass"},
            {"stage": "selection", "technical_status": "success", "flow_status": "pass"},
            {"stage": "selection", "technical_status": "success", "flow_status": "defer"},
            {"stage": "selection", "technical_status": "success", "flow_status": "reject"},
        ],
    }


def test_success_summary_preserves_stage_counts_and_invariants_without_full_payload() -> None:
    row = build_shadow_run_summary(
        _success_payload(),
        collector_run_id="COL-20260818-181236-BJT-zh_evening",
        query_group="zh_evening",
        run_started_at_bj="2026-08-18 18:12:36",
        completed_at=COMPLETED,
    )

    assert row["status"] == "success"
    assert row["shadow_item_count"] == 7
    assert row["shadow_event_count"] == 10
    assert row["shadow_event_digest_sha256"] == "a" * 64
    assert row["l4_canonical_event_count"] == 2
    assert row["l4_technical_success_count"] == 2
    assert row["l4_flow_pass_count"] == 1
    assert row["l4_flow_reject_count"] == 1
    assert row["l4_flow_defer_count"] == 0
    assert row["l4_flow_action_required_count"] == 0
    assert row["l4_flow_error_count"] == 0
    assert row["l5_editorial_event_count"] == 3
    assert row["l5_recommend_count"] == 2
    assert row["l5_consider_count"] == 1
    assert row["l5_low_value_count"] == 1
    assert row["l5_reject_count"] == 1
    assert row["l5_insufficient_evidence_count"] == 1
    assert row["l6_selection_event_count"] == 4
    assert row["l6_selected_count"] == 3
    assert row["l6_source_chase_count"] == 2
    assert row["body_fingerprint_mismatches"] == 0
    assert row["full_snapshot_invariant"] == "TRUE"
    assert row["zero_duplicate_network_invariant"] == "TRUE"
    assert row["control_result_preserved"] == "TRUE"
    assert row["summary_version"] == SHADOW_RUN_SUMMARY_VERSION
    assert "items" not in row
    assert "events" not in row
    assert set(row) == set(SHADOW_RUN_SUMMARY_HEADERS)


def test_failed_open_summary_persists_error_boundary_without_inventing_stage_counts() -> None:
    payload = {
        "version": "full-parallel-shadow-v0.6-pr7",
        "pipeline_version": "collector-v0.6-pr7.3.9",
        "control_version": "collector-v0.5.6m",
        "status": "failed_open",
        "error": "ValueError: canonical evidence malformed",
        "shadow_request_count": 0,
        "shadow_firecrawl_request_count": 0,
        "shadow_incremental_cost": 0.0,
        "control_result_preserved": True,
        "full_snapshot_invariant": False,
    }

    row = build_shadow_run_summary(
        payload,
        collector_run_id="COL-FAILED",
        query_group="pre_report",
        run_started_at_bj="2026-08-18 06:30:00",
        completed_at=COMPLETED,
    )

    assert row["status"] == "failed_open"
    assert row["error_type"] == "ValueError"
    assert row["error_message"] == "canonical evidence malformed"
    assert row["shadow_item_count"] == 0
    assert row["shadow_event_count"] == 0
    assert row["l4_canonical_event_count"] == 0
    assert row["l4_technical_success_count"] == 0
    assert row["l4_flow_error_count"] == 0
    assert row["l5_editorial_event_count"] == 0
    assert row["l6_selection_event_count"] == 0
    assert row["full_snapshot_invariant"] == "FALSE"
    assert row["control_result_preserved"] == "TRUE"


def test_summary_sheet_is_lazy_created_and_upsert_is_idempotent() -> None:
    store = FakeStore()
    row = build_shadow_run_summary(
        _success_payload(),
        collector_run_id="COL-20260818-181236-BJT-zh_evening",
        query_group="zh_evening",
        run_started_at_bj="2026-08-18 18:12:36",
        completed_at=COMPLETED,
    )

    first = upsert_shadow_run_summary(store, row)
    assert first == {"inserted": 1, "updated": 0, "total": 1}
    ws = store.book.sheets[SHADOW_RUN_SUMMARY_SHEET]
    assert ws.values[0] == SHADOW_RUN_SUMMARY_HEADERS
    assert len(ws.values) == 2

    updated_row = dict(row)
    updated_row["l6_selected_count"] = 4
    second = upsert_shadow_run_summary(store, updated_row)
    assert second == {"inserted": 0, "updated": 1, "total": 1}
    assert len(ws.values) == 2
    selected_index = SHADOW_RUN_SUMMARY_HEADERS.index("l6_selected_count")
    assert ws.values[1][selected_index] == 4


def test_persistence_backend_failure_is_fail_open() -> None:
    result = persist_shadow_run_summary_from_payload_fail_open(
        BrokenStore(),
        _success_payload(),
        collector_run_id="COL-20260818-181236-BJT-zh_evening",
        query_group="zh_evening",
        run_started_at_bj="2026-08-18 18:12:36",
        completed_at=COMPLETED,
    )

    assert result["persisted"] is False
    assert result["inserted"] == 0
    assert result["updated"] == 0
    assert "RuntimeError: sheet backend unavailable" in result["error"]


def test_missing_run_id_is_a_measurement_failure_not_an_exception() -> None:
    result = persist_shadow_run_summary_from_payload_fail_open(
        FakeStore(),
        {"status": "success"},
        collector_run_id="",
        query_group="zh_evening",
        run_started_at_bj="",
        completed_at=COMPLETED,
    )

    assert result["persisted"] is False
    assert "collector_run_id is required" in result["error"]
