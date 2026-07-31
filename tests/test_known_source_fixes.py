import asyncio
from datetime import datetime

import httpx

from longread_collector.known_source_fixes import (
    KnownFallbackAwareDiscovery,
    apply_known_source_fix,
    parse_reader_section,
)


def source(source_id: str, **overrides):
    base = {
        "source_id": source_id,
        "source_name": source_id,
        "language": "en",
        "homepage_url": "https://example.com/",
        "priority_tier": "rotate",
        "enabled": "TRUE",
        "discovery_method": ["section_scan", "firecrawl_search"],
        "parser_config_json": {
            "section_urls": ["https://example.com/news"],
            "fallback_order": [
                "rss",
                "news_sitemap",
                "sitemap",
                "section_scan",
                "firecrawl_search",
            ],
        },
    }
    base.update(overrides)
    return base


def test_validated_runtime_endpoint_fixes() -> None:
    jiemian = apply_known_source_fix(source("jiemian-depth"))
    assert jiemian["parser_config_json"]["section_urls"] == [
        "https://www.jiemian.com/lists/423.html"
    ]

    knowable = apply_known_source_fix(source("knowable"))
    assert knowable["rss_url"] == "https://www.knowablemagazine.org/rss"

    deeptech = apply_known_source_fix(source("deeptech"))
    assert deeptech["homepage_url"] == "https://www.mittrchina.com/"
    assert deeptech["parser_config_json"]["section_urls"] == [
        "https://www.mittrchina.com/news"
    ]

    icn = apply_known_source_fix(source("inside-climate-news"))
    assert icn["discovery_method"] == ["firecrawl_search"]
    assert icn["parser_config_json"]["fallback_order"] == ["firecrawl_search"]


def test_parse_reader_section_keeps_mittrchina_articles() -> None:
    body = """
    Title: MITTR China
    Markdown Content:
    ## [三星芯片工程师正成批跳槽去SK海力士](https://www.mittrchina.com/news/detail/16699)
    [栏目首页](https://www.mittrchina.com/news)
    [External report](https://example.com/news/detail/1)
    ## [第二篇足够长的科技报道](https://www.mittrchina.com/news/detail/16700)
    """
    items = parse_reader_section(
        body,
        source=apply_known_source_fix(source("deeptech")),
        endpoint="https://r.jina.ai/http://www.mittrchina.com/news",
        limit=6,
    )
    assert [item.url for item in items] == [
        "https://www.mittrchina.com/news/detail/16699",
        "https://www.mittrchina.com/news/detail/16700",
    ]
    assert all(item.discovery_method == "reader_section" for item in items)


def test_inside_climate_news_skips_known_blocked_native_requests() -> None:
    class NeverCalledClient:
        async def get(self, *args, **kwargs):
            raise AssertionError("direct native request should have been skipped")

    discovery = KnownFallbackAwareDiscovery(timeout=1, concurrency=1)
    items, log = asyncio.run(
        discovery.discover_source(
            NeverCalledClient(),
            source("inside-climate-news"),
            limit=6,
            started=datetime(2026, 7, 31, 8, 0, 0),
            freshness_days=3,
        )
    )
    assert items == []
    assert log.fallback_needed is True
    assert log.error_type == "NativeAccessBlocked"


def test_deeptech_uses_reader_after_js_shell_returns_no_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.mittrchina.com":
            return httpx.Response(
                200,
                text="<html><body><div id='root'></div></body></html>",
                headers={"content-type": "text/html"},
            )
        if request.url.host == "r.jina.ai":
            return httpx.Response(
                200,
                text=(
                    "## [一篇足够长的科技深度报道]"
                    "(https://www.mittrchina.com/news/detail/16701)"
                ),
                headers={"content-type": "text/plain"},
            )
        raise AssertionError(f"unexpected endpoint: {request.url}")

    async def run():
        discovery = KnownFallbackAwareDiscovery(timeout=2, concurrency=1)
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await discovery.discover_source(
                client,
                source("deeptech", language="zh"),
                limit=6,
                started=datetime(2026, 7, 31, 8, 0, 0),
                freshness_days=3,
            )

    items, log = asyncio.run(run())
    assert len(items) == 1
    assert items[0].url == "https://www.mittrchina.com/news/detail/16701"
    assert log.success is True
    assert log.selected_method == "reader_section"
