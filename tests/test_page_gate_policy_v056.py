from __future__ import annotations

import pytest

from longread_collector.models import DiscoveredURL
from longread_collector.page_gate_policy_v056 import evaluate_page_gate_policy
from longread_collector.prefilter_v056c import filter_discovered


def item(url: str, title: str, description: str = "") -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at="2026-08-01",
        discovery_method="firecrawl_search",
    )


@pytest.mark.parametrize(
    ("candidate", "reason"),
    [
        (
            item(
                "https://www.unep.org/news-and-stories/press-release/example",
                "UNEP announces a new initiative",
            ),
            "press_release",
        ),
        (
            item(
                "https://www.wired.com/gallery/best-organic-mattresses/",
                "The Best Organic Mattresses We've Tested",
                "We may earn a commission from links on this page.",
            ),
            "commerce_or_buying_guide",
        ),
        (
            item(
                "https://domyessay.com/blog/history-essay-topics",
                "280+ History Essay Topics for Students",
            ),
            "seo_essay_farm",
        ),
        (
            item(
                "https://example.com/newsletter/daily",
                "The Daily Newsletter",
            ),
            "newsletter_or_roundup",
        ),
        (
            item(
                "https://www.theguardian.com/news/audio/2026/aug/01/podcast",
                "Today in Focus podcast: a changing world",
            ),
            "podcast_page",
        ),
        (
            item(
                "https://libguides.example.edu/journal-articles/databases",
                "Journal articles – databases",
            ),
            "database_or_resource_index",
        ),
        (
            item(
                "https://university.example.edu/programs/public-policy",
                "Graduate Program in Public Policy",
            ),
            "course_or_program_page",
        ),
        (
            item(
                "https://university.example.edu/about/research-center",
                "公共经济、金融与治理研究中心",
            ),
            "institution_profile",
        ),
        (
            item(
                "https://example.cn/notices/award",
                "关于推荐参评第36届中国新闻奖作品的公示",
            ),
            "award_or_public_notice",
        ),
        (
            item(
                "https://example.edu/events/webinar",
                "Register for our climate policy webinar",
                "Join us and register for the event.",
            ),
            "event_or_release_announcement",
        ),
    ],
)
def test_confirmed_non_article_types_are_rejected(candidate, reason) -> None:
    decision = evaluate_page_gate_policy(candidate)
    assert decision.reject_reason == reason
    assert candidate.metadata["page_gate"]["policy_version"] == (
        "page-gate-policy-v0.5.6f"
    )


@pytest.mark.parametrize(
    "candidate",
    [
        item(
            "https://www.newyorker.com/magazine/2026/08/03/a-feature",
            "How Artificial Intelligence Changed the Way We Think",
        ),
        item(
            "https://e360.yale.edu/features/batteries-mining-recycling",
            "Can New Battery Chemistry Reduce the Cost of the Energy Transition?",
        ),
        item(
            "https://academic.oup.com/journal/article/42/1/100/123456",
            "A systematic review of environmental policy",
        ),
        item(
            "https://agency.gov.cn/guidance/privacy-guidance.pdf",
            "Artificial intelligence privacy guidance document",
        ),
        item(
            "https://news.example.com/article/degree-of-uncertainty.html",
            "The degree of uncertainty facing central banks",
        ),
        item(
            "https://news.example.cn/article/company-announcement.html",
            "公告显示公司上半年研发投入增长",
        ),
        item(
            "https://news.example.com/article/inside-the-research-center.html",
            "Inside the Research Center That Tracks Emerging Viruses",
        ),
        item(
            "https://www.tmtpost.com/8036314.html",
            "从深度报道到长访谈：媒体人重做播客的商业逻辑",
            (
                "文章分析社会调查、特稿记者和科技媒体主编如何把采访经验"
                "转化为商业访谈产品，并讨论播客行业的商业模式。"
            ),
        ),
    ],
)
def test_articles_and_primary_documents_are_not_false_positive_rejects(candidate) -> None:
    decision = evaluate_page_gate_policy(candidate)
    assert decision.rejected is False


def test_podcast_episode_route_remains_rejected() -> None:
    episode = item(
        "https://example.com/podcast/episode-42",
        "Podcast: Episode 42",
        "Listen to this week's audio programme.",
    )
    assert evaluate_page_gate_policy(episode).reject_reason == "podcast_page"


def test_prefilter_records_page_gate_separately_from_capacity() -> None:
    buying = item(
        "https://www.wired.com/gallery/best-organic-mattresses/",
        "Best Organic Mattresses",
    )
    article = item(
        "https://news.example.com/article/current-investigation.html",
        "Current investigation into public spending",
    )
    accepted, rejected = filter_discovered([buying, article], max_urls=2)
    assert [candidate.url for candidate in accepted] == [article.url]
    assert rejected == [
        {"url": buying.url, "reason": "commerce_or_buying_guide"}
    ]
    assert buying.metadata["selection"]["selection_status"] == "page_gate_reject"
