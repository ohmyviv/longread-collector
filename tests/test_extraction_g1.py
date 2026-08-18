from __future__ import annotations

import asyncio
from types import SimpleNamespace

from longread_collector.extraction import FallbackBudget
from longread_collector.extraction_v056m import EXTRACTION_VERSION, extract_article_v056m
from longread_collector.models import DiscoveredURL


def _body(seed: str, paragraphs: int = 24) -> str:
    return "\n\n".join(
        (
            f"{seed} paragraph {index}. Reporters interviewed researchers and industry "
            "participants, reviewed the historical context and implementation constraints, "
            "and compared multiple explanations before reaching a conclusion."
        )
        for index in range(paragraphs)
    )


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        min_body_chars=1200,
        editor_min_body_chars=2500,
        content_cell_limit=50000,
    )


def test_g1_direct_html_success_skips_jina_and_firecrawl(monkeypatch) -> None:
    title = "Direct HTML should be the normal acquisition path"
    body = f"# {title}\n\n" + _body("direct", 30)

    async def fake_direct(url: str):
        return (
            {
                "markdown": body,
                "title": title,
                "published_at": "2026-08-18T12:00:00+08:00",
                "author": "Reporter",
                "description": "",
                "metadata": {"direct_html_method": "embedded_json"},
            },
            {"http_status": 200, "latency_ms": 8, "request_sent": True},
        )

    monkeypatch.setattr(
        "longread_collector.extraction_v056m.read_direct_html_v056m",
        fake_direct,
    )

    class ForbiddenJina:
        api_key = None

        async def read(self, url: str):
            raise AssertionError("Jina must not run when direct HTML is sufficient")

    class ForbiddenFirecrawl:
        async def scrape(self, url: str):
            raise AssertionError("Firecrawl must not run when direct HTML is sufficient")

    budget = FallbackBudget(remaining=1)
    article = asyncio.run(
        extract_article_v056m(
            DiscoveredURL(url="https://example.com/direct", title=title),
            ForbiddenJina(),
            ForbiddenFirecrawl(),
            _settings(),
            budget,
        )
    )

    assert EXTRACTION_VERSION == "extraction-v0.5.6m-g1"
    assert article.extractor_used == "direct_html"
    assert [attempt["extractor"] for attempt in article.extraction_attempts] == [
        "direct_html"
    ]
    assert article.metadata["jina_fallback_requested"] is False
    assert article.metadata["jina_fallback_attempted"] is False
    assert article.metadata["jina_auth_mode"] == "anonymous"
    assert budget.remaining == 1


def test_g1_jina_only_rescues_insufficient_direct_html(monkeypatch) -> None:
    title = "Jina is a rescue layer rather than the primary extractor"
    direct_body = "short direct response"
    jina_body = f"# {title}\n\n" + _body("jina", 30)

    async def fake_direct(url: str):
        return (
            {
                "markdown": direct_body,
                "title": title,
                "published_at": "2026-08-18T12:00:00+08:00",
                "author": "",
                "description": "",
                "metadata": {"direct_html_method": "semantic_html"},
            },
            {"http_status": 200, "latency_ms": 7, "request_sent": True},
        )

    monkeypatch.setattr(
        "longread_collector.extraction_v056m.read_direct_html_v056m",
        fake_direct,
    )

    class RescueJina:
        api_key = None

        async def read(self, url: str):
            return (
                {
                    "markdown": jina_body,
                    "title": title,
                    "published_at": "2026-08-18T12:00:00+08:00",
                    "author": "Reporter",
                },
                {"http_status": 200, "latency_ms": 11},
            )

    class ForbiddenFirecrawl:
        async def scrape(self, url: str):
            raise AssertionError("Firecrawl must not run after a successful Jina rescue")

    budget = FallbackBudget(remaining=1)
    article = asyncio.run(
        extract_article_v056m(
            DiscoveredURL(url="https://example.com/jina-rescue", title=title),
            RescueJina(),
            ForbiddenFirecrawl(),
            _settings(),
            budget,
        )
    )

    assert article.extractor_used == "jina"
    assert [attempt["extractor"] for attempt in article.extraction_attempts] == [
        "direct_html",
        "jina",
    ]
    assert article.metadata["jina_fallback_requested"] is True
    assert article.metadata["jina_fallback_attempted"] is True
    assert article.metadata["fallback_requested"] is False
    assert budget.remaining == 1


def test_g1_firecrawl_remains_budgeted_final_rescue(monkeypatch) -> None:
    title = "Firecrawl remains the final bounded rescue layer"
    firecrawl_body = f"# {title}\n\n" + _body("firecrawl", 30)

    async def fake_direct(url: str):
        return (
            {
                "markdown": "short direct response",
                "title": title,
                "published_at": "2026-08-18T12:00:00+08:00",
                "author": "",
                "description": "",
                "metadata": {"direct_html_method": "semantic_html"},
            },
            {"http_status": 200, "latency_ms": 7, "request_sent": True},
        )

    monkeypatch.setattr(
        "longread_collector.extraction_v056m.read_direct_html_v056m",
        fake_direct,
    )

    class EmptyJina:
        api_key = None

        async def read(self, url: str):
            return (
                {"markdown": "", "title": title, "published_at": "2026-08-18"},
                {"http_status": 200, "latency_ms": 9},
            )

    class RescueFirecrawl:
        async def scrape(self, url: str):
            return (
                {
                    "markdown": firecrawl_body,
                    "metadata": {
                        "title": title,
                        "author": "Reporter",
                        "publishedTime": "2026-08-18T12:00:00+08:00",
                    },
                },
                {"http_status": 200, "latency_ms": 18, "credits_used": 1},
            )

    budget = FallbackBudget(remaining=1)
    article = asyncio.run(
        extract_article_v056m(
            DiscoveredURL(url="https://example.com/firecrawl-rescue", title=title),
            EmptyJina(),
            RescueFirecrawl(),
            _settings(),
            budget,
        )
    )

    assert article.extractor_used == "firecrawl"
    assert [attempt["extractor"] for attempt in article.extraction_attempts] == [
        "direct_html",
        "jina",
        "firecrawl",
    ]
    assert article.metadata["jina_fallback_requested"] is True
    assert article.metadata["fallback_requested"] is True
    assert article.metadata["fallback_allowed"] is True
    assert budget.remaining == 0
