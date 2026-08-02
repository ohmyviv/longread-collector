from types import SimpleNamespace

from longread_collector.effective_route_extensions_v056 import (
    BJNEWS_EFFECTIVE_ROUTES,
    BJNEWS_NEWS_PAGES,
    JIEMIAN_EFFECTIVE_ROUTES,
    THEPAPER_EFFECTIVE_ROUTES,
    _bjnews_published_at,
    apply_effective_route_fix,
    merge_route_items,
)


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


def result(source_id: str, suffix: str, rank: int):
    return SimpleNamespace(
        url=f"https://example.com/article/{suffix}",
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
    assert len(BJNEWS_NEWS_PAGES) == 64
    assert BJNEWS_NEWS_PAGES[-1].endswith("/64.html")

    thepaper = apply_effective_route_fix(source("thepaper"))
    assert thepaper["parser_config_json"]["section_urls"] == THEPAPER_EFFECTIVE_ROUTES
    assert thepaper["parser_config_json"]["metadata_limit"] == 48
    assert THEPAPER_EFFECTIVE_ROUTES == [
        "https://www.thepaper.cn/list_25462",
        "https://www.thepaper.cn/list_25448",
    ]


def test_bjnews_article_id_restores_approximate_creation_time() -> None:
    observed = _bjnews_published_at(
        "https://www.bjnews.com.cn/detail/1785144458129453.html"
    )
    assert observed is not None
    # The ID timestamp predates the page's displayed publication time, so it is
    # a medium-confidence creation/freshness signal rather than exact publish time.
    assert observed.strftime("%Y-%m-%d %H:%M") == "2026-07-27 17:27"


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
