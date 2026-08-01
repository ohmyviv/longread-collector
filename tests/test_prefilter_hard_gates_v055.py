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
