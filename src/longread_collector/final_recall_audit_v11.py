"""Recall audit v1.1 with explicit registry and effective-route denominators."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

from .config import get_settings
from .final_recall_audit import (
    AUDIT_HEADERS,
    DAILY_HEADERS,
    _ensure_sheet,
    _ratio,
    _replace_date_rows,
    _source_key,
    _upsert_daily,
    audit_final_recall,
)
from .normalization import canonicalize_url, domain_from_url
from .sheets import SOURCE_HEADERS, GoogleSheetStore

AUDIT_VERSION = "final-recall-audit-v1.1-denominators"
DENOMINATOR_VERSION = "registry-route-denominators-v0.5.6e"

COVERAGE_HEADERS = [
    "editor_source_allowed",
    "registry_status",
    "effective_route_status",
    "route_scope",
    "route_lookback_hours",
    "promotion_denominator_status",
]
AUDIT_V11_HEADERS = AUDIT_HEADERS + COVERAGE_HEADERS
DAILY_EXTRA_HEADERS = [
    "registered_denominator",
    "registered_discovered",
    "registered_discovery_recall",
    "effective_route_denominator",
    "effective_route_discovered",
    "effective_route_discovery_recall",
    "registered_editable",
    "registered_editable_recall",
    "source_pool_gaps",
    "registered_route_misses",
    "effective_route_misses",
    "denominator_version",
]
DAILY_V11_HEADERS = DAILY_HEADERS + DAILY_EXTRA_HEADERS


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    editor_source_allowed: bool
    registry_status: str
    effective_route_status: str
    route_scope: str
    route_lookback_hours: int
    promotion_denominator_status: str


def _domain(value: str) -> str:
    if not value:
        return ""
    try:
        return domain_from_url(canonicalize_url(value))
    except Exception:
        return urlsplit(value).netloc.lower().removeprefix("www.")


def _methods(row: dict[str, Any]) -> set[str]:
    raw = row.get("discovery_method", "")
    if isinstance(raw, list):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    return {
        item.strip().lower()
        for item in str(raw or "").replace(",", "|").split("|")
        if item.strip()
    }


def _route_scope(row: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key in (
        "rss_url",
        "news_sitemap_url",
        "sitemap_url",
        "author_pages",
        "newsletter_url",
        "homepage_url",
    ):
        value = str(row.get(key, "") or "").strip()
        if value:
            result.append(f"{key}={value}")
    return result


def _lookback_hours(row: dict[str, Any], effective_status: str) -> int:
    try:
        config = json.loads(str(row.get("parser_config_json", "") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        config = {}
    for key in ("lookback_hours", "route_lookback_hours"):
        try:
            value = int(config.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    for key in ("lookback_days", "freshness_days"):
        try:
            value = int(config.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value * 24
    if effective_status in {"effective_native", "partial_native"}:
        return 168
    return 0


def _match_registry(
    final_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    final_source = _source_key(
        str(final_row.get("final_source") or final_row.get("canonical_source") or "")
    )
    final_url = str(
        final_row.get("final_url_canonical")
        or final_row.get("url_canonical")
        or final_row.get("final_url")
        or final_row.get("url")
        or ""
    )
    final_domain = _domain(final_url)
    for source in source_rows:
        source_name = _source_key(str(source.get("source_name", "")))
        domains = {
            _domain(str(source.get(key, "") or ""))
            for key in (
                "homepage_url",
                "rss_url",
                "sitemap_url",
                "news_sitemap_url",
                "newsletter_url",
            )
            if str(source.get(key, "") or "").strip()
        }
        if (final_source and source_name == final_source) or (
            final_domain and final_domain in domains
        ):
            return source
    return None


def classify_source_coverage(
    final_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> SourceCoverage:
    old_pool = str(final_row.get("source_pool_status", "")).strip().lower()
    outside_flag = str(final_row.get("is_outside_pool", "")).strip().upper()
    editor_allowed = old_pool != "outside_pool" and outside_flag not in {
        "TRUE",
        "1",
        "YES",
        "Y",
    }
    source = _match_registry(final_row, source_rows)
    if source is None:
        return SourceCoverage(
            editor_source_allowed=editor_allowed,
            registry_status="outside_registry",
            effective_route_status="no_route",
            route_scope="",
            route_lookback_hours=0,
            promotion_denominator_status="outside_registry",
        )

    methods = _methods(source)
    scope = _route_scope(source)
    has_feed = bool(
        str(source.get("rss_url", "")).strip()
        or str(source.get("news_sitemap_url", "")).strip()
        or str(source.get("sitemap_url", "")).strip()
    )
    directed_only = bool(methods) and methods.issubset(
        {"firecrawl_search", "directed_search", "directed_source_scan"}
    )
    partial_hint = (
        "partial" in methods
        or "section_scan" in methods
        or "directed_fallback" in methods
        or not has_feed
    )

    if directed_only:
        effective_status = "directed_fallback_only"
    elif has_feed and not partial_hint:
        effective_status = "effective_native"
    elif has_feed or "section_scan" in methods:
        effective_status = "partial_native"
    else:
        effective_status = "no_route"

    registry_status = "registered_partial" if partial_hint else "registered"
    promotion_status = (
        "effective_route_denominator"
        if effective_status in {"effective_native", "partial_native"}
        else "registered_denominator_only"
    )
    return SourceCoverage(
        editor_source_allowed=editor_allowed,
        registry_status=registry_status,
        effective_route_status=effective_status,
        route_scope="|".join(scope),
        route_lookback_hours=_lookback_hours(source, effective_status),
        promotion_denominator_status=promotion_status,
    )


def _discovered(row: dict[str, Any]) -> bool:
    return str(row.get("match_status", "")) in {
        "captured_eligible",
        "captured_but_rejected",
        "captured_extraction_failed",
    }


def _editable(row: dict[str, Any]) -> bool:
    return str(row.get("match_status", "")) == "captured_eligible"


def enrich_recall_result(
    result: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for row in result["items"]:
        enriched = dict(row)
        coverage = classify_source_coverage(enriched, source_rows)
        enriched.update(asdict(coverage))
        enriched["editor_source_allowed"] = str(coverage.editor_source_allowed).upper()
        enriched["audit_version"] = AUDIT_VERSION
        items.append(enriched)

    registered = [
        row
        for row in items
        if row["registry_status"] in {"registered", "registered_partial"}
        and str(row.get("match_status", "")) != "not_yet_available"
    ]
    effective = [
        row
        for row in items
        if row["promotion_denominator_status"] == "effective_route_denominator"
        and str(row.get("match_status", "")) != "not_yet_available"
    ]
    registered_discovered = sum(_discovered(row) for row in registered)
    effective_discovered = sum(_discovered(row) for row in effective)
    registered_editable = sum(_editable(row) for row in registered)

    summary = dict(result["summary"])
    summary.update(
        {
            "registered_denominator": len(registered),
            "registered_discovered": registered_discovered,
            "registered_discovery_recall": _ratio(
                registered_discovered, len(registered)
            ),
            "effective_route_denominator": len(effective),
            "effective_route_discovered": effective_discovered,
            "effective_route_discovery_recall": _ratio(
                effective_discovered, len(effective)
            ),
            "registered_editable": registered_editable,
            "registered_editable_recall": _ratio(
                registered_editable, len(registered)
            ),
            "source_pool_gaps": sum(
                row["registry_status"] == "outside_registry" for row in items
            ),
            "registered_route_misses": sum(
                row["registry_status"] in {"registered", "registered_partial"}
                and not _discovered(row)
                and str(row.get("match_status", "")) != "not_yet_available"
                for row in items
            ),
            "effective_route_misses": sum(
                row["promotion_denominator_status"] == "effective_route_denominator"
                and not _discovered(row)
                and str(row.get("match_status", "")) != "not_yet_available"
                for row in items
            ),
            "audit_version": AUDIT_VERSION,
            "denominator_version": DENOMINATOR_VERSION,
        }
    )
    return {**result, "items": items, "summary": summary}


def audit_final_recall_v11(
    store: GoogleSheetStore,
    *,
    report_date: date,
    cutoff_time: str = "07:35",
    lookback_hours: int = 48,
    write: bool = True,
) -> dict[str, Any]:
    base = audit_final_recall(
        store,
        report_date=report_date,
        cutoff_time=cutoff_time,
        lookback_hours=lookback_hours,
        write=False,
    )
    source_rows = store.book.worksheet("source_registry").get_all_records(
        expected_headers=SOURCE_HEADERS
    )
    result = enrich_recall_result(base, source_rows)
    if write:
        audit_ws = _ensure_sheet(
            store,
            "final_recall_audit_v11",
            AUDIT_V11_HEADERS,
            rows=5000,
        )
        daily_ws = _ensure_sheet(
            store,
            "final_recall_daily_v11",
            DAILY_V11_HEADERS,
            rows=1000,
        )
        report_text = report_date.isoformat()
        _replace_date_rows(
            audit_ws,
            date_column=2,
            report_date=report_text,
            rows=[
                [row.get(header, "") for header in AUDIT_V11_HEADERS]
                for row in result["items"]
            ],
        )
        _upsert_daily(
            daily_ws,
            report_text,
            [result["summary"].get(header, "") for header in DAILY_V11_HEADERS],
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final recall with v1.1 denominators")
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--cutoff-time", default="07:35")
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    store = GoogleSheetStore(settings)
    result = audit_final_recall_v11(
        store,
        report_date=date.fromisoformat(args.report_date),
        cutoff_time=args.cutoff_time,
        lookback_hours=args.lookback_hours,
        write=not args.dry_run,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
