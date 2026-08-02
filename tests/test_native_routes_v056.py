from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from longread_collector.native_routes_v056 import (
    EffectiveNativeRouteDiscovery,
    apply_v056_source_route,
    current_native_route_audit,
    parse_effective_section_html,
)


def source(source_id: str = "example", **overrides):
    base = {
        "source_id": source_id,
        "source_name": source_id,
        "language": "en",
        "homepage_url": "https://example.com/",
        "priority_tier": "rotate",
        "enabled": "TRUE",
        "discovery_method": ["section_scan", "firecrawl_search"],
        "parser_config_json": {
            "section_urls": ["https://example.com/section-a"],
            "fallback_order": ["section_scan", "firecrawl_search"],
        },
    }
    base.update(overrides)
    return base


def test_known_route_contracts_expand_registered_scope() -> None:
    jiemian = apply_v056_source_route(
        source(
            "jiemian-depth",
            homepage_url="https://www.jiemian.com/",
            parser_config_json={
                "section_urls": ["https://www.jiemian.com/lists/423.html"],
                "fallback_order": ["section_scan", "firecrawl_search"],
            },
        )
    )
    routes = jiemian["parser_config_json"]["section_urls"]
    assert "https://www.jiemian.com/lists/9.html" in routes
    assert "https://www.jiemian.com/lists/112.html" in routes
    assert "https://www.jiemian.com/lists/174.html" in routes

    propublica = apply_v056_source_route(
        source(
            "propublica",
            homepage_url="https://www.propublica.org/",
            rss_url="https://www.propublica.org/feeds/propublica/main",
            discovery_method=["rss", "firecrawl_search"],
            parser_config_json={
                "section_urls": [],
                "fallback_order": ["rss", "section_scan", "firecrawl_search"],
            },
        )
    )
    assert "section_scan" in propublica["discovery_method"]
    assert "https://www.propublica.org/archive/page/2" in propublica[
        "parser_config_json"
    ]["section_urls"]
    assert propublica["parser_config_json"]["target_lookback_days"] == 7
    assert propublica["parser_config_json"]["metadata_limit_per_source"] == 30


def test_route_specific_parser_keeps_stage4_target_shapes() -> None:
    fixtures = [
        (
            source("propublica", homepage_url="https://www.propublica.org/"),
            "https://www.propublica.org/archive/",
            "https://www.propublica.org/article/federal-science-grants-russell-vought-omb",
        ),
        (
            source("quanta", homepage_url="https://www.quantamagazine.org/"),
            "https://www.quantamagazine.org/archive/",
            "https://www.quantamagazine.org/a-new-way-that-a-cows-inner-world-shapes-earths-atmosphere-20260727/",
        ),
        (
            source("jiemian-depth", homepage_url="https://www.jiemian.com/"),
            "https://www.jiemian.com/lists/174.html",
            "https://www.jiemian.com/article/14841105.html",
        ),
        (
            source("bjnews-depth", homepage_url="https://www.bjnews.com.cn/"),
            "https://m.bjnews.com.cn/depth",
            "https://m.bjnews.com.cn/detail/1785144458129453.html",
        ),
        (
            source("thepaper", homepage_url="https://www.thepaper.cn/"),
            "https://www.thepaper.cn/list_25448",
            "https://www.thepaper.cn/newsDetail_forward_33660139",
        ),
    ]
    for item, endpoint, target in fixtures:
        body = f'<html><body><a href="{target}">A sufficiently descriptive article title</a></body></html>'
        parsed = parse_effective_section_html(
            body,
            source=item,
            endpoint=endpoint,
            limit=30,
        )
        assert [row.url for row in parsed] == [target]


def test_effective_discovery_forces_seven_day_feed_window() -> None:
    rss = """
    <rss><channel>
      <item>
        <title>Six day investigative feature</title>
        <link>https://example.com/news/six-day-feature</link>
        <pubDate>Sun, 26 Jul 2026 08:00:00 GMT</pubDate>
      </item>
      <item>
        <title>Eight day old feature</title>
        <link>https://example.com/news/eight-day-feature</link>
        <pubDate>Fri, 24 Jul 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/feed"
        return httpx.Response(200, text=rss, headers={"content-type": "application/rss+xml"})

    async def run():
        discovery = EffectiveNativeRouteDiscovery(timeout=2, concurrency=1)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await discovery.discover_source(
                client,
                source(
                    rss_url="https://example.com/feed",
                    discovery_method=["rss", "firecrawl_search"],
                    parser_config_json={
                        "section_urls": [],
                        "fallback_order": ["rss", "firecrawl_search"],
                    },
                ),
                limit=6,
                started=datetime(2026, 8, 2, 7, 0, 0),
                freshness_days=3,
            )

    items, log = asyncio.run(run())
    assert [item.title for item in items] == ["Six day investigative feature"]
    summary = log.attempts[-1]
    assert summary["method"] == "route_summary"
    assert summary["native_route_status"] == "effective_native"
    assert summary["effective_lookback_hours"] >= 160


def test_discovery_aggregates_sections_and_exposes_audit() -> None:
    pages = {
        "https://example.com/section-a": """
            <a href='/news/a-one'>First section article one</a>
            <a href='/news/a-two'>First section article two</a>
        """,
        "https://example.com/section-b": """
            <a href='/reports/b-one'>Second section article one</a>
            <a href='/reports/b-two'>Second section article two</a>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages[str(request.url)], headers={"content-type": "text/html"})

    async def run():
        discovery = EffectiveNativeRouteDiscovery(timeout=2, concurrency=1)
        transport = httpx.MockTransport(handler)
        original_get = discovery._get

        async def mocked_get(client, url):
            response = await client.get(url)
            response.raise_for_status()
            return response

        discovery._get = mocked_get
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                items, log = await discovery.discover_source(
                    client,
                    source(
                        parser_config_json={
                            "section_urls": [
                                "https://example.com/section-a",
                                "https://example.com/section-b",
                            ],
                            "fallback_order": ["section_scan", "firecrawl_search"],
                        }
                    ),
                    limit=2,
                    started=datetime(2026, 8, 2, 7, 0, 0),
                    freshness_days=3,
                )
                return items, log
        finally:
            discovery._get = original_get

    items, log = asyncio.run(run())
    assert len(items) == 4
    assert {item.metadata["native_route"]["route_version"] for item in items} == {
        "effective-native-routes-v0.5.6"
    }
    summary = log.attempts[-1]
    assert summary["items_seen"] == 4
    assert summary["sections_covered"] == [
        "https://example.com/section-a",
        "https://example.com/section-b",
    ]


def test_batch_discovery_publishes_source_level_audit() -> None:
    page = '<a href="/news/a-long-report">A long report for route auditing</a>'

    class TestDiscovery(EffectiveNativeRouteDiscovery):
        async def _get(self, client, url):
            return httpx.Response(
                200,
                text=page,
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", url),
            )

    discovery = TestDiscovery(timeout=2, concurrency=1)
    batch = asyncio.run(
        discovery.discover(
            [source()],
            limit_per_source=6,
            started=datetime(2026, 8, 2, 7, 0, 0),
            freshness_days=3,
        )
    )
    assert len(batch.items) == 1
    audit = current_native_route_audit()
    assert len(audit) == 1
    assert audit[0]["source_id"] == "example"
    assert audit[0]["items_seen"] == 1
    assert audit[0]["native_route_status"] == "partial_native"
