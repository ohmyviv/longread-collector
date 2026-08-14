"""Recall audit v1.2 with item-level observation windows and strict measurement coverage.

v1.1 correctly separated source-registry and effective-route denominators, but it
still matched every final recommendation against one global 48-hour snapshot
window. That makes older deep-read recommendations look undiscovered even when
the Collector captured them earlier in their legitimate editorial lifetime.

v1.2 preserves v1.1 history and source-coverage semantics while adding a new,
immutable-snapshot measurement contract:

* each selected final item is observed from its publication date to the 07:35
  report cutoff, with a hard maximum of 14 calendar days;
* final ``time_track`` remains an editorial label and QA signal, not a trusted
  historical clock, because older rows contain known label inconsistencies;
* items published before immutable snapshot instrumentation began are marked
  ``partial_observation`` and excluded from the strict headline denominator;
* source registry/effective-route coverage remains a separate denominator axis;
* v1.1 sheets are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from typing import Any

from .config import get_settings
from .final_recall_audit import (
    AUDIT_HEADERS,
    DAILY_HEADERS,
    _ensure_sheet,
    _latest_final_run,
    _parse_cutoff,
    _ratio,
    _replace_date_rows,
    _sheet_datetime,
    _source_pool_status,
    build_daily_summary,
    classify_match,
    select_best_match,
)
from .final_recall_audit_v11 import (
    AUDIT_V11_HEADERS,
    DAILY_V11_HEADERS,
    classify_source_coverage,
    enrich_recall_result,
)
from .normalization import canonicalize_url
from .recall_instrumentation import SNAPSHOT_HEADERS
from .sheets import RUN_HEADERS, SOURCE_HEADERS, GoogleSheetStore

AUDIT_VERSION = "final-recall-audit-v1.2-item-window"
DENOMINATOR_VERSION = "registry-route-item-observation-v1.2"
MEASUREMENT_VERSION = "item-observation-window-v1.2"
MAX_OBSERVATION_DAYS = 14

MEASUREMENT_HEADERS = [
    "final_time_track",
    "used_72h",
    "publication_age_days",
    "measurement_age_bucket",
    "item_observation_started_at_bj",
    "snapshot_coverage_started_at_bj",
    "observation_coverage_status",
    "track_window_status",
    "measurement_denominator_status",
]
AUDIT_V12_HEADERS = AUDIT_V11_HEADERS + MEASUREMENT_HEADERS

DAILY_MEASUREMENT_HEADERS = [
    "strict_effective_route_denominator",
    "strict_effective_route_discovered",
    "strict_effective_route_discovery_recall",
    "strict_effective_route_editable",
    "strict_effective_route_editable_recall",
    "age_0_3d_denominator",
    "age_0_3d_discovered",
    "age_0_3d_recall",
    "age_4_7d_denominator",
    "age_4_7d_discovered",
    "age_4_7d_recall",
    "age_8_14d_denominator",
    "age_8_14d_discovered",
    "age_8_14d_recall",
    "partial_observation_items",
    "measurement_invalid_items",
    "time_track_inconsistent_items",
    "snapshot_coverage_started_at_bj",
    "measurement_version",
]
DAILY_V12_HEADERS = DAILY_V11_HEADERS + DAILY_MEASUREMENT_HEADERS


def _truthy(value: Any) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _discovered(row: dict[str, Any]) -> bool:
    return str(row.get("match_status", "")) in {
        "captured_eligible",
        "captured_but_rejected",
        "captured_extraction_failed",
    }


def _editable(row: dict[str, Any]) -> bool:
    return str(row.get("match_status", "")) == "captured_eligible"


def _calendar_window_start(cutoff: datetime, max_observation_days: int) -> datetime:
    return datetime.combine(
        cutoff.date() - timedelta(days=max_observation_days),
        time.min,
        tzinfo=cutoff.tzinfo,
    )


def _publication_age_days(
    published_at: datetime | None,
    cutoff: datetime,
) -> int | None:
    if published_at is None:
        return None
    return (cutoff.date() - published_at.date()).days


def _age_bucket(age_days: int | None) -> str:
    if age_days is None or age_days < 0 or age_days > MAX_OBSERVATION_DAYS:
        return "invalid"
    if age_days <= 3:
        return "0_3d"
    if age_days <= 7:
        return "4_7d"
    return "8_14d"


def _measurement_validity(
    published_at: datetime | None,
    cutoff: datetime,
    *,
    max_observation_days: int,
) -> str:
    if published_at is None:
        return "missing_publication_date"
    if published_at > cutoff or published_at.date() > cutoff.date():
        return "not_yet_available"
    age_days = _publication_age_days(published_at, cutoff)
    if age_days is None or age_days < 0:
        return "not_yet_available"
    if age_days > max_observation_days:
        return "outside_editor_max_window"
    return "valid"


def _track_window_status(
    raw_track: Any,
    published_at: datetime | None,
    cutoff: datetime,
    validity: str,
) -> str:
    if validity != "valid":
        return f"measurement_{validity}"
    track = str(raw_track or "").strip()
    age_days = _publication_age_days(published_at, cutoff)
    if published_at is None or age_days is None:
        return "measurement_missing_publication_date"
    age_hours = (cutoff - published_at).total_seconds() / 3600

    if track == "timely":
        if age_hours <= 72:
            return "consistent_timely"
        # final_items stores publication date rather than reliable publication
        # time. A three-calendar-day item can still be inside 72h, so do not
        # turn that boundary uncertainty into a false editor-contract failure.
        if age_days == 3:
            return "timely_72h_boundary_ambiguous"
        return "inconsistent_timely_gt72h"
    if track == "deep_read":
        if age_days <= 7:
            return "consistent_deep_read"
        return "deep_read_exception_8_14d"
    if "深读" in track:
        return "legacy_non_enum_deep_read"
    if not track:
        return "missing_time_track"
    return "invalid_time_track"


def _observation_start(
    published_at: datetime | None,
    cutoff: datetime,
    *,
    max_observation_days: int,
    validity: str,
) -> datetime:
    max_start = _calendar_window_start(cutoff, max_observation_days)
    if validity == "valid" and published_at is not None:
        return published_at
    return max_start


def _observation_coverage_status(
    observation_start: datetime,
    snapshot_coverage_start: datetime | None,
    cutoff: datetime,
    validity: str,
) -> str:
    if validity == "not_yet_available":
        return "not_yet_available"
    if validity != "valid":
        return "measurement_invalid"
    if snapshot_coverage_start is None or snapshot_coverage_start > cutoff:
        return "unobservable"
    if snapshot_coverage_start <= observation_start:
        return "full"
    return "partial"


def _measurement_denominator_status(row: dict[str, Any]) -> str:
    validity = str(row.get("measurement_validity", "valid"))
    if validity == "not_yet_available":
        return "not_yet_available"
    if validity != "valid":
        return "measurement_invalid"
    if str(row.get("registry_status", "")) == "outside_registry":
        return "source_coverage_gap"
    if str(row.get("promotion_denominator_status", "")) != "effective_route_denominator":
        return "registered_no_effective_route"
    coverage = str(row.get("observation_coverage_status", ""))
    if coverage != "full":
        return "partial_observation" if coverage == "partial" else "unobservable"
    return "strict_effective_route_denominator"


def _snapshot_rows(
    store: GoogleSheetStore,
    *,
    cutoff: datetime,
    max_observation_days: int,
) -> tuple[list[dict[str, Any]], datetime | None]:
    rows = store.book.worksheet("collector_discovery_snapshot").get_all_records(
        expected_headers=SNAPSHOT_HEADERS
    )
    timed: list[tuple[datetime, dict[str, Any]]] = []
    for row in rows:
        captured = _sheet_datetime(row.get("captured_at_bj"), store.tz)
        if captured and captured <= cutoff:
            timed.append((captured, row))
    if not timed:
        return [], None
    coverage_start = min(captured for captured, _ in timed)
    max_start = _calendar_window_start(cutoff, max_observation_days)
    return [row for captured, row in timed if captured >= max_start], coverage_start


def _item_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    observation_start: datetime,
    cutoff: datetime,
    tz: Any,
) -> list[dict[str, Any]]:
    return [
        row
        for row in snapshots
        if (
            (captured := _sheet_datetime(row.get("captured_at_bj"), tz))
            and observation_start <= captured <= cutoff
        )
    ]


def _base_record(
    *,
    final_row: dict[str, Any],
    final_run_id: str,
    report_date: date,
    cutoff: datetime,
    observation_start: datetime,
    snapshots: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    store: GoogleSheetStore,
    audited_at: str,
) -> dict[str, Any]:
    final_raw_url = str(final_row.get("url_canonical") or final_row.get("url") or "")
    canonical = canonicalize_url(final_raw_url) if final_raw_url else ""
    source_pool_status = _source_pool_status(final_row, source_rows)
    published_at = _sheet_datetime(final_row.get("published_date"), store.tz)
    matched, match_type, manual_review = select_best_match(final_row, snapshots, store.tz)
    match_status, miss_stage = classify_match(
        matched,
        source_pool_status=source_pool_status,
        published_at=published_at,
        cutoff=cutoff,
    )
    item_index = int(final_row.get("item_index") or 0)
    audit_id = hashlib.sha256(
        f"{report_date.isoformat()}|{final_run_id}|{item_index}|{canonical}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "audit_id": audit_id,
        "report_date": report_date.isoformat(),
        "final_run_id": final_run_id,
        "item_index": item_index,
        "section": str(final_row.get("section", "")),
        "language": str(final_row.get("language", "")),
        "final_title": str(final_row.get("title", "")),
        "final_title_norm": str(final_row.get("title_norm", "")),
        "final_url": str(final_row.get("url", "")),
        "final_url_canonical": canonical,
        "final_source": str(final_row.get("canonical_source", "")),
        "published_date": str(final_row.get("published_date", "")),
        "cutoff_at_bj": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_started_at_bj": observation_start.strftime("%Y-%m-%d %H:%M:%S"),
        "source_pool_status": source_pool_status,
        "match_status": match_status,
        "match_type": match_type,
        "matched_snapshot_id": str(matched.get("snapshot_id", "")) if matched else "",
        "matched_article_id": str(matched.get("article_id", "")) if matched else "",
        "matched_url": str(matched.get("url_canonical") or matched.get("url") or "") if matched else "",
        "matched_title": str(matched.get("title", "")) if matched else "",
        "matched_source": str(matched.get("canonical_source", "")) if matched else "",
        "matched_first_seen_at_bj": str(matched.get("captured_at_bj", "")) if matched else "",
        "matched_run_id": str(matched.get("collector_run_id", "")) if matched else "",
        "matched_discovery_method": str(matched.get("discovery_method", "")) if matched else "",
        "prefilter_status": str(matched.get("prefilter_status", "")) if matched else "",
        "prefilter_reject_reason": str(matched.get("prefilter_reject_reason", "")) if matched else "",
        "extraction_status": str(matched.get("extraction_status", "")) if matched else "",
        "eligible_for_editor": str(matched.get("eligible_for_editor", "")) if matched else "",
        "candidate_disposition": str(matched.get("candidate_disposition", "")) if matched else "",
        "reject_reason": str(matched.get("reject_reason", "")) if matched else "",
        "content_cluster_id": str(matched.get("content_cluster_id", "")) if matched else "",
        "manual_review_required": str(manual_review).upper(),
        "notes": f"miss_stage={miss_stage}; snapshot_mode=immutable_snapshot; item_window=true",
        "audited_at_bj": audited_at,
        "audit_version": AUDIT_VERSION,
    }


def _measurement_summary(items: list[dict[str, Any]], snapshot_start: datetime | None) -> dict[str, Any]:
    strict = [
        row
        for row in items
        if row.get("measurement_denominator_status") == "strict_effective_route_denominator"
    ]
    strict_discovered = sum(_discovered(row) for row in strict)
    strict_editable = sum(_editable(row) for row in strict)
    result: dict[str, Any] = {
        "strict_effective_route_denominator": len(strict),
        "strict_effective_route_discovered": strict_discovered,
        "strict_effective_route_discovery_recall": _ratio(strict_discovered, len(strict)),
        "strict_effective_route_editable": strict_editable,
        "strict_effective_route_editable_recall": _ratio(strict_editable, len(strict)),
        "partial_observation_items": sum(
            row.get("measurement_denominator_status") == "partial_observation"
            for row in items
        ),
        "measurement_invalid_items": sum(
            row.get("measurement_denominator_status") == "measurement_invalid"
            for row in items
        ),
        "time_track_inconsistent_items": sum(
            str(row.get("track_window_status", "")).startswith("inconsistent_")
            or str(row.get("track_window_status", "")).startswith("legacy_non_enum_")
            or str(row.get("track_window_status", "")) in {"missing_time_track", "invalid_time_track"}
            for row in items
        ),
        "snapshot_coverage_started_at_bj": (
            snapshot_start.strftime("%Y-%m-%d %H:%M:%S") if snapshot_start else ""
        ),
        "measurement_version": MEASUREMENT_VERSION,
    }
    for bucket, prefix in (
        ("0_3d", "age_0_3d"),
        ("4_7d", "age_4_7d"),
        ("8_14d", "age_8_14d"),
    ):
        bucket_rows = [row for row in strict if row.get("measurement_age_bucket") == bucket]
        discovered = sum(_discovered(row) for row in bucket_rows)
        result[f"{prefix}_denominator"] = len(bucket_rows)
        result[f"{prefix}_discovered"] = discovered
        result[f"{prefix}_recall"] = _ratio(discovered, len(bucket_rows))
    return result


def _upsert_daily(ws: Any, report_date: str, row: list[object]) -> None:
    end_column_number = len(row)
    letters = ""
    current = end_column_number
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    for row_no, value in enumerate(ws.col_values(1)[1:], start=2):
        if str(value).strip() == report_date:
            ws.update(
                range_name=f"A{row_no}:{letters}{row_no}",
                values=[row],
                value_input_option="USER_ENTERED",
            )
            return
    ws.append_row(row, value_input_option="USER_ENTERED")


def audit_final_recall_v12(
    store: GoogleSheetStore,
    *,
    report_date: date,
    cutoff_time: str = "07:35",
    max_observation_days: int = MAX_OBSERVATION_DAYS,
    write: bool = True,
) -> dict[str, Any]:
    cutoff = _parse_cutoff(report_date, cutoff_time, store.tz)
    audited_at = datetime.now(store.tz).strftime("%Y-%m-%d %H:%M:%S")
    final_run_id, final_rows = _latest_final_run(
        store.book.worksheet("final_items").get_all_records(), report_date
    )
    source_rows = store.book.worksheet("source_registry").get_all_records(
        expected_headers=SOURCE_HEADERS
    )
    snapshots, snapshot_start = _snapshot_rows(
        store,
        cutoff=cutoff,
        max_observation_days=max_observation_days,
    )

    run_rows = store.book.worksheet("collector_runs").get_all_records(
        expected_headers=RUN_HEADERS
    )
    max_window_start = _calendar_window_start(cutoff, max_observation_days)
    collector_runs = [
        row
        for row in run_rows
        if (
            str(row.get("final_status", "")).lower() == "success"
            and (started := _sheet_datetime(row.get("started_at_bj"), store.tz))
            and max_window_start <= started <= cutoff
        )
    ]

    base_items: list[dict[str, Any]] = []
    measurement_by_audit_id: dict[str, dict[str, Any]] = {}
    for final_row in final_rows:
        published_at = _sheet_datetime(final_row.get("published_date"), store.tz)
        validity = _measurement_validity(
            published_at,
            cutoff,
            max_observation_days=max_observation_days,
        )
        observation_start = _observation_start(
            published_at,
            cutoff,
            max_observation_days=max_observation_days,
            validity=validity,
        )
        item_snapshots = _item_snapshots(
            snapshots,
            observation_start=observation_start,
            cutoff=cutoff,
            tz=store.tz,
        )
        record = _base_record(
            final_row=final_row,
            final_run_id=final_run_id,
            report_date=report_date,
            cutoff=cutoff,
            observation_start=observation_start,
            snapshots=item_snapshots,
            source_rows=source_rows,
            store=store,
            audited_at=audited_at,
        )
        age_days = _publication_age_days(published_at, cutoff)
        measurement_by_audit_id[record["audit_id"]] = {
            "final_time_track": str(final_row.get("time_track", "")),
            "used_72h": str(final_row.get("used_72h", "")),
            "publication_age_days": "" if age_days is None else age_days,
            "measurement_age_bucket": _age_bucket(age_days),
            "item_observation_started_at_bj": observation_start.strftime("%Y-%m-%d %H:%M:%S"),
            "snapshot_coverage_started_at_bj": (
                snapshot_start.strftime("%Y-%m-%d %H:%M:%S") if snapshot_start else ""
            ),
            "observation_coverage_status": _observation_coverage_status(
                observation_start,
                snapshot_start,
                cutoff,
                validity,
            ),
            "track_window_status": _track_window_status(
                final_row.get("time_track", ""),
                published_at,
                cutoff,
                validity,
            ),
            # Internal helper field removed before Sheet serialization.
            "measurement_validity": validity,
        }
        base_items.append(record)

    base_daily = build_daily_summary(
        base_items,
        report_date=report_date.isoformat(),
        final_run_id=final_run_id,
        collector_runs=collector_runs,
        cutoff=cutoff,
        lookback_hours=max_observation_days * 24,
        snapshot_mode="immutable_snapshot" if snapshot_start else "immutable_snapshot_unavailable",
        audited_at=audited_at,
    )
    enriched = enrich_recall_result(
        {
            "summary": base_daily,
            "items": base_items,
            "snapshot_mode": "immutable_snapshot" if snapshot_start else "immutable_snapshot_unavailable",
        },
        source_rows,
    )

    items: list[dict[str, Any]] = []
    for row in enriched["items"]:
        item = dict(row)
        measurement = measurement_by_audit_id[item["audit_id"]]
        item.update(measurement)
        item["measurement_denominator_status"] = _measurement_denominator_status(item)
        item.pop("measurement_validity", None)
        item["audit_version"] = AUDIT_VERSION
        items.append(item)

    summary = dict(enriched["summary"])
    summary.update(_measurement_summary(items, snapshot_start))
    summary["audit_version"] = AUDIT_VERSION
    summary["denominator_version"] = DENOMINATOR_VERSION
    summary["lookback_hours"] = max_observation_days * 24

    result = {
        "summary": summary,
        "items": items,
        "snapshot_mode": "immutable_snapshot" if snapshot_start else "immutable_snapshot_unavailable",
    }
    if write:
        audit_ws = _ensure_sheet(
            store,
            "final_recall_audit_v12",
            AUDIT_V12_HEADERS,
            rows=5000,
        )
        daily_ws = _ensure_sheet(
            store,
            "final_recall_daily_v12",
            DAILY_V12_HEADERS,
            rows=1000,
        )
        report_text = report_date.isoformat()
        _replace_date_rows(
            audit_ws,
            date_column=2,
            report_date=report_text,
            rows=[
                [row.get(header, "") for header in AUDIT_V12_HEADERS]
                for row in items
            ],
        )
        _upsert_daily(
            daily_ws,
            report_text,
            [summary.get(header, "") for header in DAILY_V12_HEADERS],
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
        description="Audit final recall with v1.2 item-level observation windows"
    )
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--cutoff-time", default="07:35")
    parser.add_argument("--max-observation-days", type=int, default=MAX_OBSERVATION_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    target_date = date.fromisoformat(args.report_date)
    settings = get_settings()
    store = GoogleSheetStore(settings)
    try:
        result = audit_final_recall_v12(
            store,
            report_date=target_date,
            cutoff_time=args.cutoff_time,
            max_observation_days=args.max_observation_days,
            write=not args.dry_run,
        )
    except ValueError as exc:
        if str(exc).startswith("No final_items found for report_date="):
            print(json.dumps(no_final_items_summary(target_date), ensure_ascii=False, indent=2))
            return
        raise
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
