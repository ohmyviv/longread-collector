from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_settings
from .sheets import GoogleSheetStore, SOURCE_HEADERS

CSV_HEADERS = [
    "source_id",
    "source_name",
    "language",
    "country_region",
    "subject_groups",
    "homepage_url",
    "rss_url",
    "sitemap_url",
    "news_sitemap_url",
    "section_urls",
    "access_type",
    "discovery_method",
    "preferred_extractor",
    "priority_tier",
    "enabled",
    "notes",
]


def load_seed(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_HEADERS:
            raise ValueError(
                f"unexpected source registry CSV headers: {reader.fieldnames!r}"
            )
        rows = [dict(row) for row in reader]
    ids = [row["source_id"].strip() for row in rows]
    if any(not source_id for source_id in ids):
        raise ValueError("source registry seed contains a blank source_id")
    if len(ids) != len(set(ids)):
        raise ValueError("source registry seed contains duplicate source_id values")
    return rows


def _parser_config(row: dict[str, str]) -> str:
    section_urls = [
        value.strip()
        for value in str(row.get("section_urls", "")).split("|")
        if value.strip()
    ]
    return json.dumps(
        {
            "section_urls": section_urls,
            "fallback_order": [
                "rss",
                "news_sitemap",
                "sitemap",
                "section_scan",
                "firecrawl_search",
            ],
            "registry_version": "source-registry-v1",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def seed_to_sheet_row(
    row: dict[str, str],
    *,
    existing: dict[str, Any] | None,
    updated_at_bj: str,
) -> list[object]:
    existing = existing or {}
    new_notes = str(row.get("notes", "")).strip()
    old_notes = str(existing.get("notes", "")).strip()
    notes = new_notes or old_notes
    values: dict[str, object] = {
        "source_id": row["source_id"].strip(),
        "source_name": row["source_name"].strip(),
        "language": row["language"].strip(),
        "country_region": row["country_region"].strip(),
        "subject_groups": row["subject_groups"].strip(),
        "homepage_url": row["homepage_url"].strip(),
        "rss_url": row["rss_url"].strip(),
        "sitemap_url": row["sitemap_url"].strip(),
        "news_sitemap_url": row["news_sitemap_url"].strip(),
        "author_pages": str(existing.get("author_pages", "")),
        "newsletter_url": str(existing.get("newsletter_url", "")),
        "access_type": row["access_type"].strip(),
        "discovery_method": row["discovery_method"].strip(),
        "preferred_extractor": row["preferred_extractor"].strip(),
        "parser_config_json": _parser_config(row),
        "priority_tier": row["priority_tier"].strip(),
        "enabled": row["enabled"].strip().upper(),
        "last_scanned_at_bj": existing.get("last_scanned_at_bj", ""),
        "parser_success_rate_30d": existing.get("parser_success_rate_30d", ""),
        "discovered_30d": existing.get("discovered_30d", 0),
        "extracted_30d": existing.get("extracted_30d", 0),
        "selected_30d": existing.get("selected_30d", 0),
        "notes": notes,
        "updated_at_bj": updated_at_bj,
    }
    return [values.get(header, "") for header in SOURCE_HEADERS]


def backup_registry(store: GoogleSheetStore, values: list[list[str]]) -> str:
    timestamp = store._now().strftime("%Y%m%d-%H%M%S")
    title = f"source_registry_backup_{timestamp}"
    worksheet = store.book.add_worksheet(
        title=title,
        rows=max(100, len(values) + 10),
        cols=len(SOURCE_HEADERS),
    )
    if values:
        worksheet.update(
            range_name=f"A1:X{len(values)}",
            values=values,
            value_input_option="USER_ENTERED",
        )
    return title


def sync_seed(store: GoogleSheetStore, seed_rows: list[dict[str, str]]) -> dict[str, Any]:
    worksheet = store.book.worksheet("source_registry")
    current_values = worksheet.get_all_values()
    current_records = worksheet.get_all_records(expected_headers=SOURCE_HEADERS)
    current_by_id = {
        str(row.get("source_id", "")).strip(): row
        for row in current_records
        if str(row.get("source_id", "")).strip()
    }
    backup_title = backup_registry(store, current_values)
    now = store._now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [SOURCE_HEADERS]
    seeded_ids: set[str] = set()
    for seed in seed_rows:
        source_id = seed["source_id"].strip()
        seeded_ids.add(source_id)
        rows.append(
            seed_to_sheet_row(
                seed,
                existing=current_by_id.get(source_id),
                updated_at_bj=now,
            )
        )
    for source_id, existing in current_by_id.items():
        if source_id not in seeded_ids:
            rows.append([existing.get(header, "") for header in SOURCE_HEADERS])
    worksheet.clear()
    worksheet.update(
        range_name=f"A1:X{len(rows)}",
        values=rows,
        value_input_option="USER_ENTERED",
    )
    return {
        "backup_sheet": backup_title,
        "seeded_sources": len(seed_rows),
        "preserved_unlisted_sources": len(rows) - 1 - len(seed_rows),
        "zh_sources": sum(row["language"] == "zh" for row in seed_rows),
        "en_sources": sum(row["language"] == "en" for row in seed_rows),
        "enabled_sources": sum(
            row["enabled"].strip().upper() == "TRUE" for row in seed_rows
        ),
        "updated_at_bj": now,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync source registry v1 to Google Sheets")
    parser.add_argument(
        "--seed",
        type=Path,
        default=Path("config/source_registry_v1.csv"),
    )
    args = parser.parse_args()
    seed_rows = load_seed(args.seed)
    store = GoogleSheetStore(get_settings())
    result = sync_seed(store, seed_rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
