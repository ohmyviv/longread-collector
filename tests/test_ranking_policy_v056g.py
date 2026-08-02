from __future__ import annotations

from longread_collector.initial_selection_threshold_v056g import (
    INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY,
    apply_initial_selection_threshold,
)
from longread_collector.models import DiscoveredURL
from longread_collector.ranked_freshness_v056 import score_with_resolved_freshness
from longread_collector.ranked_selection_plan_v056 import filter_discovered
from longread_collector.selection_plan_v056 import (
    clear_selection_plan,
    current_selection_plan,
)


def item(
    url: str,
    title: str,
    *,
    description: str = "A complete reported article with evidence.",
    published_at: str = "2026-08-02",
    source_id: str = "source-a",
    method: str = "rss",
) -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at=published_at,
        rank=1,
        discovery_method=method,
        query_or_source=f"source:{source_id}",
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_id,
            "native_method": method,
        },
    )


def annotated(priority: int, index: int) -> DiscoveredURL:
    current = item(
        f"https://source{index}.example.com/2026/08/02/article-{index}.html",
        f"Article {index}",
        source_id=f"source{index}",
    )
    current.metadata["selection"] = {
        "selection_status": "selected",
        "selection_bucket": "native",
        "selection_group": f"source:source{index}",
        "score_components": {
            "editorial_priority": priority,
            "quality": 0,
            "freshness_ordinal": 3,
            "article_confidence": 2,
            "depth": 0,
            "title_richness": 1,
            "description_richness": 1,
            "rank_score": 0,
        },
    }
    return current


def test_initial_threshold_applies_when_caps_leave_capacity_unfilled() -> None:
    strong = annotated(INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY + 5, 1)
    weak = annotated(INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY - 1, 2)
    reserve = annotated(INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY - 2, 3)
    reserve.metadata["selection"]["selection_status"] = "bucket_capacity_reserve"

    selected = apply_initial_selection_threshold(
        discovered=[strong, weak, reserve],
        selected=[strong, weak],
        max_urls=32,
    )

    assert selected == [strong]
    assert weak.metadata["selection"]["selection_status"] == (
        "editorial_priority_reserve"
    )
    assert weak.metadata["selection"]["initial_selection_threshold_applied"] is True


def test_initial_threshold_is_not_a_gate_without_competition() -> None:
    weak = annotated(INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY - 10, 1)
    selected = apply_initial_selection_threshold(
        discovered=[weak],
        selected=[weak],
        max_urls=32,
    )
    assert selected == [weak]
    assert weak.metadata["selection"]["initial_selection_threshold_applied"] is False


def test_profile_and_weekend_commentary_receive_editorial_signals() -> None:
    profile = item(
        "https://www.bjnews.com.cn/depth/2026/08/02/profile.html",
        "逝者｜改道去灾区，他的最后一次重装徒步",
    )
    weekend = item(
        "https://www.newyorker.com/the-weekend-essay/pop-stars-careers-in-eras",
        "Forget Albums—Pop Stars Measure Their Careers in Eras Now",
        source_id="new-yorker",
    )
    _, profile_components = score_with_resolved_freshness(profile, 0)
    _, weekend_components = score_with_resolved_freshness(weekend, 0)
    assert profile_components["profile_signal"] == 20
    assert weekend_components["reporting_signal"] >= 14


def test_article_discussing_newsletters_is_not_treated_as_newsletter_page() -> None:
    article = item(
        "https://www.theatlantic.com/health/archive/2026/08/fauci-capitol-hill/",
        "Fauci’s Return to Capitol Hill",
        description="A public health analysis adapted from a newsletter discussion.",
        source_id="atlantic",
    )
    actual_newsletter = item(
        "https://www.theatlantic.com/newsletters/archive/2026/08/fauci/",
        "Fauci’s Return to Capitol Hill newsletter",
        description="The weekly newsletter edition.",
        source_id="atlantic",
    )
    _, article_components = score_with_resolved_freshness(article, 0)
    _, newsletter_components = score_with_resolved_freshness(actual_newsletter, 0)
    assert article_components["low_value_format_penalty"] == 0
    assert newsletter_components["low_value_format_penalty"] < 0


def test_mojibake_commercial_and_academic_landings_are_penalized() -> None:
    mojibake = item(
        "https://inewsweek.cn/article/2026/08/02/broken.html",
        "Chinaâ€™s economy â€“ a new era",
    )
    commercial = item(
        "https://example.com/reviews/chair-vs-chair.html",
        "Chair A vs Chair B: We Tested Them Head to Head",
    )
    academic = item(
        "https://academic.oup.com/journal/article/12/3/100/123456",
        "Scientists’ warning on climate change",
    )
    _, mojibake_components = score_with_resolved_freshness(mojibake, 0)
    _, commercial_components = score_with_resolved_freshness(commercial, 0)
    _, academic_components = score_with_resolved_freshness(academic, 0)
    assert mojibake_components["mojibake_penalty"] == -40
    assert commercial_components["commercial_penalty"] <= -30
    assert academic_components["academic_landing_penalty"] <= -18


def test_strong_unknown_native_search_fallback_is_still_initial_reserve() -> None:
    clear_selection_plan()
    fallback = item(
        "https://news.ifeng.com/c/7vactyAKzz6",
        "Investigation reveals failures in a public response",
        published_at="",
        source_id="ifeng",
        method="firecrawl_search",
    )
    fallback.metadata["freshness"] = {
        "native_search_fallback": True,
        "strong_fallback_depth": True,
        "freshness_unknown": True,
        "unknown_date_policy": "defer_deep_native_search_fallback",
    }
    current = item(
        "https://current.example.com/2026/08/02/current-analysis.html",
        "Current analysis of industrial policy",
        source_id="current",
    )

    selected, rejected = filter_discovered(
        [fallback, current], max_urls=1, max_per_domain=2
    )
    assert rejected == []
    assert selected == [current]
    assert fallback.metadata["selection"]["selection_status"] == (
        "evidence_reserve_only"
    )
    plan = current_selection_plan()
    assert plan is not None
    assert fallback in plan.reserves
