"""Durable sidecar telemetry for Chinese paired route Shadow S1.

The two sheets are independent of ``collector_source_run_coverage`` and the
immutable Control Discovery snapshot.  They never feed candidate selection.
Rows are append-only by stable observation IDs; duplicates from a repeated
persistence call are skipped rather than rewritten.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from .sheets import _retry_sheet_call
from .zh_route_shadow_discovery_v1 import ZhRouteShadowReport

ROUTE_OBSERVATION_SHEET = "collector_route_shadow_observations"
ROUTE_ITEM_SHEET = "collector_route_shadow_items"
ROUTE_SHADOW_TELEMETRY_VERSION = "zh-route-shadow-telemetry-v1"

ROUTE_OBSERVATION_HEADERS = [
    "route_shadow_observation_id",
    "collector_run_id",
    "query_group",
    "control_run_started_at_bj",
    "treatment_observed_at_bj",
    "source_id",
    "surface_id",
    "surface_role",
    "publication_surface_id",
    "route_variant",
    "route_contract_version",
    "route_discovery_version",
    "body_mode",
    "endpoint",
    "transport",
    "request_success",
    "http_status",
    "parse_success",
    "surface_status",
    "raw_item_count",
    "unique_item_count",
    "recent_item_count",
    "dated_item_count",
    "exact_timestamp_count",
    "oldest_published_at",
    "newest_published_at",
    "control_overlap_count",
    "treatment_unique_count",
    "noise_item_count",
    "noise_reason_counts_json",
    "request_latency_ms",
    "error_type",
    "error_message",
    "persisted_at_bj",
    "telemetry_version",
]

ROUTE_ITEM_HEADERS = [
    "route_shadow_item_id",
    "collector_run_id",
    "query_group",
    "control_run_started_at_bj",
    "treatment_observed_at_bj",
    "source_id",
    "surface_id",
    "surface_role",
    "publication_surface_id",
    "endpoint",
    "transport",
    "url",
    "url_canonical",
    "title",
    "published_at",
    "publication_time_source",
    "publication_time_confidence",
    "surface_rank",
    "within_freshness",
    "control_overlap",
    "noise_reason",
    "route_contract_version",
    "route_discovery_version",
    "body_mode",
    "persisted_at_bj",
    "telemetry_version",
]


def _stable_id(*parts: object) -> str:
    value = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _ensure_sheet(store: Any, title: str, headers: list[str], *, rows: int) -> Any:
    try:
        if hasattr(store, "_worksheet"):
            ws = store._worksheet(title)
        else:
            ws = store.book.worksheet(title)
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        # Do not retry creation blindly: an ambiguous create response could
        # otherwise produce duplicate sidecar tabs.
        ws = store.book.add_worksheet(title=title, rows=rows, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
        return ws

    values = _retry_sheet_call(ws.get_all_values)
    if not values:
        ws.append_row(headers, value_input_option="USER_ENTERED")
        return ws
    if list(values[0]) != headers:
        raise ValueError(f"{title} header mismatch; refusing schema mutation")
    return ws


def _append_new_rows(ws: Any, headers: list[str], rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"inserted": 0, "skipped_existing": 0}
    values = _retry_sheet_call(ws.get_all_values)
    existing = {
        str(row[0]).strip()
        for row in values[1:]
        if row and str(row[0]).strip()
    }
    serialized: list[list[Any]] = []
    skipped = 0
    for row in rows:
        row_id = str(row.get(headers[0], "") or "").strip()
        if not row_id or row_id in existing:
            skipped += 1
            continue
        existing.add(row_id)
        serialized.append([row.get(header, "") for header in headers])
    if serialized:
        # Append is deliberately not retried: an ambiguous response can mean the
        # server already committed the rows. Stable IDs make a later explicit
        # replay safe without risking immediate duplicate evidence.
        ws.append_rows(serialized, value_input_option="USER_ENTERED")
    return {"inserted": len(serialized), "skipped_existing": skipped}


def _route_rows(
    report: ZhRouteShadowReport,
    *,
    collector_run_id: str,
    persisted_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for observation in report.observations:
        rows.append(
            {
                "route_shadow_observation_id": _stable_id(
                    collector_run_id,
                    observation.source_id,
                    observation.surface_id,
                    "treatment",
                ),
                "collector_run_id": collector_run_id,
                "query_group": report.group_id,
                "control_run_started_at_bj": report.started_at_bj,
                "treatment_observed_at_bj": observation.observed_at_bj,
                "source_id": observation.source_id,
                "surface_id": observation.surface_id,
                "surface_role": observation.surface_role,
                "publication_surface_id": observation.publication_surface_id,
                "route_variant": "treatment",
                "route_contract_version": report.contract_version,
                "route_discovery_version": report.version,
                "body_mode": report.body_mode,
                "endpoint": observation.endpoint,
                "transport": observation.transport,
                "request_success": "TRUE" if observation.request_success else "FALSE",
                "http_status": observation.http_status,
                "parse_success": "TRUE" if observation.parse_success else "FALSE",
                "surface_status": observation.surface_status,
                "raw_item_count": observation.raw_item_count,
                "unique_item_count": observation.unique_item_count,
                "recent_item_count": observation.recent_item_count,
                "dated_item_count": observation.dated_item_count,
                "exact_timestamp_count": observation.exact_timestamp_count,
                "oldest_published_at": observation.oldest_published_at,
                "newest_published_at": observation.newest_published_at,
                "control_overlap_count": observation.control_overlap_count,
                "treatment_unique_count": observation.treatment_unique_count,
                "noise_item_count": observation.noise_item_count,
                "noise_reason_counts_json": json.dumps(
                    observation.noise_reason_counts,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "request_latency_ms": observation.request_latency_ms,
                "error_type": observation.error_type,
                "error_message": observation.error_message,
                "persisted_at_bj": persisted_at.strftime("%Y-%m-%d %H:%M:%S"),
                "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
            }
        )
    return rows


def _item_rows(
    report: ZhRouteShadowReport,
    *,
    collector_run_id: str,
    persisted_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in report.items:
        rows.append(
            {
                "route_shadow_item_id": _stable_id(
                    collector_run_id,
                    item.source_id,
                    item.surface_id,
                    item.url_canonical,
                ),
                "collector_run_id": collector_run_id,
                "query_group": report.group_id,
                "control_run_started_at_bj": report.started_at_bj,
                "treatment_observed_at_bj": report.observed_at_bj,
                "source_id": item.source_id,
                "surface_id": item.surface_id,
                "surface_role": item.surface_role,
                "publication_surface_id": item.publication_surface_id,
                "endpoint": item.endpoint,
                "transport": item.transport,
                "url": item.url,
                "url_canonical": item.url_canonical,
                "title": item.title,
                "published_at": item.published_at,
                "publication_time_source": item.publication_time_source,
                "publication_time_confidence": item.publication_time_confidence,
                "surface_rank": item.rank,
                "within_freshness": "TRUE" if item.within_freshness else "FALSE",
                "control_overlap": "TRUE" if item.control_overlap else "FALSE",
                "noise_reason": item.noise_reason,
                "route_contract_version": report.contract_version,
                "route_discovery_version": report.version,
                "body_mode": report.body_mode,
                "persisted_at_bj": persisted_at.strftime("%Y-%m-%d %H:%M:%S"),
                "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
            }
        )
    return rows


def persist_zh_route_shadow_fail_open(
    store: Any,
    report: ZhRouteShadowReport | None,
    *,
    collector_run_id: str,
    persisted_at: datetime,
) -> dict[str, Any]:
    """Persist S1 evidence after the authoritative Control run has succeeded."""
    if report is None:
        return {
            "persisted": False,
            "error": "no_route_shadow_report",
            "route_rows": 0,
            "item_rows": 0,
        }
    if not collector_run_id:
        return {
            "persisted": False,
            "error": "missing_collector_run_id",
            "route_rows": 0,
            "item_rows": 0,
        }
    try:
        route_ws = _ensure_sheet(
            store,
            ROUTE_OBSERVATION_SHEET,
            ROUTE_OBSERVATION_HEADERS,
            rows=10000,
        )
        item_ws = _ensure_sheet(
            store,
            ROUTE_ITEM_SHEET,
            ROUTE_ITEM_HEADERS,
            rows=30000,
        )
        route_result = _append_new_rows(
            route_ws,
            ROUTE_OBSERVATION_HEADERS,
            _route_rows(report, collector_run_id=collector_run_id, persisted_at=persisted_at),
        )
        item_result = _append_new_rows(
            item_ws,
            ROUTE_ITEM_HEADERS,
            _item_rows(report, collector_run_id=collector_run_id, persisted_at=persisted_at),
        )
        return {
            "persisted": True,
            "error": "",
            "route_rows": route_result["inserted"],
            "item_rows": item_result["inserted"],
            "route_rows_skipped_existing": route_result["skipped_existing"],
            "item_rows_skipped_existing": item_result["skipped_existing"],
        }
    except Exception as exc:
        return {
            "persisted": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "route_rows": 0,
            "item_rows": 0,
        }


__all__ = [
    "ROUTE_ITEM_HEADERS",
    "ROUTE_ITEM_SHEET",
    "ROUTE_OBSERVATION_HEADERS",
    "ROUTE_OBSERVATION_SHEET",
    "ROUTE_SHADOW_TELEMETRY_VERSION",
    "persist_zh_route_shadow_fail_open",
]
