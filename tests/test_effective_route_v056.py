import asyncio
from datetime import datetime, timedelta

import httpx

from longread_collector.effective_route_v056 import (
    EFFECTIVE_ROUTE_VERSION,
    EffectiveRouteDiscovery,
    JIEMIAN_SECTION_URLS,
    MIN_METADATA_ITEMS_PER_SOURCE,
    MIN_NATIVE_LOOKBACK_DAYS,
    PROPUBLICA_SECTION_URLS,
    QUANTA_SECTION_URLS,
    THEPAPER_SECTION_URLS,
    apply_effective_route_fix,
    begin_effective_route_audit,
    current_effective_route_audit,
    end_effective_route_audit,
    parse_section_html_v056,
    parse_sitemap_v056,
)


def source(source_id: str, **overrides):
    base = {
        "source_id": source_id,
        "source_name": source_id,
        "language": "en",
        "homepage_url": "https://example.com/",
        "rss_url": "",
        "priority_tier": "rotate",
        "enabled": "TRUE",
        "subject_groups": "public_policy|science",
        "discovery_method": ["rss", "section_scan", "firecrawl_search"],
        "parser_config_json": {
            "section_urls": [],
            "fallback_order": ["rss", "section_scan", "firecrawl_search"],
        },
    }
    base.update(overrides)
    return base


def test_effective_route_contract_expands_known_sources() -> None:
    jiemian = apply_effective_route_fix(source("jiemian-depth", language="zh"))
    assert jiemian["parser_config_json"]["section_urls"] == JIEMIAN_SECTION_URLS

    thepaper = apply_effective_route_fix(source("thepaper", language="zh"))
    assert thepaper["parser_config_json"]["section_urls"] == THEPAPER_SECTION_URLS

    propublica = apply_effective_route_fix(
        source(
            "propublica",
            homepage_url="https://www.propublica.org/",
            rss_url="https://www.propublica.org/feeds/propublica/main",
        )
    )
    assert propublica["parser_config_json"]["section_urls"] == PROPUBLICA_SECTION_URLS

    quanta = apply_effective_route_fix(
        source(
            "quanta",
            homepage_url="https://www.quantamagazine.org/",
            rss_url="https://www.quantamagazine.org/feed/",
        )
    )
    assert quanta["parser_config_json"]["section_urls"] == QUANTA_SECTION_URLS

    for fixed in (jiemian, thepaper, propublica, quanta):
        config = fixed["parser_config_json"]
        assert config["metadata_limit"] >= MIN_METADATA_ITEMS_PER_SOURCE
        assert config["lookback_days"] >= MIN_NATIVE_LOOKBACK_DAYS


def test_section_parser_accepts_thepaper_and_quanta_article_shapes() -> None:
    paper_body = """
    <a href="https://m.thepaper.cn/newsDetail_forward_33664738">
      多地推进处改科遏制头衔通货膨胀
    </a>
    <a href="/channel_25951">财经频道</a>
    """
    paper_items = parse_section_html_v056(
        paper_body,
        source=source(
            "thepaper",
            language="zh",
            homepage_url="https://www.thepaper.cn/",
        ),
        endpoint="https://www.thepaper.cn/channel_25951",
        limit=24,
    )
    assert [item.url for item in paper_items] == [
        "https://m.thepaper.cn/newsDetail_forward_33664738"
    ]

    quanta_body = """
    <a href="/a-new-way-that-a-cows-inner-world-shapes-earths-atmosphere-20260727/">
      A New Way That a Cow's Inner World Shapes Earth's Atmosphere
    </a>
    """
    quanta_items = parse_section_html_v056(
        quanta_body,
        source=source(
            "quanta",
            homepage_url="https://www.quantamagazine.org/",
        ),
        endpoint="https://www.quantamagazine.org/archive/",
        limit=24,
    )
    assert len(quanta_items) == 1


def test_sitemap_index_exposes_ten_children() -> None:
    xml = "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + "".join(
        f"<sitemap><loc>https://example.com/sitemap-{index}.xml</loc></sitemap>"
        for index in range(12)
    ) + "</sitemapindex>"
    items, children = parse_sitemap_v056(
        xml,
        source=source("example"),
        endpoint="https://example.com/sitemap.xml",
        limit=24,
        started=datetime(2026, 8, 2, 8, 0, 0),
        freshness_days=7,
        method="sitemap",
    )
    assert items == []
    assert len(children) == 10


def _rss(entries: list[tuple[str, str, datetime]]) -> str:
    rows = []
    for title, url, published in entries:
        rows.append(
            "<item>"
            f"<title>{title}</title><link>{url}</link>"
            f"<pubDate>{published.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
            "</item>"
        )
    return "<rss><channel>" + "".join(rows) + "</channel></rss>"


def test_shallow_rss_is_aggregated_with_archive_and_audited() -> None:
    started = datetime(2026, 8, 2, 8, 0, 0)
    feed_entries = [
        (
            f"Recent investigation {index}",
            f"https://www.propublica.org/article/recent-{index}",
            started - timedelta(days=index),
        )
        for index in range(1, 6)
    ]
    target = "https://www.propublica.org/article/federal-science-grants-russell-vought-omb"
    archive = """
    <html><body>
      <a href="/article/federal-science-grants-russell-vought-omb">
        How federal science grants could be politicized
      </a>
      <a href="/article/archive-second-investigation">A second archive investigation</a>
      <a href="/article/archive-third-investigation">A third archive investigation</a>
    </body></html>
    """

    class FixtureDiscovery(EffectiveRouteDiscovery):
        async def _get(self, client, url):
            if url.endswith("/feeds/propublica/main"):
                return httpx.Response(200, text=_rss(feed_entries))
            if url.endswith("/archive/"):
                return httpx.Response(200, text=archive)
            raise AssertionError(f"unexpected URL: {url}")

    async def run():
        token = begin_effective_route_audit()
        try:
            batch = await FixtureDiscovery(timeout=1, concurrency=1).discover(
                [
                    source(
                        "propublica",
                        homepage_url="https://www.propublica.org/",
                        rss_url="https://www.propublica.org/feeds/propublica/main",
                    )
                ],
                limit_per_source=6,
                started=started,
                freshness_days=3,
            )
            return batch, current_effective_route_audit()
        finally:
            end_effective_route_audit(token)

    batch, audit = asyncio.run(run())

    assert target in {item.url for item in batch.items}
    assert len(batch.items) == 8
    log = batch.logs[0]
    assert log["route_type"] == "rss+section_scan"
    assert log["metadata_limit"] == MIN_METADATA_ITEMS_PER_SOURCE
    assert log["configured_lookback_days"] == MIN_NATIVE_LOOKBACK_DAYS
    assert log["fallback_used"] is False
    assert log["effective_route_version"] == EFFECTIVE_ROUTE_VERSION
    assert audit is not None
    assert audit["items_discovered"] == 8
    assert audit["effective_native_successes"] == 1


def test_multiple_sections_are_aggregated_before_return() -> None:
    started = datetime(2026, 8, 2, 8, 0, 0)

    class FixtureDiscovery(EffectiveRouteDiscovery):
        async def _get(self, client, url):
            index = JIEMIAN_SECTION_URLS.index(url)
            return httpx.Response(
                200,
                text=(
                    f'<a href="/article/14841{index:03d}.html">'
                    f'界面新闻栏目深度文章编号{index}</a>'
                ),
            )

    fixed = source(
        "jiemian-depth",
        language="zh",
        homepage_url="https://www.jiemian.com/",
        discovery_method=["section_scan", "firecrawl_search"],
    )
    items, log = asyncio.run(
        FixtureDiscovery(timeout=1, concurrency=1).discover_source(
            None,
            fixed,
            limit=6,
            started=started,
            freshness_days=3,
        )
    )
    assert len(items) == len(JIEMIAN_SECTION_URLS)
    assert len(log.selected_endpoint.split("|")) == len(JIEMIAN_SECTION_URLS)
    assert all(item.metadata["native_route_status"] == "effective_native" for item in items)
