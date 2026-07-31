from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .config import get_settings
from .normalization import canonicalize_url, domain_from_url
from .recall_instrumentation import SNAPSHOT_HEADERS, normalize_title
from .sheets import ARTICLE_HEADERS, RUN_HEADERS, SOURCE_HEADERS, GoogleSheetStore

AUDIT_VERSION = "final-recall-audit-v1.0"
EXPECTED_GROUPS = {"zh_midday", "zh_evening", "intl_early", "pre_report"}

AUDIT_HEADERS = [
    "audit_id", "report_date", "final_run_id", "item_index", "section", "language",
    "final_title", "final_title_norm", "final_url", "final_url_canonical",
    "final_source", "published_date", "cutoff_at_bj", "lookback_started_at_bj",
    "source_pool_status", "match_status", "match_type", "matched_snapshot_id",
    "matched_article_id", "matched_url", "matched_title", "matched_source",
    "matched_first_seen_at_bj", "matched_run_id", "matched_discovery_method",
    "prefilter_status", "prefilter_reject_reason", "extraction_status",
    "eligible_for_editor", "candidate_disposition", "reject_reason",
    "content_cluster_id", "manual_review_required", "notes", "audited_at_bj",
    "audit_version",
]

DAILY_HEADERS = [
    "report_date", "final_run_id", "final_items", "eligible_denominator",
    "discovered_matches", "editable_matches", "exact_url_matches",
    "normalized_title_matches", "same_story_matches", "not_discovered",
    "captured_but_rejected", "captured_extraction_failed", "not_yet_available",
    "manual_source_only", "discovery_recall", "editable_recall",
    "exact_or_title_recall", "zh_final", "zh_discovered", "en_final",
    "en_discovered", "in_pool_final", "in_pool_discovered", "outside_pool_final",
    "outside_pool_discovered", "collector_runs_in_window", "collector_groups",
    "expected_groups_covered", "audit_status", "manual_review_items",
    "cutoff_at_bj", "lookback_hours", "audited_at_bj", "audit_version",
]


def _truthy(value: Any) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _sheet_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        if number > 1000:
            return (datetime(1899, 12, 30) + timedelta(days=number)).date()
    except ValueError:
        pass
    for candidate in (text, text.replace("/", "-")):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def _sheet_datetime(value: Any, tz: ZoneInfo) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)):
        result = datetime(1899, 12, 30) + timedelta(days=float(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
            if number <= 1000:
                return None
            result = datetime(1899, 12, 30) + timedelta(days=number)
        except ValueError:
            try:
                result = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = _sheet_date(text)
                return datetime.combine(parsed, time.min, tzinfo=tz) if parsed else None
    if result.tzinfo is None:
        result = result.replace(tzinfo=tz)
    return result.astimezone(tz)


def _parse_cutoff(report_date: date, cutoff_time: str, tz: ZoneInfo) -> datetime:
    hour_text, minute_text = cutoff_time.split(":", 1)
    return datetime.combine(
        report_date,
        time(hour=int(hour_text), minute=int(minute_text)),
        tzinfo=tz,
    )


def _source_key(value: str) -> str:
    return normalize_title(value)


def _final_title_norms(row: dict[str, Any]) -> set[str]:
    values = {
        str(row.get("title", "")),
        str(row.get("title_zh", "")),
        str(row.get("title_norm", "")),
    }
    return {normalize_title(value) for value in values if normalize_title(value)}


def _snapshot_title_norms(row: dict[str, Any]) -> set[str]:
    values = {str(row.get("title", "")), str(row.get("title_norm", ""))}
    return {normalize_title(value) for value in values if normalize_title(value)}


def _row_domain(row: dict[str, Any]) -> str:
    url = str(row.get("url_canonical") or row.get("url") or "")
    return domain_from_url(canonicalize_url(url)) if url else ""


def _source_pool_status(
    final_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> str:
    outside_value = str(final_row.get("is_outside_pool", "")).strip()
    if outside_value:
        return "outside_pool" if _truthy(outside_value) else "in_pool"

    final_source = _source_key(str(final_row.get("canonical_source", "")))
    final_domain = _row_domain(final_row)
    for source in source_rows:
        if final_source and final_source == _source_key(str(source.get("source_name", ""))):
            return "in_pool"
        for key in ("homepage_url", "rss_url", "sitemap_url", "news_sitemap_url"):
            candidate = str(source.get(key, "")).strip()
            if candidate and final_domain == domain_from_url(canonicalize_url(candidate)):
                return "in_pool"
    return "unknown"


def _outcome_rank(row: dict[str, Any]) -> int:
    prefilter = str(row.get("prefilter_status", ""))
    extraction = str(row.get("extraction_status", "")).lower()
    eligible = _truthy(row.get("eligible_for_editor"))
    disposition = str(row.get("candidate_disposition", ""))
    if prefilter in {"prefilter_rejected", "not_selected_capacity"}:
        return 2
    if extraction and extraction != "success":
        return 3
    if eligible or disposition in {"formal_candidate", "special_candidate"}:
        return 5
    if extraction == "success" or str(row.get("article_id", "")):
        return 4
    return 1


def _earliest_timestamp(row: dict[str, Any], tz: ZoneInfo) -> datetime:
    return (
        _sheet_datetime(row.get("captured_at_bj"), tz)
        or _sheet_datetime(row.get("first_seen_at_bj"), tz)
        or datetime.max.replace(tzinfo=tz)
    )


def _choose_best(rows: Iterable[dict[str, Any]], tz: ZoneInfo) -> dict[str, Any] | None:
    candidates = list(rows)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (-_outcome_rank(row), _earliest_timestamp(row, tz)),
    )[0]


def _title_similarity(final_norms: set[str], snapshot_norms: set[str]) -> float:
    best = 0.0
    for final_norm in final_norms:
        for snapshot_norm in snapshot_norms:
            if final_norm and snapshot_norm:
                best = max(
                    best,
                    SequenceMatcher(None, final_norm, snapshot_norm).ratio(),
                )
    return best


def select_best_match(
    final_row: dict[str, Any],
    snapshots: list[dict[str, Any]],
    tz: ZoneInfo,
) -> tuple[dict[str, Any] | None, str, bool]:
    """Return matched row, match type, and manual-review flag."""
    final_raw_url = str(final_row.get("url_canonical") or final_row.get("url") or "")
    final_url = canonicalize_url(final_raw_url) if final_raw_url else ""
    exact_url = [
        row
        for row in snapshots
        if final_url
        and canonicalize_url(str(row.get("url_canonical") or row.get("url") or ""))
        == final_url
    ]
    match = _choose_best(exact_url, tz)
    if match:
        return match, "exact_url", False

    final_norms = _final_title_norms(final_row)
    exact_title = [
        row for row in snapshots if final_norms.intersection(_snapshot_title_norms(row))
    ]
    match = _choose_best(exact_title, tz)
    if match:
        return match, "normalized_title", False

    final_domain = _row_domain(final_row)
    final_source = _source_key(str(final_row.get("canonical_source", "")))
    fuzzy: list[tuple[float, dict[str, Any]]] = []
    for row in snapshots:
        ratio = _title_similarity(final_norms, _snapshot_title_norms(row))
        if ratio < 0.90:
            continue
        row_domain = _row_domain(row)
        row_source = _source_key(str(row.get("canonical_source", "")))
        source_aligned = bool(
            (final_domain and final_domain == row_domain)
            or (final_source and final_source == row_source)
        )
        if source_aligned or ratio >= 0.96:
            fuzzy.append((ratio, row))
    if fuzzy:
        best_ratio = max(value for value, _ in fuzzy)
        match = _choose_best(
            [row for value, row in fuzzy if value == best_ratio], tz
        )
        return match, "same_story", True
    return None, "none", False


def classify_match(
    matched: dict[str, Any] | None,
    *,
    source_pool_status: str,
    published_at: datetime | None,
    cutoff: datetime,
) -> tuple[str, str]:
    if matched is None:
        if published_at and published_at > cutoff:
            return "not_yet_available", "availability"
        if source_pool_status == "outside_pool":
            return "manual_source_only", "manual_outside_pool"
        return "not_discovered", "discovery"

    prefilter = str(matched.get("prefilter_status", ""))
    if prefilter in {"prefilter_rejected", "not_selected_capacity"}:
        return "captured_but_rejected", "prefilter"

    extraction = str(matched.get("extraction_status", "")).lower()
    if extraction and extraction != "success":
        return "captured_extraction_failed", "extraction"

    eligible = _truthy(matched.get("eligible_for_editor"))
    disposition = str(matched.get("candidate_disposition", ""))
    if eligible or disposition in {"formal_candidate", "special_candidate"}:
        return "captured_eligible", "eligible"
    return "captured_but_rejected", "classification"


def _latest_final_run(
    rows: list[dict[str, Any]], report_date: date
) -> tuple[str, list[dict[str, Any]]]:
    selected = [
        (index, row)
        for index, row in enumerate(rows)
        if _sheet_date(row.get("report_date")) == report_date
    ]
    if not selected:
        raise ValueError(
            f"No final_items found for report_date={report_date.isoformat()}"
        )
    last_position_by_run: dict[str, int] = {}
    for index, row in selected:
        run_id = str(row.get("run_id", "")).strip()
        last_position_by_run[run_id] = index
    final_run_id = max(last_position_by_run, key=last_position_by_run.get)
    final_rows = [
        row
        for _, row in selected
        if str(row.get("run_id", "")).strip() == final_run_id
    ]
    final_rows.sort(key=lambda row: int(row.get("item_index") or 0))
    return final_run_id, final_rows


def _load_snapshots(
    store: GoogleSheetStore,
    *,
    window_start: datetime,
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], str]:
    try:
        rows = store.book.worksheet("collector_discovery_snapshot").get_all_records(
            expected_headers=SNAPSHOT_HEADERS
        )
    except Exception:
        rows = []
    filtered = [
        row
        for row in rows
        if (
            (captured := _sheet_datetime(row.get("captured_at_bj"), store.tz))
            and window_start <= captured <= cutoff
        )
    ]
    if filtered:
        return filtered, "immutable_snapshot"

    cache_rows = store.book.worksheet("article_cache").get_all_records(
        expected_headers=ARTICLE_HEADERS
    )
    fallback: list[dict[str, Any]] = []
    for row in cache_rows:
        first_seen = (
            _sheet_datetime(row.get("first_seen_at_bj"), store.tz)
            or _sheet_datetime(row.get("discovered_at_bj"), store.tz)
        )
        if not first_seen or not (window_start <= first_seen <= cutoff):
            continue
        fallback.append({
            "snapshot_id": f"cache:{row.get('article_id', '')}",
            "collector_run_id": row.get("discovery_run_id", ""),
            "captured_at_bj": first_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "query_group": "",
            "source_id": "",
            "discovery_method": row.get("discovery_method", ""),
            "query_or_source": row.get("query_or_source", ""),
            "url": row.get("url", ""),
            "url_canonical": row.get("url_canonical", ""),
            "domain": row.get("domain", ""),
            "title": row.get("title", ""),
            "title_norm": normalize_title(str(row.get("title", ""))),
            "description": row.get("description", ""),
            "published_at": row.get("published_at", ""),
            "language": row.get("language", ""),
            "discovered_rank": row.get("discovered_rank", ""),
            "prefilter_status": "accepted_for_extraction",
            "prefilter_reject_reason": "",
            "article_id": row.get("article_id", ""),
            "extraction_status": row.get("extraction_status", ""),
            "extractor_used": row.get("extractor_used", ""),
            "eligible_for_editor": row.get("eligible_for_editor", ""),
            "candidate_disposition": row.get("candidate_disposition", ""),
            "reject_reason": row.get("reject_reason", ""),
            "canonical_source": row.get("canonical_source", ""),
            "content_cluster_id": row.get("content_cluster_id", ""),
            "source_relationship": row.get("source_relationship", ""),
            "original_url": row.get("original_url", ""),
            "metadata_json": row.get("metadata_json", ""),
        })
    return fallback, "article_cache_fallback"


def _ensure_sheet(
    store: GoogleSheetStore,
    title: str,
    headers: list[str],
    *,
    rows: int,
) -> Any:
    try:
        ws = store.book.worksheet(title)
    except Exception:
        ws = store.book.add_worksheet(title=title, rows=rows, cols=len(headers))
        ws.append_row(headers, value_input_option="RAW")
        ws.freeze(rows=1)
    if ws.row_values(1) != headers:
        raise ValueError(f"{title} header mismatch")
    return ws


def _replace_date_rows(
    ws: Any,
    *,
    date_column: int,
    report_date: str,
    rows: list[list[object]],
) -> None:
    values = ws.col_values(date_column)
    matching_rows = [
        row_no
        for row_no, value in enumerate(values[1:], start=2)
        if str(value).strip() == report_date
    ]
    for row_no in reversed(matching_rows):
        ws.delete_rows(row_no)
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")


def _upsert_daily(ws: Any, report_date: str, row: list[object]) -> None:
    for row_no, value in enumerate(ws.col_values(1)[1:], start=2):
        if str(value).strip() == report_date:
            ws.update(
                range_name=f"A{row_no}:AH{row_no}",
                values=[row],
                value_input_option="USER_ENTERED",
            )
            return
    ws.append_row(row, value_input_option="USER_ENTERED")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def build_daily_summary(
    audit_rows: list[dict[str, Any]],
    *,
    report_date: str,
    final_run_id: str,
    collector_runs: list[dict[str, Any]],
    cutoff: datetime,
    lookback_hours: int,
    snapshot_mode: str,
    audited_at: str,
) -> dict[str, Any]:
    statuses = Counter(str(row["match_status"]) for row in audit_rows)
    match_types = Counter(str(row["match_type"]) for row in audit_rows)
    eligible_denominator = len(audit_rows) - statuses["not_yet_available"]
    discovered_statuses = {
        "captured_eligible", "captured_but_rejected", "captured_extraction_failed"
    }
    discovered = sum(statuses[status] for status in discovered_statuses)
    editable = statuses["captured_eligible"]

    def segment(field: str, value: str) -> tuple[int, int]:
        rows = [row for row in audit_rows if str(row.get(field, "")) == value]
        hits = sum(str(row["match_status"]) in discovered_statuses for row in rows)
        return len(rows), hits

    zh_final, zh_discovered = segment("language", "zh")
    en_final, en_discovered = segment("language", "en")
    in_pool_final, in_pool_discovered = segment("source_pool_status", "in_pool")
    outside_final, outside_discovered = segment("source_pool_status", "outside_pool")
    groups = sorted({
        str(row.get("query_group", "")).strip()
        for row in collector_runs
        if str(row.get("query_group", "")).strip()
    })
    expected_covered = EXPECTED_GROUPS.issubset(set(groups))
    manual_review_items = sum(
        _truthy(row.get("manual_review_required")) for row in audit_rows
    )
    if snapshot_mode == "article_cache_fallback":
        audit_status = "legacy_cache_fallback"
    elif expected_covered:
        audit_status = "complete"
    else:
        audit_status = "partial_runs"
    if manual_review_items:
        audit_status += "_with_manual_review"

    return {
        "report_date": report_date,
        "final_run_id": final_run_id,
        "final_items": len(audit_rows),
        "eligible_denominator": eligible_denominator,
        "discovered_matches": discovered,
        "editable_matches": editable,
        "exact_url_matches": match_types["exact_url"],
        "normalized_title_matches": match_types["normalized_title"],
        "same_story_matches": match_types["same_story"],
        "not_discovered": statuses["not_discovered"],
        "captured_but_rejected": statuses["captured_but_rejected"],
        "captured_extraction_failed": statuses["captured_extraction_failed"],
        "not_yet_available": statuses["not_yet_available"],
        "manual_source_only": statuses["manual_source_only"],
        "discovery_recall": _ratio(discovered, eligible_denominator),
        "editable_recall": _ratio(editable, eligible_denominator),
        "exact_or_title_recall": _ratio(
            match_types["exact_url"] + match_types["normalized_title"],
            eligible_denominator,
        ),
        "zh_final": zh_final,
        "zh_discovered": zh_discovered,
        "en_final": en_final,
        "en_discovered": en_discovered,
        "in_pool_final": in_pool_final,
        "in_pool_discovered": in_pool_discovered,
        "outside_pool_final": outside_final,
        "outside_pool_discovered": outside_discovered,
        "collector_runs_in_window": len(collector_runs),
        "collector_groups": "|".join(groups),
        "expected_groups_covered": str(expected_covered).upper(),
        "audit_status": audit_status,
        "manual_review_items": manual_review_items,
        "cutoff_at_bj": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": lookback_hours,
        "audited_at_bj": audited_at,
        "audit_version": AUDIT_VERSION,
    }


def audit_final_recall(
    store: GoogleSheetStore,
    *,
    report_date: date,
    cutoff_time: str = "07:35",
    lookback_hours: int = 48,
    write: bool = True,
) -> dict[str, Any]:
    cutoff = _parse_cutoff(report_date, cutoff_time, store.tz)
    window_start = cutoff - timedelta(hours=lookback_hours)
    audited_at = datetime.now(store.tz).strftime("%Y-%m-%d %H:%M:%S")

    final_run_id, final_rows = _latest_final_run(
        store.book.worksheet("final_items").get_all_records(), report_date
    )
    snapshots, snapshot_mode = _load_snapshots(
        store, window_start=window_start, cutoff=cutoff
    )
    source_rows = store.book.worksheet("source_registry").get_all_records(
        expected_headers=SOURCE_HEADERS
    )
    run_rows = store.book.worksheet("collector_runs").get_all_records(
        expected_headers=RUN_HEADERS
    )
    collector_runs = [
        row
        for row in run_rows
        if (
            str(row.get("final_status", "")).lower() == "success"
            and (started := _sheet_datetime(row.get("started_at_bj"), store.tz))
            and window_start <= started <= cutoff
        )
    ]

    audit_records: list[dict[str, Any]] = []
    for final_row in final_rows:
        final_raw_url = str(
            final_row.get("url_canonical") or final_row.get("url") or ""
        )
        canonical = canonicalize_url(final_raw_url) if final_raw_url else ""
        source_pool_status = _source_pool_status(final_row, source_rows)
        published_at = _sheet_datetime(final_row.get("published_date"), store.tz)
        matched, match_type, manual_review = select_best_match(
            final_row, snapshots, store.tz
        )
        match_status, miss_stage = classify_match(
            matched,
            source_pool_status=source_pool_status,
            published_at=published_at,
            cutoff=cutoff,
        )
        item_index = int(final_row.get("item_index") or 0)
        audit_id = hashlib.sha256(
            f"{report_date.isoformat()}|{final_run_id}|{item_index}|{canonical}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        audit_records.append({
            "audit_id": audit_id,
            "report_date": report_date.isoformat(),
            "final_run_id": final_run_id,
            "item_index": item_index,
            "section": str(final_row.get("section", "")),
            "language": str(final_row.get("language", "")),
            "final_title": str(final_row.get("title", "")),
            "final_title_norm": next(iter(_final_title_norms(final_row)), ""),
            "final_url": str(final_row.get("url", "")),
            "final_url_canonical": canonical,
            "final_source": str(final_row.get("canonical_source", "")),
            "published_date": str(final_row.get("published_date", "")),
            "cutoff_at_bj": cutoff.strftime("%Y-%m-%d %H:%M:%S"),
            "lookback_started_at_bj": window_start.strftime("%Y-%m-%d %H:%M:%S"),
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
            "notes": f"miss_stage={miss_stage}; snapshot_mode={snapshot_mode}",
            "audited_at_bj": audited_at,
            "audit_version": AUDIT_VERSION,
        })

    daily = build_daily_summary(
        audit_records,
        report_date=report_date.isoformat(),
        final_run_id=final_run_id,
        collector_runs=collector_runs,
        cutoff=cutoff,
        lookback_hours=lookback_hours,
        snapshot_mode=snapshot_mode,
        audited_at=audited_at,
    )

    if write:
        audit_ws = _ensure_sheet(
            store, "final_recall_audit", AUDIT_HEADERS, rows=5000
        )
        daily_ws = _ensure_sheet(
            store, "final_recall_daily", DAILY_HEADERS, rows=1000
        )
        _replace_date_rows(
            audit_ws,
            date_column=2,
            report_date=report_date.isoformat(),
            rows=[
                [record.get(header, "") for header in AUDIT_HEADERS]
                for record in audit_records
            ],
        )
        _upsert_daily(
            daily_ws,
            report_date.isoformat(),
            [daily.get(header, "") for header in DAILY_HEADERS],
        )

    return {"summary": daily, "items": audit_records, "snapshot_mode": snapshot_mode}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final longread recall")
    parser.add_argument("--report-date", default="")
    parser.add_argument("--cutoff-time", default="07:35")
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    settings = get_settings()
    store = GoogleSheetStore(settings)
    target_date = (
        date.fromisoformat(args.report_date)
        if args.report_date
        else datetime.now(store.tz).date()
    )
    result = audit_final_recall(
        store,
        report_date=target_date,
        cutoff_time=args.cutoff_time,
        lookback_hours=args.lookback_hours,
        write=not args.dry_run,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
