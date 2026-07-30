from pathlib import Path

from longread_collector.source_registry_seed import (
    load_seed,
    seed_to_sheet_row,
)
from longread_collector.source_validation import (
    candidate_endpoints,
    detect_document_kind,
    planned_method,
    validate_source_rows,
)
from longread_collector.sheets import SOURCE_HEADERS


def test_source_registry_v1_counts_and_unique_ids() -> None:
    rows = load_seed(Path("config/source_registry_v1.csv"))
    assert len(rows) == 72
    assert sum(row["language"] == "zh" for row in rows) == 42
    assert sum(row["language"] == "en" for row in rows) == 30
    assert sum(row["enabled"] == "TRUE" for row in rows) == 63
    assert len({row["source_id"] for row in rows}) == len(rows)
    assert all(
        row["enabled"] == "FALSE"
        for row in rows
        if row["priority_tier"] == "monitor"
    )


def test_seed_row_preserves_operational_metrics() -> None:
    seed = load_seed(Path("config/source_registry_v1.csv"))[0]
    row = seed_to_sheet_row(
        seed,
        existing={
            "last_scanned_at_bj": "2026-07-30 10:00:00",
            "parser_success_rate_30d": "0.75",
            "discovered_30d": 8,
            "extracted_30d": 6,
            "selected_30d": 2,
            "notes": "old note",
        },
        updated_at_bj="2026-07-30 23:18:00",
    )
    mapped = dict(zip(SOURCE_HEADERS, row))
    assert mapped["last_scanned_at_bj"] == "2026-07-30 10:00:00"
    assert mapped["discovered_30d"] == 8
    assert mapped["selected_30d"] == 2
    assert mapped["parser_config_json"].startswith("{")


def test_source_rows_are_structurally_valid() -> None:
    seed_rows = load_seed(Path("config/source_registry_v1.csv"))
    sources = []
    for row in seed_rows:
        sources.append(
            {
                **row,
                "enabled": row["enabled"] == "TRUE",
                "discovery_method": row["discovery_method"].split("|"),
            }
        )
    assert validate_source_rows(sources) == []


def test_detect_feed_sitemap_and_html() -> None:
    assert detect_document_kind(
        "<rss><channel><item/><item/></channel></rss>",
        "application/rss+xml",
    ) == ("feed", 2)
    assert detect_document_kind(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>a</loc></url></urlset>',
        "application/xml",
    ) == ("sitemap", 1)
    assert detect_document_kind(
        '<html><a href="/2026/07/story-one">one</a><a href="/about">about</a></html>',
        "text/html",
    ) == ("html", 1)


def test_method_and_endpoint_priority() -> None:
    source = {
        "rss_url": "https://example.com/feed",
        "sitemap_url": "https://example.com/sitemap.xml",
        "homepage_url": "https://example.com/",
        "parser_config_json": '{"section_urls":["https://example.com/features"]}',
        "discovery_method": ["rss", "firecrawl_search"],
    }
    assert planned_method(source) == "rss"
    assert candidate_endpoints(source) == [
        "https://example.com/feed",
        "https://example.com/sitemap.xml",
        "https://example.com/features",
        "https://example.com/",
    ]
