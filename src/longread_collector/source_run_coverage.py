from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timedelta
from typing import Any, Iterable

from dateutil import parser as date_parser

SOURCE_RUN_COVERAGE_SHEET = "collector_source_run_coverage"
SOURCE_RUN_COVERAGE_VERSION = "run-source-coverage-v0.2"

SOURCE_RUN_COVERAGE_HEADERS = [
    "coverage_id",
    "collector_run_id",
    "query_group",
    "run_started_at_bj",
    "source_id",
    "source_name",
    "language",
    "selected",
    "selection_reason",
    "scan_age_hours",
    "native_attempted",
    "native_status",
    "selected_method",
    "selected_endpoint",
    "native_results_count",
    "fallback_attempted",
    "fallback_status",
    "fallback_results_count",
    "route_status",
    "raw_observation_count",
    "dated_observation_count",
    "oldest_observed_published_at",
    "newest_observed_published_at",
    "observed_horizon_hours",
    "coverage_confidence",
    "attempts_json",
    "persisted_at_bj",
    "coverage_version",
]

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _column_name(column_number: int) -> str:
    if column_number < 1:
        raise ValueError("column_number must be positive")
    result = ""
    current = column_number
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _parse_datetime(value: Any, tz: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    else:
        parsed = parsed.astimezone(tz)
    return parsed


def _coverage_boundary(value: Any, parsed: datetime, started: datetime) -> datetime:
    """Return the oldest instant that the observation can safely prove covered.

    A date-only value such as ``2026-08-17`` does not prove that the article was
    available at 00:00.  Its latest possible publication instant is the end of
    that calendar day, so the conservative lower-bound boundary is the next
    day's midnight.  If the scan occurs before that boundary, the observation
    proves zero lookback hours and the run start itself becomes the boundary.

    Timestamp-precision evidence keeps its literal instant.
    """

    text = str(value or "").strip()
    if _DATE_ONLY_RE.fullmatch(text):
        next_day = datetime.combine(
            parsed.date() + timedelta(days=1),
            time.min,
            tzinfo=started.tzinfo,
        )
        return min(started, next_day)
    return parsed


def _item_source_id(item: Any) -> str:
    metadata = getattr(item, "metadata", None) or {}
    source_id = str(metadata.get("source_id", "") or "").strip()
    if source_id:
        return source_id
    query_or_source = str(getattr(item, "query_or_source", "") or "").strip()
    if query_or_source.startswith("source:"):
        return query_or_source.split(":", 1)[1].strip()
    return ""


def _item_published_at(item: Any) -> Any:
    return getattr(item, "published_at", "")


def _native_status(log: dict[str, Any] | None) -> str:
    if log is None:
        return "not_attempted"
    if bool(log.get("success")) and int(log.get("results_count") or 0) > 0:
        return "success"
    attempts = list(log.get("attempts") or [])
    if attempts:
        has_error = any(
            str(attempt.get("error_type", "") or "").strip()
            or str(attempt.get("error_message", "") or "").strip()
            for attempt in attempts
        )
        has_completed_request = any(
            attempt.get("http_status") not in {None, ""}
            or "results_count" in attempt
            for attempt in attempts
        )
        if has_completed_request and not has_error:
            return "zero_results"
    return "failed"


def _fallback_status(
    log: dict[str, Any] | None,
    *,
    expected: bool,
) -> str:
    if log is None:
        return "attempted_unknown" if expected else "not_used"
    if not bool(log.get("success")):
        return "failed"
    if int(log.get("results_count") or 0) > 0:
        return "success"
    return "zero_results"


def _coverage_id(run_id: str, source_id: str) -> str:
    return hashlib.sha256(f"{run_id}|{source_id}".encode("utf-8")).hexdigest()[:24]


def _selection_reason(source: dict[str, Any]) -> str:
    reason = str(source.get("_selection_reason", "") or "").strip()
    return reason or "coverage_rotation"


def _route_status(
    *,
    native_status: str,
    fallback_status: str,
    dated_observation_count: int,
) -> str:
    if native_status == "success":
        return "native_covered" if dated_observation_count > 0 else "native_success_date_unknown"
    if fallback_status == "success":
        return "fallback_only"
    if fallback_status == "zero_results":
        return "fallback_zero"
    if fallback_status == "failed":
        return "fallback_failed"
    if fallback_status == "attempted_unknown":
        return "fallback_unknown"
    if native_status == "zero_results":
        return "native_zero_results"
    if native_status == "failed":
        return "native_failed"
    return "not_attempted"


def build_source_run_coverage_rows(
    *,
    run_id: str,
    query_group: str,
    started: datetime,
    selected_sources: Iterable[dict[str, Any]],
    native_logs: Iterable[dict[str, Any]],
    native_items: Iterable[Any],
    firecrawl_logs: Iterable[dict[str, Any]],
    firecrawl_items: Iterable[Any],
    persisted_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build one immutable-observation row for every selected registered source.

    Coverage horizons are evidence lower bounds derived only from dated native
    observations. Date-only observations use the end of their calendar day as
    the conservative coverage boundary rather than silently assuming 00:00.
    Directed Firecrawl search can prove fallback activity or raw capture, but it
    never manufactures native-route coverage.
    """

    selected = list(selected_sources)
    native_logs_by_source = {
        str(log.get("source_id", "") or "").strip(): log
        for log in native_logs
        if str(log.get("source_id", "") or "").strip()
    }
    fallback_logs_by_source: dict[str, dict[str, Any]] = {}
    for log in firecrawl_logs:
        query_id = str(log.get("query_id", "") or "").strip()
        purpose = str(log.get("purpose", "") or "").strip()
        if not query_id.startswith("source:") or purpose != "directed_source_scan":
            continue
        fallback_logs_by_source[query_id.split(":", 1)[1]] = log

    native_items_by_source: dict[str, list[Any]] = {}
    for item in native_items:
        source_id = _item_source_id(item)
        if source_id:
            native_items_by_source.setdefault(source_id, []).append(item)

    fallback_items_by_source: dict[str, list[Any]] = {}
    for item in firecrawl_items:
        source_id = _item_source_id(item)
        metadata = getattr(item, "metadata", None) or {}
        if source_id and str(metadata.get("purpose", "")) == "directed_source_scan":
            fallback_items_by_source.setdefault(source_id, []).append(item)

    persisted = persisted_at or datetime.now(started.tzinfo)
    rows: list[dict[str, Any]] = []
    for source in selected:
        source_id = str(source.get("source_id", "") or "").strip()
        if not source_id:
            continue
        native_log = native_logs_by_source.get(source_id)
        fallback_log = fallback_logs_by_source.get(source_id)
        source_native_items = native_items_by_source.get(source_id, [])
        source_fallback_items = fallback_items_by_source.get(source_id, [])

        dated: list[tuple[datetime, datetime]] = []
        for item in source_native_items:
            raw_published = _item_published_at(item)
            parsed = _parse_datetime(raw_published, started.tzinfo)
            if parsed is not None and parsed <= started:
                dated.append(
                    (
                        parsed,
                        _coverage_boundary(raw_published, parsed, started),
                    )
                )

        literal_dates = [parsed for parsed, _ in dated]
        coverage_boundaries = [boundary for _, boundary in dated]
        # The persisted oldest value is deliberately the conservative coverage
        # boundary because v1.3 consumes it as interval evidence.  For exact
        # timestamps it equals the literal publication instant; for date-only
        # evidence it moves to the next-day boundary and therefore cannot
        # overstate proven route coverage.
        oldest = min(coverage_boundaries) if coverage_boundaries else None
        newest = max(literal_dates) if literal_dates else None
        horizon = (
            round(max(0.0, (started - oldest).total_seconds() / 3600), 3)
            if oldest is not None
            else ""
        )
        native_state = _native_status(native_log)
        fallback_expected = bool((native_log or {}).get("fallback_needed"))
        fallback_state = _fallback_status(
            fallback_log,
            expected=fallback_expected,
        )
        route_state = _route_status(
            native_status=native_state,
            fallback_status=fallback_state,
            dated_observation_count=len(dated),
        )
        raw_count = len(source_native_items) + len(source_fallback_items)

        rows.append(
            {
                "coverage_id": _coverage_id(run_id, source_id),
                "collector_run_id": run_id,
                "query_group": query_group,
                "run_started_at_bj": started.strftime("%Y-%m-%d %H:%M:%S"),
                "source_id": source_id,
                "source_name": str(source.get("source_name", "") or ""),
                "language": str(source.get("language", "") or ""),
                "selected": "TRUE",
                "selection_reason": _selection_reason(source),
                "scan_age_hours": source.get("_selection_scan_age_hours", ""),
                "native_attempted": "TRUE" if native_log is not None else "FALSE",
                "native_status": native_state,
                "selected_method": str((native_log or {}).get("selected_method", "") or ""),
                "selected_endpoint": str((native_log or {}).get("selected_endpoint", "") or ""),
                "native_results_count": int((native_log or {}).get("results_count") or 0),
                "fallback_attempted": "TRUE" if fallback_log is not None or fallback_expected else "FALSE",
                "fallback_status": fallback_state,
                "fallback_results_count": int((fallback_log or {}).get("results_count") or 0),
                "route_status": route_state,
                "raw_observation_count": raw_count,
                "dated_observation_count": len(dated),
                "oldest_observed_published_at": oldest.strftime("%Y-%m-%d %H:%M:%S") if oldest else "",
                "newest_observed_published_at": newest.strftime("%Y-%m-%d %H:%M:%S") if newest else "",
                "observed_horizon_hours": horizon,
                "coverage_confidence": "lower_bound" if route_state == "native_covered" else "unknown",
                "attempts_json": json.dumps(
                    list((native_log or {}).get("attempts") or []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
                "persisted_at_bj": persisted.strftime("%Y-%m-%d %H:%M:%S"),
                "coverage_version": SOURCE_RUN_COVERAGE_VERSION,
            }
        )
    return rows


def _ensure_coverage_worksheet(store: Any) -> Any:
    try:
        ws = store.book.worksheet(SOURCE_RUN_COVERAGE_SHEET)
    except Exception as exc:
        if exc.__class__.__name__ != "WorksheetNotFound":
            raise
        ws = store.book.add_worksheet(
            title=SOURCE_RUN_COVERAGE_SHEET,
            rows=5000,
            cols=len(SOURCE_RUN_COVERAGE_HEADERS),
        )
        ws.append_row(SOURCE_RUN_COVERAGE_HEADERS, value_input_option="USER_ENTERED")
        return ws

    values = ws.get_all_values()
    if not values:
        ws.append_row(SOURCE_RUN_COVERAGE_HEADERS, value_input_option="USER_ENTERED")
        return ws
    if list(values[0]) != SOURCE_RUN_COVERAGE_HEADERS:
        raise ValueError(
            f"{SOURCE_RUN_COVERAGE_SHEET} header mismatch; refusing schema mutation"
        )
    return ws


def upsert_source_run_coverage(store: Any, rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    row_list = list(rows)
    if not row_list:
        return {"inserted": 0, "updated": 0, "total": 0}
    ws = _ensure_coverage_worksheet(store)
    values = ws.get_all_values()
    existing = {
        str(row[0]): index
        for index, row in enumerate(values[1:], start=2)
        if row and str(row[0]).strip()
    }
    inserted_rows: list[list[Any]] = []
    updated = 0
    end_column = _column_name(len(SOURCE_RUN_COVERAGE_HEADERS))
    for row in row_list:
        serialized = [row.get(header, "") for header in SOURCE_RUN_COVERAGE_HEADERS]
        coverage_id = str(row.get("coverage_id", ""))
        if coverage_id in existing:
            row_no = existing[coverage_id]
            ws.update(
                range_name=f"A{row_no}:{end_column}{row_no}",
                values=[serialized],
                value_input_option="USER_ENTERED",
            )
            updated += 1
        else:
            inserted_rows.append(serialized)
    if inserted_rows:
        ws.append_rows(inserted_rows, value_input_option="USER_ENTERED")
    return {
        "inserted": len(inserted_rows),
        "updated": updated,
        "total": len(row_list),
    }


def persist_source_run_coverage_fail_open(
    store: Any,
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Persist measurement telemetry without making Collector availability depend on it."""

    try:
        result = upsert_source_run_coverage(store, rows)
        return {"persisted": True, "error": "", **result}
    except Exception as exc:
        return {
            "persisted": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "inserted": 0,
            "updated": 0,
            "total": 0,
        }