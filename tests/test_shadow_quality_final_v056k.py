from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.classification_v056k_final import (
    classify_candidate_v056k_final,
)
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector import post_extraction_gates_v056k as post_gates
from longread_collector.publication_date_v056k_final import (
    extract_body_publication_date_final,
)

BJ = ZoneInfo("Asia/Shanghai")


def _paragraph(seed: str, repeat: int = 36) -> str:
    return "".join(
        f"{seed} 第{i}段包含数据、案例、采访和背景分析，形成完整正文。"
        "记者进一步核对政策文件、行业统计和多方回应，并讨论变化的原因、影响与限制。\n\n"
        for i in range(repeat)
    )


def test_cppcc_consultative_meeting_is_rejected() -> None:
    markdown = (
        "# CPPCC members discuss advancing 'AI Plus' initiative\n\n"
        "The CPPCC held its 48th biweekly consultative meeting in Beijing. "
        "Wang Huning presided over the meeting. Twelve CPPCC members spoke at "
        "the meeting. Officials from three ministries gave briefings at the "
        "meeting and vice-chairpersons attended the meeting.\n\n"
        + _paragraph("Meeting remarks", 30)
    )
    result = classify_candidate_v056k_final(
        url="http://en.cppcc.gov.cn/2026-08/03/c_1202277.htm",
        title="CPPCC members discuss advancing 'AI Plus' initiative",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "official_consultative_meeting_recap"


def test_external_header_source_is_secondary_republish() -> None:
    markdown = (
        "# 人工智能技术产业迎来爆发式增长\n\n"
        "2026-08-05 09:38:44 来源：人民邮电报\n\n"
        "工业和信息化部数据显示产业规模增长，记者结合报告与企业案例展开分析。\n\n"
        + _paragraph("人工智能产业", 45)
    )
    result = classify_candidate_v056k_final(
        url="https://www.cnr.cn/tech/gstj/20260805/example.shtml",
        title="人工智能技术产业迎来爆发式增长央广网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "人民邮电报"


def test_same_publisher_header_source_stays_original() -> None:
    markdown = (
        "# AI进厨房，味道怎么样\n\n"
        "2026-08-05 08:31 来源：中国经济网-《经济日报》 中国经济网记者\n\n"
        "记者深入采访实验室、食品企业和餐饮机构，分析人工智能的实际应用与局限。\n\n"
        + _paragraph("食品工业智能化", 48)
    )
    result = classify_candidate_v056k_final(
        url="http://www.ce.cn/xwzx/gnsz/gdxw/202608/example.shtml",
        title="AI进厨房，味道怎么样中国经济网——国家经济门户",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "original"
    assert result.original_publisher == ""


def test_emphasized_old_header_date_projects_terminal_reject() -> None:
    markdown = (
        "# 这就是名酒势能！汾酒抖音挑战赛播放量突破6.3亿次\n\n"
        "_2024-02-05 17:13:22_\n\n"
        + _paragraph("品牌挑战赛和营销传播", 45)
    )
    evidence = extract_body_publication_date_final(markdown)
    assert evidence is not None
    assert evidence.value.date().isoformat() == "2024-02-05"
    assert evidence.source == "body_header_emphasized_date"

    discovered = DiscoveredURL(
        url="https://www.yicai.com/news/example.html",
        title="这就是名酒势能！汾酒抖音挑战赛播放量突破6.3亿次",
        published_at="",
    )
    article = ExtractedArticle(
        article_id="fenjiu-old-promotion",
        url=discovered.url,
        url_canonical=discovered.url,
        domain="yicai.com",
        title=discovered.title,
        published_at="",
        extraction_status="success",
        verification_level="B",
        content_markdown=markdown,
        content_chars=len(markdown),
        candidate_disposition="formal_candidate",
        source_relationship="original",
        classification_version="collector-v0.5.6k",
        classification_reason="strong_editorial_structure_v056k",
        eligible_for_editor=True,
    )
    original = post_gates.extract_body_publication_date
    post_gates.extract_body_publication_date = extract_body_publication_date_final
    try:
        result = post_gates.apply_post_extraction_gates_v056k(
            discovered,
            article,
            now=datetime(2026, 8, 5, 22, 0, tzinfo=BJ),
        )
    finally:
        post_gates.extract_body_publication_date = original

    assert result["freshness_rejected"] is True
    assert article.candidate_disposition == "reject"
    assert article.reject_reason == "stale_article_over_14d"
    assert article.metadata["freshness"]["published_at_source"] == (
        "body_header_emphasized_date"
    )
