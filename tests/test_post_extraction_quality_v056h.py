from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from longread_collector.classification_v056h import classify_candidate_v056h
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.post_extraction_gates_v056 import apply_post_extraction_gates
from longread_collector.post_freshness_v056h import normalize_extracted_publication_date

BJ = ZoneInfo("Asia/Shanghai")
LONG_BODY = "This is reported analysis with evidence, interviews and context. " * 220


def _classify(url: str, title: str, markdown: str = LONG_BODY):
    return classify_candidate_v056h(
        url=url,
        title=title,
        description="",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )


@pytest.mark.parametrize(
    ("url", "title", "markdown", "expected_reason"),
    [
        (
            "https://aeon.co/videos/the-workforce-of-elderly-women-recycling-what-vietnam-throws-away",
            "The workforce of elderly women recycling what Vietnam throws away | Aeon Videos",
            LONG_BODY,
            "video_page_v056h",
        ),
        (
            "https://cen.acs.org/acs-news/petroleum-research-fund-continues-supplemental/104/web/2026/07",
            "Petroleum Research Fund continues supplemental funding program with new grantees",
            LONG_BODY,
            "award_or_funding_announcement_v056h",
        ),
        (
            "https://cen.acs.org/acs-news/mark-thiemens-awarded-magellanic-premium/104/web/2026/07",
            "Mark Thiemens is awarded Magellanic Premium, the US’s oldest scientific prize",
            LONG_BODY,
            "award_or_funding_announcement_v056h",
        ),
        (
            "https://warontherocks.com/the-atlantic-brief-the-strait-of-hormuz-and-the-future-of-free-navigation/",
            "The Atlantic Brief: The Strait of Hormuz and the Future of Free Navigation",
            "For the first webinar, the organisers present a dialogue. Speakers: A, B and C. Register to join. "
            * 80,
            "event_announcement_or_recap_v056h",
        ),
        (
            "https://www.techtimes.com/articles/322674/20260802/ai4-2026-opens-tuesday.htm",
            "Ai4 2026 Opens Tuesday: Hinton and Ng Face Off on AI’s Existential Stakes",
            "The conference opens Tuesday. Registration, agenda, speakers, schedule, Standard Pass and VIP Pass. "
            * 80,
            "event_announcement_or_recap_v056h",
        ),
        (
            "https://www.xinhuanet.com/fortune/20260802/example.html",
            "太阳岛年会里的“康养之钥”",
            "本次年会由有关机构主办，多位嘉宾参会并围绕康养产业发表观点。会议议程包括论坛交流。"
            * 80,
            "event_announcement_or_recap_v056h",
        ),
        (
            "https://www.scau.edu.cn/2026/0801/c17861a441666/page.htm",
            "生物质学院成功举办第四期交叉学科论坛",
            "论坛由学院主办，多位嘉宾参会，会议设置主题报告和交流议程。" * 100,
            "event_announcement_or_recap_v056h",
        ),
        (
            "https://mini.caixin.com/2026-08-03/102470717.html",
            "财新闻｜持续发酵 欧足联或将投票罢免因凡蒂诺",
            "今日多条新闻摘要。" * 300,
            "news_roundup_v056h",
        ),
    ],
)
def test_real_shadow_non_editorial_false_accepts_are_rejected(
    url: str,
    title: str,
    markdown: str,
    expected_reason: str,
) -> None:
    result = _classify(url, title, markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == expected_reason


def _article(published_at: str) -> ExtractedArticle:
    return ExtractedArticle(
        article_id="old-yicai",
        url="https://www.yicai.com/news/103301988.html",
        url_canonical="https://yicai.com/news/103301988.html",
        domain="yicai.com",
        title="华侨系案追踪：余增云亲属被警方控制",
        published_at=published_at,
        language="zh",
        canonical_source="第一财经",
        hosting_source="第一财经",
        extractor_used="jina",
        extraction_status="success",
        verification_level="B",
        content_markdown="调查报道正文。" * 1500,
        content_chars=9000,
        eligible_for_editor=True,
        candidate_disposition="formal_candidate",
        content_type="analysis_or_commentary",
        classification_version="collector-v0.5.6h",
        classification_reason="verified_longform_default",
    )


@pytest.mark.parametrize("published_at", ["2025年8月13日", "2026年4月28日"])
def test_chinese_extracted_dates_trigger_stale_post_gate(published_at: str) -> None:
    discovered = DiscoveredURL(
        url="https://www.yicai.com/news/103301988.html",
        title="华侨系案追踪：余增云亲属被警方控制",
        discovery_method="section_scan",
        query_or_source="source:yicai",
        language="zh",
        metadata={"purpose": "native_source_scan", "native_method": "section_scan"},
    )
    article = _article(published_at)
    result = apply_post_extraction_gates(
        discovered,
        article,
        now=datetime(2026, 8, 3, 15, 0, tzinfo=BJ),
    )
    assert result["freshness_rejected"] is True
    assert article.candidate_disposition == "reject"
    assert article.reject_reason == "stale_article_over_14d"
    assert article.metadata["freshness"]["extracted_date_raw"] == published_at


def test_chinese_date_normalization_is_auditable() -> None:
    assert normalize_extracted_publication_date("2026年4月28日") == "2026-04-28T00:00:00"


def test_reported_conference_analysis_is_not_mistaken_for_event_listing() -> None:
    result = _classify(
        "https://www.propublica.org/article/conference-industry-investigation",
        "How Conference Organizers Hid Safety Failures for Years",
        "An investigation based on records and interviews explains the failures. " * 220,
    )
    assert result.candidate_disposition == "formal_candidate"


def test_reported_grant_fraud_is_not_mistaken_for_funding_announcement() -> None:
    result = _classify(
        "https://www.propublica.org/article/grant-fraud-investigation",
        "Investigation: How Grant Fraud Distorted Public Research Funding",
        "Records, interviews and financial documents reveal a systemic problem. " * 220,
    )
    assert result.candidate_disposition == "formal_candidate"
