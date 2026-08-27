"""Read-only Google Sheets runner for the Chinese Route Shadow S1 audit.

The runner never creates a worksheet and never writes cells. Missing S1 sidecar
sheets are represented as empty evidence so the audit can distinguish
NOT_EVALUABLE/FAIL instead of manufacturing state. The canonical entry point
also applies the real PR #134 activation boundary so pre-S1 historical runs are
never mislabeled as Treatment failures.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

from .sheets import SCOPES, _retry_sheet_call
from .source_run_coverage import SOURCE_RUN_COVERAGE_HEADERS, SOURCE_RUN_COVERAGE_SHEET
from .v06.shadow.run_summary_persistence import (
    SHADOW_RUN_SUMMARY_HEADERS,
    SHADOW_RUN_SUMMARY_SHEET,
)
from .zh_route_shadow_s1_cohort_guard_v1 import audit_prospective_s1_run
from .zh_route_shadow_telemetry_v1 import (
    ROUTE_ITEM_HEADERS,
    ROUTE_ITEM_SHEET,
    ROUTE_OBSERVATION_HEADERS,
    ROUTE_OBSERVATION_SHEET,
)


def _read_records(book: Any, title: str, headers: list[str], *, optional: bool = False) -> list[dict[str, Any]]:
    try:
        ws = _retry_sheet_call(lambda: book.worksheet(title))
    except WorksheetNotFound:
        if optional:
            return []
        raise
    values = _retry_sheet_call(ws.get_all_values)
    if not values:
        return []
    if list(values[0]) != headers:
        raise ValueError(f"{title} header mismatch; refusing read with unknown schema")
    return [
        {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
        for row in values[1:]
        if any(str(cell or "").strip() for cell in row)
    ]


def run_read_only_s1_audit(
    *,
    collector_run_id: str,
    sheet_id: str,
    service_account_file: str,
) -> dict[str, Any]:
    creds = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    book = _retry_sheet_call(lambda: client.open_by_key(sheet_id))

    # collector_runs is historical and its live sheet contains extended columns
    # beyond the old RUN_HEADERS constant, so read by its actual first-row schema.
    run_ws = _retry_sheet_call(lambda: book.worksheet("collector_runs"))
    run_values = _retry_sheet_call(run_ws.get_all_values)
    run_headers = list(run_values[0]) if run_values else []
    run_rows = [
        {header: row[index] if index < len(row) else "" for index, header in enumerate(run_headers)}
        for row in run_values[1:]
        if row and str(row[0] or "").strip() == collector_run_id
    ]

    coverage_rows = [
        row for row in _read_records(book, SOURCE_RUN_COVERAGE_SHEET, SOURCE_RUN_COVERAGE_HEADERS)
        if str(row.get("collector_run_id", "")).strip() == collector_run_id
    ]
    shadow_rows = [
        row for row in _read_records(
            book, SHADOW_RUN_SUMMARY_SHEET, SHADOW_RUN_SUMMARY_HEADERS, optional=True
        )
        if str(row.get("collector_run_id", "")).strip() == collector_run_id
    ]
    route_rows = [
        row for row in _read_records(
            book, ROUTE_OBSERVATION_SHEET, ROUTE_OBSERVATION_HEADERS, optional=True
        )
        if str(row.get("collector_run_id", "")).strip() == collector_run_id
    ]
    item_rows = [
        row for row in _read_records(
            book, ROUTE_ITEM_SHEET, ROUTE_ITEM_HEADERS, optional=True
        )
        if str(row.get("collector_run_id", "")).strip() == collector_run_id
    ]

    return audit_prospective_s1_run(
        collector_run_id=collector_run_id,
        run_rows=run_rows,
        coverage_rows=coverage_rows,
        shadow_summary_rows=shadow_rows,
        route_observation_rows=route_rows,
        route_item_rows=item_rows,
    ).as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only S1 Natural Shadow acceptance audit")
    parser.add_argument("collector_run_id")
    parser.add_argument("--sheet-id", default=os.getenv("GOOGLE_SHEET_ID", ""))
    parser.add_argument(
        "--service-account-file",
        default=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", ""),
    )
    args = parser.parse_args()
    if not args.sheet_id or not args.service_account_file:
        parser.error("GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_FILE are required")
    report = run_read_only_s1_audit(
        collector_run_id=args.collector_run_id,
        sheet_id=args.sheet_id,
        service_account_file=args.service_account_file,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
