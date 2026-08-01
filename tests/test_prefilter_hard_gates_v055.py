from longread_collector.models import DiscoveredURL
from longread_collector.prefilter_v055 import (
    PREFILTER_VERSION,
    discovery_hard_gate_reason,
    filter_discovered,
)


def _item(url: str, title: str, description: str = "") -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at="2026-08-01",
        rank=1,
        discovery_method="rss",
        query_or_source="source:test",
        metadata={
            "purpose": "native_source_scan",
            "source_id": "test",
            "source_name": "Test Source",
        },
    )


def _native(source_id: str, article_index: int) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://{source_id}.example.com/2026/08/01/article-{article_index}.html",
        title=f"Investigation feature {source_id} {article_index}",
        description="A detailed reported article with evidence and analysis.",
        published_at="2026-08-01",
        rank=article_index,
        discovery_method="rss",
        query_or_source=f"source:{source_id}",
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_id,
        },
    )


def _open(domain_index: int, article_index: int) -> DiscoveredURL:
    return DiscoveredURL(
        url=(
            f"https://open{domain_index}.example.org/2026/08/01/"
            f"analysis-{article_index}.html"
        ),
        title=f"Open analysis {domain_index} {article_index}",
        description="An independent analysis article with sufficient metadata.",
        published_at="2026-08-01",
        rank=article_index,
        discovery_method="firecrawl_search",
        query_or_source="en_ai_fresh",
    )


def test_known_non_articles_are_rejected_before_extraction() -> None:
    cen = _item("https://cen.acs.org/explore/features.html", "Features")
    correction = _item(
        "https://www.nature.com/articles/s1",
        "Author Correction: Important membrane paper",
    )
    roundup = _item(
        "https://www.thenewhumanitarian.org/news/2026/08/01/cheat-sheet",
        "The Cheat Sheet: Hamas agrees to disarm and more",
    )
    pr = _item(
        "https://www.prnewswire.com/news-releases/ai-market.html",
        "Generative AI Market worth $1,658 billion by 2033",
    )

    assert discovery_hard_gate_reason(cen) == "listing_page"
    assert discovery_hard_gate_reason(correction) == "correction_notice"
    assert discovery_hard_gate_reason(roundup) == "news_roundup"
    assert discovery_hard_gate_reason(pr) == "press_release"

    accepted, rejected = filter_discovered(
        [cen, correction, roundup, pr], max_urls=32, max_per_domain=2
    )
    assert accepted == []
    assert {row["reason"] for row in rejected} == {
        "listing_page",
        "correction_notice",
        "news_roundup",
        "press_release",
    }
    assert cen.metadata["selection"]["prefilter_version"] == PREFILTER_VERSION


def test_real_feature_keeps_capacity_when_roundup_is_removed() -> None:
    roundup = _item(
        "https://www.thenewhumanitarian.org/news/2026/08/01/cheat-sheet",
        "The Cheat Sheet: weekly humanitarian news roundup",
    )
    feature = _item(
        "https://www.thenewhumanitarian.org/analysis/2026/07/29/home-gardening-sudan",
        "How home gardening became a lifeline in Sudan's besieged towns",
        "A reported feature based on interviews in Sudan.",
    )

    accepted, rejected = filter_discovered(
        [roundup, feature], max_urls=1, max_per_domain=2
    )
    assert [item.url for item in accepted] == [feature.url]
    assert rejected == [{"url": roundup.url, "reason": "news_roundup"}]


def test_source_chase_leads_are_not_discarded_by_prefilter() -> None:
    occrp_project = _item(
        "https://www.occrp.org/en/project/bad-practice",
        "Bad Practice",
        "An OCCRP investigation project containing individual reports.",
    )
    takeaways = _item(
        "https://www.nytimes.com/2026/07/31/magazine/takeaways-ai.html",
        "Five Takeaways From the Times Investigation Into Larry Ellison's A.I. Gamble",
    )

    assert discovery_hard_gate_reason(occrp_project) == ""
    assert discovery_hard_gate_reason(takeaways) == ""

    accepted, rejected = filter_discovered(
        [occrp_project, takeaways], max_urls=2, max_per_domain=2
    )
    assert {item.url for item in accepted} == {
        occrp_project.url,
        takeaways.url,
    }
    assert rejected == []


def test_unused_capacity_backfills_third_and_fourth_native_articles() -> None:
    discovered = [
        _native(source_id, article_index)
        for source_id in ("native0", "native1", "native2", "native3")
        for article_index in range(1, 5)
    ]
    discovered.extend(
        _open(domain_index, article_index)
        for domain_index in range(10)
        for article_index in range(1, 3)
    )

    accepted, _ = filter_discovered(
        discovered,
        max_urls=32,
        max_per_domain=2,
    )
    native = [
        item for item in accepted
        if item.metadata.get("purpose") == "native_source_scan"
    ]
    open_items = [
        item for item in accepted
        if item.metadata.get("purpose") != "native_source_scan"
    ]

    assert len(accepted) == 32
    assert len(native) == 16
    assert len(open_items) == 16
    assert sum(
        bool(item.metadata["selection"].get("capacity_backfill"))
        for item in native
    ) == 8
    assert sorted(
        item.metadata["selection"]["selected_order"] for item in accepted
    ) == list(range(1, 33))
