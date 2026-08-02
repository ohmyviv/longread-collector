from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.freshness_policy_v056f import evaluate_freshness_policy
from longread_collector.models import DiscoveredURL

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=BJ)


def candidate(
    *,
    url: str,
    title: str,
    description: str = "",
    method: str,
    native: bool = True,
) -> DiscoveredURL:
    metadata = {}
    if native:
        metadata = {
            "purpose": "native_source_scan",
            "source_id": "source-a",
            "native_method": method,
        }
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        discovery_method=method,
        query_or_source="source:source-a" if native else "open",
        metadata=metadata,
    )


def test_unknown_native_firecrawl_fallback_requires_depth_signal() -> None:
    shallow = candidate(
        url="https://example.com/article/62a9e903-c859-4b82-81dd-d0ee1d4adbb0",
        title="Company chairman faces investigation",
        method="firecrawl_search",
    )
    result = evaluate_freshness_policy(shallow, now=NOW)
    assert result.allowed is False
    assert result.reject_reason == (
        "freshness_unknown_native_fallback_insufficient_evidence"
    )

    deep = candidate(
        url="https://example.com/article/62a9e903-c859-4b82-81dd-d0ee1d4adbb0",
        title="Investigation reveals a hidden industrial supply chain",
        method="firecrawl_search",
    )
    result = evaluate_freshness_policy(deep, now=NOW)
    assert result.allowed is True
    assert deep.metadata["freshness"]["unknown_date_policy"] == (
        "defer_deep_native_search_fallback"
    )


def test_section_scan_unknown_article_retains_native_route_trust() -> None:
    article = candidate(
        url="https://worksinprogress.co/issue/the-story-of-viktor-zhdanov",
        title="Read more",
        method="section_scan",
    )
    result = evaluate_freshness_policy(article, now=NOW)
    assert result.allowed is True
    assert result.track == "ordinary_unknown_native_structured"


def test_explicit_republication_year_rejects_stale_method_article() -> None:
    article = candidate(
        url="https://zh.gijn.org/stories/tips-for-investigative-reporters/",
        title="在这个真实案例中，顶尖调查团队教你怎样进行采访突破",
        description="2022年深度报道网获授权转载，这篇文章展示调查全过程。",
        method="firecrawl_search",
        native=False,
    )
    result = evaluate_freshness_policy(article, now=NOW)
    assert result.allowed is False
    assert result.reject_reason == "stale_article_over_14d"
    freshness = article.metadata["freshness"]
    assert freshness["published_at_source"] == (
        "snippet_explicit_publication_year"
    )
