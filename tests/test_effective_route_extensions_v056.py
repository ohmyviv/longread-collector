from longread_collector.effective_route_extensions_v056 import (
    BJNEWS_EFFECTIVE_ROUTES,
    JIEMIAN_EFFECTIVE_ROUTES,
    THEPAPER_EFFECTIVE_ROUTES,
    apply_effective_route_fix,
    merge_route_items,
)
from longread_collector.models import SearchResult


def source(source_id: str):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "language": "zh",
        "homepage_url": "https://example.com/",
        "priority_tier": "rotate",
        "enabled": "TRUE",
        "subject_groups": "business|public_policy",
        "discovery_method": ["section_scan", "firecrawl_search"],
        "parser_config_json": {
            "section_urls": [],
            "fallback_order": ["section_scan", "firecrawl_search"],
        },
    }


def result(source_id: str, suffix: str, rank: int) -> SearchResult:
    return SearchResult(
        query_id=f"source:{source_id}",
        group="native_source",
        purpose="native_source_scan",
        url=f"https://example.com/article/{suffix}",
        title=f"Article {suffix}",
        description="",
        published_at="",
        language="zh",
        rank=rank,
        metadata={"source_id": source_id},
    )


def test_source_specific_route_contracts_are_bounded_and_ordered() -> None:
    jiemian = apply_effective_route_fix(source("jiemian-depth"))
    assert jiemian["parser_config_json"]["section_urls"] == JIEMIAN_EFFECTIVE_ROUTES
    assert jiemian["parser_config_json"]["metadata_limit"] == 96
    assert "lists/506.html" in JIEMIAN_EFFECTIVE_ROUTES[0]
    assert all("_2.html" not in url for url in JIEMIAN_EFFECTIVE_ROUTES)

    bjnews = apply_effective_route_fix(source("bjnews-depth"))
    assert bjnews["parser_config_json"]["section_urls"] == BJNEWS_EFFECTIVE_ROUTES
    assert bjnews["parser_config_json"]["metadata_limit"] == 64
    assert BJNEWS_EFFECTIVE_ROUTES[0].endswith("/depth")

    thepaper = apply_effective_route_fix(source("thepaper"))
    assert thepaper["parser_config_json"]["section_urls"] == THEPAPER_EFFECTIVE_ROUTES
    assert thepaper["parser_config_json"]["metadata_limit"] == 320
    assert any("nodeids=25462&pageidx=8" in url for url in THEPAPER_EFFECTIVE_ROUTES)
    assert any("nodeids=25448&pageidx=8" in url for url in THEPAPER_EFFECTIVE_ROUTES)


def test_high_volume_sources_use_declared_priority_not_round_robin() -> None:
    groups = [
        [result("bjnews-depth", f"depth-{index}", index + 1) for index in range(20)],
        [result("bjnews-depth", f"news-{index}", index + 1) for index in range(20)],
    ]
    merged = merge_route_items(groups, limit=24)
    assert [item.url.rsplit("/", 1)[-1] for item in merged[:20]] == [
        f"depth-{index}" for index in range(20)
    ]
    assert [item.url.rsplit("/", 1)[-1] for item in merged[20:]] == [
        f"news-{index}" for index in range(4)
    ]
