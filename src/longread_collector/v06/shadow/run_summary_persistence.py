"""Durable, lightweight run summaries for the v0.6 parallel Shadow.

The full Shadow payload remains an in-memory diagnostic return value.  This
module persists only one compact row per natural Collector run so later audits
can prove whether Shadow executed and how far it progressed without storing the
full per-item/event payload.

Persistence is deliberately fail-open: a Sheets/schema error is observability
failure, never a reason to change the authoritative legacy Control result or the
v0.6 Shadow judgment itself.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

SHADOW_RUN_SUMMARY_SHEET = "collector_v06_shadow_runs"
SHADOW_RUN_SUMMARY_VERSION = "v06-shadow-run-summary-v0.1"

SHADOW_RUN_SUMMARY_HEADERS = [
    "summary_id",
    "collector_run_id",
    "query_group",
    "run_started_at_bj",
    "shadow_completed_at_bj",
    "status",
    "parallel_shadow_version",
    "pipeline_version",
    "control_version",
    "source_selection_policy_version",
    "snapshot_persistence_version",
    "discovery_snapshot_count",
    "control_discovery_snapshot_count",
    "persisted_discovery_snapshot_count",
    "snapshot_readback_performed",
    "capture_gap_count",
    "full_snapshot_invariant",
    "control_acquired_count",
    "shared_body_count",
    "l4_canonical_event_count",
    "l5_editorial_event_count",
    "l5_recommend_count",
    "l5_consider_count",
    "l5_low_value_count",
    "l5_reject_count",
    "l5_insufficient_evidence_count",
    "l6_selection_event_count",
    "l6_selected_count",
    "l6_source_chase_count",
    "body_fingerprint_mismatches",
    "zero_duplicate_network_invariant",
    "shadow_request_count",
    "shadow_firecrawl_request_count",
    "shadow_incremental_cost",
    "gate_action_counts_json",
    "v06_policy_action_counts_json",
    "difference_tag_counts_json",
    "error_type",
    "error_message",
    "control_result_preserved",
    "persisted_at_bj",
    "summary_version",
]


def _column_name(column_number: int) -> str:
    if column_number < 1:
        raise ValueError("column_number must be positive")
    result = ""
    current = column_number
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _bool_cell(value: Any) -> str:
    return "TRUE" if bool(value) else "FALSE"


def _json_cell(value: Any) -> str:
    payload = value if isinstance(value, dict) else {}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _error_parts(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", ""
    if ": " in text:
        error_type, message = text.split(": ", 1)
        return error_type.strip(), message.strip()[:1800]
    return "", text[:1800]


def _event_stage_counts(events: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events if isinstance(events, (list, tuple)) else ():
        if not isinstance(event, dict):
            continue
        stage = str(event.get("stage", "") or "").strip()
        if stage:
            counts[stage] += 1
    return counts


def _editorial_verdict_counts(items: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items if isinstance(items, (list, tuple)) else ():
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("v06_editorial_verdict", "") or "").strip()
        if verdict:
            counts[verdict] += 1
    return counts


def _summary_id(run_id: str) -> str:
    if not run_id:
        raise ValueError("collector_run_id is required for Shadow summary persistence")
    return hashlib.sha256(
        f"{SHADOW_RUN_SUMMARY_VERSION}|{run_id}".encode("utf-8")
    ).hexdigest()[:24]


def build_shadow_run_summary(
    shadow_payload: dict[str, Any],
    *,
    collector_run_id: str,
    query_group: str,
    run_started_at_bj: str,
    completed_at: datetime,
) -> dict[str, Any]:
    """Project the full Shadow payload into one durable audit row."""

    run_id = str(collector_run_id or shadow_payload.get("run_id", "") or "").strip()
    summary_id = _summary_id(run_id)
    status = str(shadow_payload.get("status", "") or "unknown").strip()
    stages = _event_stage_counts(shadow_payload.get("events"))
    verdicts = _editorial_verdict_counts(shadow_payload.get("items"))
    error_type, error_message = _error_parts(shadow_payload.get("error"))
    control_preserved = bool(
        shadow_payload.get("control_result_preserved", status == "success")
    )

    return {
        "summary_id": summary_id,
        "collector_run_id": run_id,
        "query_group": str(query_group or shadow_payload.get("group_id", "") or ""),
        "run_started_at_bj": str(run_started_at_bj or ""),
        "shadow_completed_at_bj": completed_at.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "parallel_shadow_version": str(shadow_payload.get("version", "") or ""),
        "pipeline_version": str(shadow_payload.get("pipeline_version", "") or ""),
        "control_version": str(shadow_payload.get("control_version", "") or ""),
        "source_selection_policy_version": str(
            shadow_payload.get("source_selection_policy_version", "") or ""
        ),
        "snapshot_persistence_version": str(
            shadow_payload.get("snapshot_persistence_version", "") or ""
        ),
        "discovery_snapshot_count": int(
            shadow_payload.get("discovery_snapshot_count") or 0
        ),
        "control_discovery_snapshot_count": int(
            shadow_payload.get("control_discovery_snapshot_count") or 0
        ),
        "persisted_discovery_snapshot_count": int(
            shadow_payload.get("persisted_discovery_snapshot_count") or 0
        ),
        "snapshot_readback_performed": _bool_cell(
            shadow_payload.get("snapshot_readback_performed", False)
        ),
        "capture_gap_count": int(shadow_payload.get("capture_gap_count") or 0),
        "full_snapshot_invariant": _bool_cell(
            shadow_payload.get("full_snapshot_invariant", False)
        ),
        "control_acquired_count": int(shadow_payload.get("control_acquired_count") or 0),
        "shared_body_count": int(shadow_payload.get("shared_body_count") or 0),
        "l4_canonical_event_count": int(stages.get("canonical", 0)),
        "l5_editorial_event_count": int(stages.get("editorial", 0)),
        "l5_recommend_count": int(verdicts.get("recommend", 0)),
        "l5_consider_count": int(verdicts.get("consider", 0)),
        "l5_low_value_count": int(verdicts.get("low_value", 0)),
        "l5_reject_count": int(verdicts.get("reject", 0)),
        "l5_insufficient_evidence_count": int(
            verdicts.get("insufficient_evidence", 0)
        ),
        "l6_selection_event_count": int(stages.get("selection", 0)),
        "l6_selected_count": int(shadow_payload.get("v06_selected_count") or 0),
        "l6_source_chase_count": int(
            shadow_payload.get("v06_source_chase_count") or 0
        ),
        "body_fingerprint_mismatches": int(
            shadow_payload.get("body_fingerprint_mismatches") or 0
        ),
        "zero_duplicate_network_invariant": _bool_cell(
            shadow_payload.get("zero_duplicate_network_invariant", False)
        ),
        "shadow_request_count": int(shadow_payload.get("shadow_request_count") or 0),
        "shadow_firecrawl_request_count": int(
            shadow_payload.get("shadow_firecrawl_request_count") or 0
        ),
        "shadow_incremental_cost": float(
            shadow_payload.get("shadow_incremental_cost") or 0.0
        ),
        "gate_action_counts_json": _json_cell(shadow_payload.get("gate_action_counts")),
        "v06_policy_action_counts_json": _json_cell(
            shadow_payload.get("v06_policy_action_counts")
        ),
        "difference_tag_counts_json": _json_cell(
            shadow_payload.get("difference_tag_counts")
        ),
        "error_type": error_type,
        "error_message": error_message,
        "control_result_preserved": _bool_cell(control_preserved),
        "persisted_at_bj": completed_at.strftime("%Y-%m-%d %H:%M:%S"),
        "summary_version": SHADOW_RUN_SUMMARY_VERSION,
    }


def _ensure_summary_worksheet(store: Any) -> Any:
    try:
        ws = store.book.worksheet(SHADOW_RUN_SUMMARY_SHEET)
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        ws = store.book.add_worksheet(
            title=SHADOW_RUN_SUMMARY_SHEET,
            rows=5000,
            cols=len(SHADOW_RUN_SUMMARY_HEADERS),
        )
        ws.append_row(SHADOW_RUN_SUMMARY_HEADERS, value_input_option="USER_ENTERED")
        return ws

    values = ws.get_all_values()
    if not values:
        ws.append_row(SHADOW_RUN_SUMMARY_HEADERS, value_input_option="USER_ENTERED")
        return ws
    if list(values[0]) != SHADOW_RUN_SUMMARY_HEADERS:
        raise ValueError(
            f"{SHADOW_RUN_SUMMARY_SHEET} header mismatch; refusing schema mutation"
        )
    return ws


def upsert_shadow_run_summary(store: Any, row: dict[str, Any]) -> dict[str, int]:
    ws = _ensure_summary_worksheet(store)
    values = ws.get_all_values()
    existing = {
        str(existing_row[0]): index
        for index, existing_row in enumerate(values[1:], start=2)
        if existing_row and str(existing_row[0]).strip()
    }
    serialized = [row.get(header, "") for header in SHADOW_RUN_SUMMARY_HEADERS]
    summary_id = str(row.get("summary_id", "") or "").strip()
    if not summary_id:
        raise ValueError("summary_id is required")
    if summary_id in existing:
        row_no = existing[summary_id]
        end_column = _column_name(len(SHADOW_RUN_SUMMARY_HEADERS))
        ws.update(
            range_name=f"A{row_no}:{end_column}{row_no}",
            values=[serialized],
            value_input_option="USER_ENTERED",
        )
        return {"inserted": 0, "updated": 1, "total": 1}
    ws.append_row(serialized, value_input_option="USER_ENTERED")
    return {"inserted": 1, "updated": 0, "total": 1}


def persist_shadow_run_summary_from_payload_fail_open(
    store: Any,
    shadow_payload: dict[str, Any],
    *,
    collector_run_id: str,
    query_group: str,
    run_started_at_bj: str,
    completed_at: datetime,
) -> dict[str, Any]:
    """Build and persist one summary without ever failing the Collector run."""

    try:
        row = build_shadow_run_summary(
            shadow_payload,
            collector_run_id=collector_run_id,
            query_group=query_group,
            run_started_at_bj=run_started_at_bj,
            completed_at=completed_at,
        )
        result = upsert_shadow_run_summary(store, row)
        return {"persisted": True, "error": "", **result}
    except Exception as exc:
        return {
            "persisted": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "inserted": 0,
            "updated": 0,
            "total": 0,
        }


__all__ = [
    "SHADOW_RUN_SUMMARY_HEADERS",
    "SHADOW_RUN_SUMMARY_SHEET",
    "SHADOW_RUN_SUMMARY_VERSION",
    "build_shadow_run_summary",
    "persist_shadow_run_summary_from_payload_fail_open",
    "upsert_shadow_run_summary",
]
