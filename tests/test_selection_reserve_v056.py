from longread_collector.models import DiscoveredURL
from longread_collector.pipeline_v056b import filter_discovered as snapshot_filter
from longread_collector.prefilter_v056 import filter_discovered
from longread_collector.ranked_selection_v056 import OPEN_DIVERSITY_FLOOR
from longread_collector.recall_instrumentation import (
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
)


def native(source_id: str, article_index: int, *, day: int = 1) -> DiscoveredURL:
    return DiscoveredURL(
        url=(
            f"https://{source_id}.example.com/2026/08/0{day}/"
            f"investigation-{article_index}.html"
        ),
        title=f"Investigation feature {source_id} {article_index}",
        description="A detailed reported article with evidence and analysis.",
        published_at=f"2026-08-0{day}",
        rank=article_index,
        discovery_method="rss",
        query_or_source=f"source:{source_id}",
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_id,
        },
    )


def open_item(domain_index: int, article_index: int, *, day: int = 1) -> DiscoveredURL:
    return DiscoveredURL(
        url=(
            f"https://open{domain_index}.example.org/2026/08/0{day}/"
            f"analysis-{article_index}.html"
        ),
        title=f"Open analysis {domain_index} {article_index}",
        description="An independent analysis article with sufficient metadata.",
        published_at=f"2026-08-0{day}",
        rank=article_index,
        discovery_method="firecrawl_search",
        query_or_source="en_investigation_fresh",
    )


def test_native_third_and_fourth_rounds_precede_open_overflow() -> None:
    discovered = [
        native(source_id, article_index)
        for source_id in ("native0", "native1", "native2", "native3")
        for article_index in range(1, 6)
    ]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(12)
        for article_index in range(1, 3)
    )

    accepted, rejected = filter_discovered(
        discovered,
        max_urls=32,
        max_per_domain=2,
    )
    accepted_native = [
        item
        for item in accepted
        if item.metadata["selection"]["selection_bucket"] == "native"
    ]
    accepted_open = [
        item
        for item in accepted
        if item.metadata["selection"]["selection_bucket"] == "open"
    ]

    assert len(accepted) == 32
    assert len(accepted_native) == 16
    assert len(accepted_open) == 16
    assert rejected == []
    assert sorted(
        item.metadata["selection"]["selected_order"] for item in accepted
    ) == list(range(1, 33))
    assert sum(
        item.metadata["selection"].get("selection_phase")
        == "global_quality_fill"
        for item in accepted_native
    ) == 8
    assert sum(
        bool(item.metadata["selection"].get("capacity_backfill"))
        for item in accepted_native
    ) == 8

    fifth_items = [
        item
        for item in discovered
        if item.metadata.get("purpose") == "native_source_scan"
        and item.rank == 5
    ]
    assert len(fifth_items) == 4
    assert all(
        item.metadata["selection"]["selection_status"]
        == "source_initial_cap_reserve"
        for item in fifth_items
    )
    assert all(
        "capacity_bucket_reject_reason" not in item.metadata["selection"]
        for item in fifth_items
    )


def test_open_overflow_only_fills_capacity_after_native_is_exhausted() -> None:
    discovered = [
        native(source_id, article_index)
        for source_id in ("native0", "native1", "native2")
        for article_index in range(1, 5)
    ]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(12)
        for article_index in range(1, 3)
    )

    accepted, _ = filter_discovered(discovered, max_urls=32, max_per_domain=2)
    accepted_native = [
        item
        for item in accepted
        if item.metadata["selection"]["selection_bucket"] == "native"
    ]
    accepted_open = [
        item
        for item in accepted
        if item.metadata["selection"]["selection_bucket"] == "open"
    ]
    assert len(accepted_native) == 12
    assert len(accepted_open) == 20
    assert len(accepted) == 32


def test_native_soft_target_is_met_when_sixteen_eligible_items_exist() -> None:
    discovered = [
        native(str(source_id), article_index)
        for source_id in range(8)
        for article_index in range(1, 3)
    ]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(20)
        for article_index in range(1, 3)
    )
    accepted, _ = filter_discovered(discovered, max_urls=32, max_per_domain=2)
    assert sum(
        item.metadata["selection"]["selection_bucket"] == "native"
        for item in accepted
    ) == 16
    assert sum(
        item.metadata["selection"]["selection_bucket"] == "open"
        for item in accepted
    ) == 16


def test_quality_fill_can_exceed_sixteen_native_after_open_floor() -> None:
    discovered = [
        native(str(source_id), article_index)
        for source_id in range(8)
        for article_index in range(1, 5)
    ]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(16)
        for article_index in range(1, 3)
    )
    accepted, _ = filter_discovered(discovered, max_urls=32, max_per_domain=2)
    native_count = sum(
        item.metadata["selection"]["selection_bucket"] == "native"
        for item in accepted
    )
    open_count = len(accepted) - native_count
    assert native_count == 32 - OPEN_DIVERSITY_FLOOR
    assert open_count == OPEN_DIVERSITY_FLOOR
    assert all(
        item.metadata["selection"]["selection_status"] == "selected"
        for item in accepted
    )


def test_investigations_outrank_generic_items_within_source_cap() -> None:
    titles = [
        "Daily company appointment update",
        "Short transport price update",
        "起底防晒衣：实测四件全部翻车",
        "暗访酸臭原料灰色产业链",
        "观势：消费动能怎么上坡",
        "核电审批节奏背后的产业变化",
    ]
    discovered = [native("curated", index) for index in range(1, 7)]
    for item, title in zip(discovered, titles, strict=True):
        item.url = f"https://curated.example.com/2026/08/01/article-{item.rank}.html"
        item.title = title
        item.description = ""
    accepted, _ = filter_discovered(discovered, max_urls=4, max_per_domain=2)
    accepted_titles = {item.title for item in accepted}
    assert accepted_titles == set(titles[2:])
    assert all(
        item.metadata["selection"]["score_components"]["editorial_priority"]
        > 0
        for item in accepted
    )


def test_capacity_reserve_is_not_snapshot_page_rejection() -> None:
    discovered = [native("bjnews", index) for index in range(1, 7)]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(20)
        for article_index in range(1, 3)
    )

    token = begin_snapshot_capture("zh_evening")
    try:
        accepted, rejected = snapshot_filter(
            discovered,
            max_urls=32,
            max_per_domain=2,
        )
        state = current_snapshot_capture()
        assert state is not None
        captured = {row.item.url: row for row in state.discoveries}
    finally:
        end_snapshot_capture(token)

    assert len(accepted) == 32
    assert rejected == []
    fifth = discovered[4]
    sixth = discovered[5]
    assert captured[fifth.url].prefilter_status == "not_selected_capacity"
    assert captured[fifth.url].prefilter_reject_reason == "source_initial_cap_reserve"
    assert captured[sixth.url].prefilter_status == "not_selected_capacity"
    assert captured[sixth.url].prefilter_reject_reason == "source_initial_cap_reserve"


def test_hard_page_gate_remains_prefilter_rejection() -> None:
    homepage = DiscoveredURL(
        url="https://example.com/",
        title="Example homepage",
        description="",
    )
    article = native("native0", 1)
    accepted, rejected = filter_discovered(
        [homepage, article], max_urls=32, max_per_domain=2
    )
    assert accepted == [article]
    assert rejected == [{"url": homepage.url, "reason": "homepage"}]
    assert homepage.metadata["selection"]["selection_status"] == "page_gate_reject"


def test_extraction_attempt_list_never_exceeds_max_urls() -> None:
    discovered = [
        native(str(source_id), article_index)
        for source_id in range(12)
        for article_index in range(1, 7)
    ]
    discovered.extend(
        open_item(domain_index, article_index)
        for domain_index in range(30)
        for article_index in range(1, 4)
    )
    accepted, _ = filter_discovered(discovered, max_urls=32, max_per_domain=2)
    assert len(accepted) == 32
