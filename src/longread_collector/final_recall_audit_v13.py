"""Final Recall v1.3 with run-realized source coverage denominators.

v1.3 preserves v1.2 raw capture and item-observation semantics, but it no longer
allows static source-registry route declarations to manufacture the strict
surface-recall denominator. Strict source coverage requires durable run × source
telemetry from ``collector_source_run_coverage``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any

from .config import get_settings
from .final_recall_audit import _ensure_sheet, _ratio, _replace_date_rows, _sheet_datetime
from .final_recall_audit_v12 import (
    AUDIT_V12_HEADERS,
    DAILY_V12_HEADERS,
    _upsert_daily,
    audit_final_recall_v12,
)
from .final_recall_audit_v12_runner import PHASE0A_STRICT_SNAPSHOT_START_BJ
from .registry_matching_v056 import match_registry
from .sheets import RUN_HEADERS, SOURCE_HEADERS, GoogleSheetStore
from .source_run_coverage import (
    SOURCE_RUN_COVERAGE_HEADERS,
    SOURCE_RUN_COVERAGE_SHEET,
    SOURCE_RUN_COVERAGE_VERSION,
)

AUDIT_VERSION = "final-recall-audit-v1.3-run-realized-coverage"
DENOMINATOR_VERSION = "run-realized-source-coverage-v1.3"
MEASUREMENT_VERSION = "run-realized-source-coverage-v1.3"

REALIZED_HEADERS = [
    "realized_source_id",
    "publication_precision",
    "coverage_ledger_started_at_bj",
    "coverage_ledger_observation_status",
    "coverage_candidate_run_count",
    "coverage_persistence_gap_runs",
    "source_coverage_row_count",
    "realized_coverage_status",
    "realized_coverage_run_id",
    "realized_route_status",
    "realized_selected_method",
    "realized_selected_endpoint",
    "realized_oldest_observed_published_at",
    "realized_newest_observed_published_at",
    "realized_horizon_hours",
    "realized_coverage_confidence",
    "coverage_contract_denominator_status",
    "conditional_surface_denominator_status",
]
AUDIT_V13_HEADERS = AUDIT_V12_HEADERS + REALIZED_HEADERS

DAILY_REALIZED_HEADERS = [
    "realized_coverage_contract_denominator",
    "realized_coverage_contract_covered",
    "realized_coverage_contract_rate",
    "conditional_surface_recall_denominator",
    "conditional_surface_recall_discovered",
    "conditional_surface_recall",
    "conditional_surface_editable",
    "conditional_surface_editable_recall",
    "coverage_ledger_partial_items",
    "coverage_evidence_gap_items",
    "source_not_selected_items",
    "fallback_only_items",
    "coverage_ledger_started_at_bj",
    "realized_measurement_version",
]
DAILY_V13_HEADERS = DAILY_V12_HEADERS + DAILY_REALIZED_HEADERS

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIDNIGHT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]00:00(?::00(?:\.0+)?)?$")


@dataclass(frozen=True, slots=True)
class CoverageEvaluation:
    realized_source_id: str = ""
    publication_precision: str = "unknown"
    coverage_ledger_started_at_bj: str = ""
    coverage_ledger_observation_status: str = "unavailable"
    coverage_candidate_run_count: int = 0
    coverage_persistence_gap_runs: int = 0
    source_coverage_row_count: int = 0
    realized_coverage_status: str = "coverage_ledger_unavailable"
    realized_coverage_run_id: str = ""
    realized_route_status: str = ""
    realized_selected_method: str = ""
    realized_selected_endpoint: str = ""
    realized_oldest_observed_published_at: str = ""
    realized_newest_observed_published_at: str = ""
    realized_horizon_hours: Any = ""
    realized_coverage_confidence: str = ""
    coverage_contract_denominator_status: str = "excluded"
    conditional_surface_denominator_status: str = "excluded"

    def as_dict(self) -> dict[str, Any]:
        return {header: getattr(self, header) for header in REALIZED_HEADERS}


def _marker_map(notes: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    for fragment in str(notes or "").split(";"):
        part = fragment.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _coverage_marker(row: dict[str, Any]) -> tuple[bool, bool]:
    marker = _marker_map(row.get("notes", ""))
    instrumented = marker.get("source_run_coverage_version") == SOURCE_RUN_COVERAGE_VERSION
    persisted = marker.get("source_run_coverage_persisted", "").upper() == "TRUE"
    return instrumented, persisted


def _run_language(row: dict[str, Any]) -> str:
    group = str(row.get("query_group", "") or "")
    return "zh" if group.startswith("zh_") else "en"


def _publication_precision(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "unknown"
    if _DATE_ONLY_RE.match(text) or _MIDNIGHT_RE.match(text):
        return "date"
    if ":" in text or "T" in text:
        return "datetime"
    return "unknown"


def _full_snapshot_measurement(item: dict[str, Any], tz: Any) -> bool:
    if str(item.get("observation_coverage_status", "")) != "full":
        return False
    observation_start = _sheet_datetime(item.get("item_observation_started_at_bj"), tz)
    if observation_start is None:
        return False
    accepted_start = PHASE0A_STRICT_SNAPSHOT_START_BJ.replace(tzinfo=tz)
    return observation_start >= accepted_start


def _measurement_valid(item: dict[str, Any]) -> bool:
    if str(item.get("match_status", "")) == "not_yet_available":
        return False
    if str(item.get("observation_coverage_status", "")) in {
        "measurement_invalid",
        "not_yet_available",
    }:
        return False
    if str(item.get("measurement_age_bucket", "")) == "invalid":
        return False
    return True


def _run_started(row: dict[str, Any], tz: Any) -> datetime | None:
    return _sheet_datetime(row.get("started_at_bj"), tz)


def _coverage_run_started(row: dict[str, Any], tz: Any) -> datetime | None:
    return _sheet_datetime(row.get("run_started_at_bj"), tz)


def _coverage_relation(
    *,
    published_raw: Any,
    published_at: datetime | None,
    coverage_row: dict[str, Any],
    tz: Any,
) -> str:
    if str(coverage_row.get("route_status", "")) != "native_covered":
        return "not_native_covered"
    run_started = _coverage_run_started(coverage_row, tz)
    oldest = _sheet_datetime(coverage_row.get("oldest_observed_published_at"), tz)
    if published_at is None or run_started is None or oldest is None:
        return "unknown"

    precision = _publication_precision(published_raw)
    if precision == "datetime":
        return "covered" if oldest <= published_at <= run_started else "outside"
    if precision == "date":
        day_start = datetime.combine(published_at.date(), time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        if oldest <= day_start and run_started >= day_end:
            return "covered"
        if run_started >= day_start and oldest < day_end:
            return "ambiguous"
        return "outside"
    return "unknown"


def _best_route_row(rows: list[dict[str, Any]], tz: Any) -> dict[str, Any] | None:
    priority = {
        "native_covered": 0,
        "native_success_date_unknown": 1,
        "fallback_only": 2,
        "fallback_zero": 3,
        "fallback_failed": 4,
        "fallback_unknown": 5,
        "native_zero_results": 6,
        "native_failed": 7,
        "not_attempted": 8,
    }

    def key(row: dict[str, Any]) -> tuple[int, datetime]:
        return (
            priority.get(str(row.get("route_status", "")), 99),
            _coverage_run_started(row, tz) or datetime.max.replace(tzinfo=tz),
        )

    return min(rows, key=key) if rows else None


def _route_failure_status(rows: list[dict[str, Any]]) -> str:
    states = {str(row.get("route_status", "")) for row in rows}
    if "native_success_date_unknown" in states:
        return "observed_horizon_not_established"
    if "fallback_only" in states:
        return "fallback_only_target_missing"
    if "fallback_zero" in states:
        return "fallback_zero_results"
    if "fallback_failed" in states:
        return "fallback_route_failed"
    if "fallback_unknown" in states:
        return "fallback_route_unknown"
    if "native_zero_results" in states:
        return "native_zero_observation"
    if "native_failed" in states:
        return "native_route_failed"
    return "source_selected_not_attempted"


def evaluate_realized_coverage(
    *,
    item: dict[str, Any],
    source_row: dict[str, Any] | None,
    coverage_rows: list[dict[str, Any]],
    collector_runs: list[dict[str, Any]],
    ledger_started_at: datetime | None,
    tz: Any,
) -> CoverageEvaluation:
    precision = _publication_precision(item.get("published_date", ""))
    if source_row is None:
        return CoverageEvaluation(
            publication_precision=precision,
            coverage_ledger_started_at_bj=(
                ledger_started_at.strftime("%Y-%m-%d %H:%M:%S")
                if ledger_started_at
                else ""
            ),
            coverage_ledger_observation_status="not_applicable",
            realized_coverage_status="outside_registry",
            coverage_contract_denominator_status="outside_registry",
        )

    source_id = str(source_row.get("source_id", "") or "")
    language = str(source_row.get("language", "") or "")
    ledger_text = (
        ledger_started_at.strftime("%Y-%m-%d %H:%M:%S") if ledger_started_at else ""
    )
    observation_start = _sheet_datetime(item.get("item_observation_started_at_bj"), tz)
    cutoff = _sheet_datetime(item.get("cutoff_at_bj"), tz)
    published_at = _sheet_datetime(item.get("published_date"), tz)

    if not _measurement_valid(item) or observation_start is None or cutoff is None:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="measurement_invalid",
            realized_coverage_status="measurement_invalid",
            coverage_contract_denominator_status="measurement_invalid",
        )
    if ledger_started_at is None:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_observation_status="unavailable",
            realized_coverage_status="coverage_ledger_unavailable",
            coverage_contract_denominator_status="coverage_ledger_unavailable",
        )
    if observation_start < ledger_started_at:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="partial",
            realized_coverage_status="coverage_ledger_partial_observation",
            coverage_contract_denominator_status="coverage_ledger_partial_observation",
        )

    candidate_runs = [
        row
        for row in collector_runs
        if (
            _run_language(row) == language
            and (started := _run_started(row, tz)) is not None
            and observation_start <= started <= cutoff
        )
    ]
    gaps = 0
    for row in candidate_runs:
        instrumented, persisted = _coverage_marker(row)
        if not instrumented or not persisted:
            gaps += 1
    if gaps:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="evidence_gap",
            coverage_candidate_run_count=len(candidate_runs),
            coverage_persistence_gap_runs=gaps,
            realized_coverage_status="coverage_evidence_gap",
            coverage_contract_denominator_status="coverage_evidence_gap",
        )

    source_rows = [
        row
        for row in coverage_rows
        if (
            str(row.get("source_id", "")) == source_id
            and (started := _coverage_run_started(row, tz)) is not None
            and observation_start <= started <= cutoff
        )
    ]
    contract_status = "coverage_contract_denominator"
    if not candidate_runs:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="full",
            coverage_candidate_run_count=0,
            source_coverage_row_count=0,
            realized_coverage_status="no_eligible_source_run_in_window",
            coverage_contract_denominator_status=contract_status,
        )
    if not source_rows:
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="full",
            coverage_candidate_run_count=len(candidate_runs),
            source_coverage_row_count=0,
            realized_coverage_status="source_not_selected_in_window",
            coverage_contract_denominator_status=contract_status,
        )

    native_rows = [
        row for row in source_rows if str(row.get("route_status", "")) == "native_covered"
    ]
    relations = [
        (_coverage_relation(
            published_raw=item.get("published_date", ""),
            published_at=published_at,
            coverage_row=row,
            tz=tz,
        ), row)
        for row in native_rows
    ]
    covered_rows = [row for relation, row in relations if relation == "covered"]
    if covered_rows:
        chosen = min(
            covered_rows,
            key=lambda row: _coverage_run_started(row, tz)
            or datetime.max.replace(tzinfo=tz),
        )
        conditional = (
            "conditional_surface_denominator"
            if _full_snapshot_measurement(item, tz)
            else "partial_snapshot_observation"
        )
        return CoverageEvaluation(
            realized_source_id=source_id,
            publication_precision=precision,
            coverage_ledger_started_at_bj=ledger_text,
            coverage_ledger_observation_status="full",
            coverage_candidate_run_count=len(candidate_runs),
            source_coverage_row_count=len(source_rows),
            realized_coverage_status="realized_route_covered",
            realized_coverage_run_id=str(chosen.get("collector_run_id", "")),
            realized_route_status=str(chosen.get("route_status", "")),
            realized_selected_method=str(chosen.get("selected_method", "")),
            realized_selected_endpoint=str(chosen.get("selected_endpoint", "")),
            realized_oldest_observed_published_at=str(
                chosen.get("oldest_observed_published_at", "")
            ),
            realized_newest_observed_published_at=str(
                chosen.get("newest_observed_published_at", "")
            ),
            realized_horizon_hours=chosen.get("observed_horizon_hours", ""),
            realized_coverage_confidence=str(chosen.get("coverage_confidence", "")),
            coverage_contract_denominator_status=contract_status,
            conditional_surface_denominator_status=conditional,
        )

    best = _best_route_row(source_rows, tz)
    best_payload = {
        "realized_coverage_run_id": str((best or {}).get("collector_run_id", "")),
        "realized_route_status": str((best or {}).get("route_status", "")),
        "realized_selected_method": str((best or {}).get("selected_method", "")),
        "realized_selected_endpoint": str((best or {}).get("selected_endpoint", "")),
        "realized_oldest_observed_published_at": str(
            (best or {}).get("oldest_observed_published_at", "")
        ),
        "realized_newest_observed_published_at": str(
            (best or {}).get("newest_observed_published_at", "")
        ),
        "realized_horizon_hours": (best or {}).get("observed_horizon_hours", ""),
        "realized_coverage_confidence": str((best or {}).get("coverage_confidence", "")),
    }
    if any(relation == "ambiguous" for relation, _ in relations):
        status = "publication_time_boundary_ambiguous"
    elif native_rows:
        status = "target_outside_observed_horizon"
    else:
        status = _route_failure_status(source_rows)

    return CoverageEvaluation(
        realized_source_id=source_id,
        publication_precision=precision,
        coverage_ledger_started_at_bj=ledger_text,
        coverage_ledger_observation_status="full",
        coverage_candidate_run_count=len(candidate_runs),
        source_coverage_row_count=len(source_rows),
        realized_coverage_status=status,
        coverage_contract_denominator_status=contract_status,
        **best_payload,
    )


def _discovered(item: dict[str, Any]) -> bool:
    return str(item.get("match_status", "")) in {
        "captured_eligible",
        "captured_but_rejected",
        "captured_extraction_failed",
    }


def _editable(item: dict[str, Any]) -> bool:
    return str(item.get("match_status", "")) == "captured_eligible"


def _realized_summary(
    items: list[dict[str, Any]],
    ledger_started_at: datetime | None,
) -> dict[str, Any]:
    contract = [
        row
        for row in items
        if row.get("coverage_contract_denominator_status") == "coverage_contract_denominator"
    ]
    covered = [
        row for row in contract if row.get("realized_coverage_status") == "realized_route_covered"
    ]
    conditional = [
        row
        for row in items
        if row.get("conditional_surface_denominator_status") == "conditional_surface_denominator"
    ]
    conditional_discovered = sum(_discovered(row) for row in conditional)
    conditional_editable = sum(_editable(row) for row in conditional)
    return {
        "realized_coverage_contract_denominator": len(contract),
        "realized_coverage_contract_covered": len(covered),
        "realized_coverage_contract_rate": _ratio(len(covered), len(contract)),
        "conditional_surface_recall_denominator": len(conditional),
        "conditional_surface_recall_discovered": conditional_discovered,
        "conditional_surface_recall": _ratio(conditional_discovered, len(conditional)),
        "conditional_surface_editable": conditional_editable,
        "conditional_surface_editable_recall": _ratio(conditional_editable, len(conditional)),
        "coverage_ledger_partial_items": sum(
            row.get("realized_coverage_status") == "coverage_ledger_partial_observation"
            for row in items
        ),
        "coverage_evidence_gap_items": sum(
            row.get("realized_coverage_status") == "coverage_evidence_gap"
            for row in items
        ),
        "source_not_selected_items": sum(
            row.get("realized_coverage_status") == "source_not_selected_in_window"
            for row in items
        ),
        "fallback_only_items": sum(
            row.get("realized_coverage_status") == "fallback_only_target_missing"
            for row in items
        ),
        "coverage_ledger_started_at_bj": (
            ledger_started_at.strftime("%Y-%m-%d %H:%M:%S")
            if ledger_started_at
            else ""
        ),
        "realized_measurement_version": MEASUREMENT_VERSION,
    }


def _read_coverage_rows(store: GoogleSheetStore) -> list[dict[str, Any]]:
    try:
        ws = store.book.worksheet(SOURCE_RUN_COVERAGE_SHEET)
    except Exception as exc:
        if exc.__class__.__name__ == "WorksheetNotFound":
            return []
        raise
    return ws.get_all_records(expected_headers=SOURCE_RUN_COVERAGE_HEADERS)


def _ledger_start(collector_runs: list[dict[str, Any]], tz: Any) -> datetime | None:
    starts = []
    for row in collector_runs:
        instrumented, _ = _coverage_marker(row)
        started = _run_started(row, tz)
        if instrumented and started is not None:
            starts.append(started)
    return min(starts) if starts else None


def audit_final_recall_v13(
    store: GoogleSheetStore,
    *,
    report_date: date,
    cutoff_time: str = "07:35",
    max_observation_days: int = 14,
    write: bool = True,
) -> dict[str, Any]:
    base = audit_final_recall_v12(
        store,
        report_date=report_date,
        cutoff_time=cutoff_time,
        max_observation_days=max_observation_days,
        write=False,
    )
    source_rows = store.book.worksheet("source_registry").get_all_records(
        expected_headers=SOURCE_HEADERS
    )
    collector_runs = store.book.worksheet("collector_runs").get_all_records(
        expected_headers=RUN_HEADERS
    )
    coverage_rows = _read_coverage_rows(store)
    ledger_started_at = _ledger_start(collector_runs, store.tz)

    items: list[dict[str, Any]] = []
    for base_item in base["items"]:
        item = dict(base_item)
        source_row = match_registry(item, source_rows)
        evaluation = evaluate_realized_coverage(
            item=item,
            source_row=source_row,
            coverage_rows=coverage_rows,
            collector_runs=collector_runs,
            ledger_started_at=ledger_started_at,
            tz=store.tz,
        )
        item.update(evaluation.as_dict())
        item["audit_version"] = AUDIT_VERSION
        items.append(item)

    summary = dict(base["summary"])
    summary.update(_realized_summary(items, ledger_started_at))
    summary["audit_version"] = AUDIT_VERSION
    summary["denominator_version"] = DENOMINATOR_VERSION

    result = {
        "summary": summary,
        "items": items,
        "snapshot_mode": base.get("snapshot_mode", ""),
    }
    if write:
        audit_ws = _ensure_sheet(
            store,
            "final_recall_audit_v13",
            AUDIT_V13_HEADERS,
            rows=5000,
        )
        daily_ws = _ensure_sheet(
            store,
            "final_recall_daily_v13",
            DAILY_V13_HEADERS,
            rows=1000,
        )
        report_text = report_date.isoformat()
        _replace_date_rows(
            audit_ws,
            date_column=2,
            report_date=report_text,
            rows=[
                [row.get(header, "") for header in AUDIT_V13_HEADERS]
                for row in items
            ],
        )
        _upsert_daily(
            daily_ws,
            report_text,
            [summary.get(header, "") for header in DAILY_V13_HEADERS],
        )
    return result


def no_final_items_summary(report_date: date) -> dict[str, Any]:
    return {
        "report_date": report_date.isoformat(),
        "audit_status": "no_final_items",
        "audit_version": AUDIT_VERSION,
        "measurement_version": MEASUREMENT_VERSION,
        "write_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit final recall with run-realized source coverage"
    )
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--cutoff-time", default="07:35")
    parser.add_argument("--max-observation-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target_date = date.fromisoformat(args.report_date)
    settings = get_settings()
    store = GoogleSheetStore(settings)
    try:
        result = audit_final_recall_v13(
            store,
            report_date=target_date,
            cutoff_time=args.cutoff_time,
            max_observation_days=args.max_observation_days,
            write=not args.dry_run,
        )
    except ValueError as exc:
        if str(exc).startswith("No final_items found for report_date="):
            print(no_final_items_summary(target_date))
            return
        raise
    print(result["summary"])


if __name__ == "__main__":
    main()
