from longread_collector.models import DiscoveredURL
from longread_collector.ranked_selection import filter_discovered


def native(url: str, title: str, *, rank: int, published_at: str = "") -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        rank=rank,
        published_at=published_at,
        discovery_method="section_scan",
        query_or_source="source:jiemian-depth",
        metadata={
            "purpose": "native_source_scan",
            "source_id": "jiemian-depth",
            "source_name": "界面新闻·界面深度",
        },
    )


def test_listing_pages_do_not_consume_native_source_slots() -> None:
    items = [
        native(
            "https://www.jiemian.com/pro/lists/13.html",
            "盘前机会前瞻",
            rank=1,
        ),
        native(
            "https://www.jiemian.com/video/lists/258_1.html",
            "界面Vnews",
            rank=2,
        ),
        native(
            "https://www.jiemian.com/article/14825227.html",
            "【深度】中国新能源告别规模崇拜",
            rank=3,
        ),
        native(
            "https://www.jiemian.com/article/14755424.html",
            "【深度】海上风电何以深陷低价漩涡",
            rank=4,
        ),
        native(
            "https://www.jiemian.com/article/14718476.html",
            "【深度】中国开启可回收火箭时代",
            rank=5,
        ),
        native(
            "https://www.jiemian.com/article/14568288.html",
            "【深度】屋顶光伏度苦夏",
            rank=6,
        ),
    ]

    accepted, rejected = filter_discovered(items, max_urls=32)

    assert [item.url for item in accepted] == [
        "https://www.jiemian.com/article/14825227.html",
        "https://www.jiemian.com/article/14755424.html",
        "https://www.jiemian.com/article/14718476.html",
        "https://www.jiemian.com/article/14568288.html",
    ]
    assert [item["reason"] for item in rejected].count("listing_page") == 2


def test_native_source_cap_is_four_after_ranking() -> None:
    items = [
        native(
            f"https://example.com/article/{number}.html",
            f"深度调查文章 {number}",
            rank=number,
            published_at=f"2026-07-{20 + number:02d}",
        )
        for number in range(1, 7)
    ]

    accepted, rejected = filter_discovered(items, max_urls=32)

    assert len(accepted) == 4
    assert [item.published_at for item in accepted] == [
        "2026-07-26",
        "2026-07-25",
        "2026-07-24",
        "2026-07-23",
    ]
    assert [item["reason"] for item in rejected].count("per_source_cap") == 2


def test_open_search_keeps_two_per_host() -> None:
    items = [
        DiscoveredURL(
            url=f"https://open.example.com/news/{number}.html",
            title=f"Analysis {number}",
            rank=number,
            discovery_method="firecrawl_search",
            query_or_source="zh_business_fresh",
        )
        for number in range(1, 5)
    ]

    accepted, rejected = filter_discovered(items, max_urls=32)

    assert len(accepted) == 2
    assert [item["reason"] for item in rejected].count("per_domain_cap") == 2


def test_round_robin_preserves_source_diversity_before_second_slots() -> None:
    items = []
    for source_id, host in (("a", "a.example.com"), ("b", "b.example.com")):
        for rank in range(1, 4):
            items.append(
                DiscoveredURL(
                    url=f"https://{host}/article/{rank}.html",
                    title=f"深度文章 {source_id}-{rank}",
                    rank=rank,
                    discovery_method="section_scan",
                    query_or_source=f"source:{source_id}",
                    metadata={"purpose": "native_source_scan", "source_id": source_id},
                )
            )

    accepted, _ = filter_discovered(items, max_urls=2)

    assert {item.metadata["source_id"] for item in accepted} == {"a", "b"}
