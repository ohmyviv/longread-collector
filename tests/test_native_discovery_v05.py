from datetime import datetime

from longread_collector.native_discovery import (
    parse_feed,
    parse_section_html,
    parse_sitemap,
    select_sources_for_run,
)


def source(**overrides):
    base = {
        "source_id": "example",
        "source_name": "Example",
        "language": "en",
        "homepage_url": "https://example.com/",
        "priority_tier": "rotate",
        "enabled": "TRUE",
    }
    base.update(overrides)
    return base


def test_parse_rss_and_atom_entries() -> None:
    started = datetime(2026, 7, 31, 7, 0, 0)
    rss = """
    <rss><channel>
      <item>
        <title>Fresh investigation</title>
        <link>https://example.com/2026/07/fresh-investigation</link>
        <description>A detailed report.</description>
        <pubDate>Thu, 30 Jul 2026 10:00:00 GMT</pubDate>
      </item>
      <item>
        <title>Old story</title>
        <link>https://example.com/2026/06/old-story</link>
        <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    items = parse_feed(
        rss,
        source=source(),
        endpoint="https://example.com/feed",
        limit=10,
        started=started,
        freshness_days=3,
    )
    assert [item.title for item in items] == ["Fresh investigation"]
    assert items[0].discovery_method == "rss"
    assert items[0].metadata["source_id"] == "example"

    atom = """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Atom feature</title>
        <link rel="alternate" href="https://example.com/features/atom-feature"/>
        <updated>2026-07-31T00:30:00Z</updated>
        <summary>Long-form feature.</summary>
      </entry>
    </feed>
    """
    atom_items = parse_feed(
        atom,
        source=source(),
        endpoint="https://example.com/atom.xml",
        limit=10,
        started=started,
        freshness_days=3,
    )
    assert len(atom_items) == 1
    assert atom_items[0].title == "Atom feature"


def test_parse_sitemap_and_sitemap_index() -> None:
    started = datetime(2026, 7, 31, 7, 0, 0)
    sitemap = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url>
        <loc>https://example.com/2026/07/report-one</loc>
        <lastmod>2026-07-30</lastmod>
        <news:news><news:title>Report One</news:title></news:news>
      </url>
      <url>
        <loc>https://example.com/2026/05/old-report</loc>
        <lastmod>2026-05-01</lastmod>
      </url>
    </urlset>
    """
    items, children = parse_sitemap(
        sitemap,
        source=source(),
        endpoint="https://example.com/sitemap.xml",
        limit=10,
        started=started,
        freshness_days=3,
        method="sitemap",
    )
    assert children == []
    assert len(items) == 1
    assert items[0].title == "Report One"

    sitemap_index = """
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/sitemap-news.xml</loc></sitemap>
      <sitemap><loc>https://example.com/sitemap-features.xml</loc></sitemap>
    </sitemapindex>
    """
    indexed_items, child_urls = parse_sitemap(
        sitemap_index,
        source=source(),
        endpoint="https://example.com/sitemap.xml",
        limit=10,
        started=started,
        freshness_days=3,
        method="sitemap",
    )
    assert indexed_items == []
    assert child_urls == [
        "https://example.com/sitemap-news.xml",
        "https://example.com/sitemap-features.xml",
    ]


def test_parse_section_page_keeps_same_domain_article_links() -> None:
    body = """
    <html><body>
      <a href="/2026/07/deep-report">Deep report on a changing industry</a>
      <a href="https://other.example/story">External story</a>
      <a href="/about">About us</a>
      <a href="/category/science">Science category</a>
    </body></html>
    """
    items = parse_section_html(
        body,
        source=source(),
        endpoint="https://example.com/features",
        limit=10,
    )
    assert len(items) == 1
    assert items[0].url == "https://example.com/2026/07/deep-report"
    assert items[0].title == "Deep report on a changing industry"


def test_scheduler_prefers_unscanned_and_avoids_same_day_repeats() -> None:
    started = datetime(2026, 7, 31, 12, 0, 0)
    sources = [
        source(source_id="rotate-never", last_scanned_at_bj=""),
        source(source_id="rotate-old", last_scanned_at_bj="2026-07-25 10:00:00"),
        source(source_id="rotate-today", last_scanned_at_bj="2026-07-31 05:20:00"),
        source(
            source_id="explore-never",
            priority_tier="explore",
            last_scanned_at_bj="",
        ),
        source(
            source_id="explore-old",
            priority_tier="explore",
            last_scanned_at_bj="2026-07-20 10:00:00",
        ),
    ]
    selected = select_sources_for_run(sources, started=started, max_sources=4)
    ids = [item["source_id"] for item in selected]
    assert "rotate-today" not in ids
    assert "rotate-never" in ids
    assert "explore-never" in ids or "explore-old" in ids
    assert len(ids) == 4


def test_scheduler_never_selects_monitor_sources() -> None:
    started = datetime(2026, 7, 31, 12, 0, 0)
    sources = [
        source(source_id="core"),
        source(source_id="monitor", priority_tier="monitor", enabled="FALSE"),
    ]
    selected = select_sources_for_run(sources, started=started, max_sources=5)
    assert [item["source_id"] for item in selected] == ["core"]
