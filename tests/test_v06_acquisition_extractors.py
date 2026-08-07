import asyncio

from longread_collector.v06.acquisition.extractors import (
    DirectHtmlExtractor,
    FirecrawlExtractor,
    JinaExtractor,
)
from longread_collector.v06.contracts import DiscoveryRecord


def _record() -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="test",
        run_id="run",
        item_id="item",
        discovery_id="discovery",
        url="https://example.com/a",
        title_hint="Fallback title",
        published_at_hints=("2026-08-07",),
    )


class FakeJinaClient:
    async def read(self, url):
        return {
            "markdown": "# Jina title\n\n正文" * 100,
            "title": "Jina title",
            "author": "Reporter",
            "published_at": "2026-08-07",
        }, {"latency_ms": 12, "http_status": 200}


class FakeFirecrawlClient:
    async def scrape(self, url):
        return {
            "markdown": {"content": "# FC title\n\n正文" * 100},
            "metadata": {
                "title": "FC title",
                "author": "Author",
                "publishedDate": "2026-08-07",
                "canonicalUrl": "https://origin.example/article",
            },
        }, {"latency_ms": 21, "http_status": 200, "credits_used": 1}


def test_jina_adapter_normalizes_client_payload() -> None:
    payload = asyncio.run(JinaExtractor(FakeJinaClient()).extract(_record()))
    assert payload.extractor == "jina"
    assert payload.title == "Jina title"
    assert payload.author == "Reporter"
    assert payload.http_status == 200
    assert payload.latency_ms == 12


def test_direct_html_adapter_accepts_injected_reader_without_network() -> None:
    async def reader(url):
        return {
            "markdown": "# Direct title\n\n正文" * 100,
            "title": "Direct title",
            "published_at": "2026-08-07",
            "metadata": {
                "outbound_links": ["https://origin.example/article"],
                "video_count": 2,
            },
        }, {"latency_ms": 18, "http_status": 200}

    payload = asyncio.run(DirectHtmlExtractor(reader).extract(_record()))
    assert payload.title == "Direct title"
    assert payload.outbound_links == ("https://origin.example/article",)
    assert payload.metadata["video_count"] == 2


def test_firecrawl_adapter_normalizes_nested_markdown_and_cost() -> None:
    payload = asyncio.run(FirecrawlExtractor(FakeFirecrawlClient()).extract(_record()))
    assert payload.extractor == "firecrawl"
    assert payload.title == "FC title"
    assert payload.canonical_links == ("https://origin.example/article",)
    assert payload.credits_used == 1.0
    assert payload.http_status == 200
