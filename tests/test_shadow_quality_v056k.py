from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.classification_v056k import classify_candidate_v056k
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.post_extraction_gates_v056k import apply_post_extraction_gates_v056k
from longread_collector.publication_date_v056k import extract_body_publication_date

BJ = ZoneInfo("Asia/Shanghai")


def _paragraph(seed: str, repeat: int = 24) -> str:
    return "".join(
        f"{seed} 第{i}段包含采访、数据、背景和影响分析，形成完整的事实与论证链条。\n\n"
        for i in range(repeat)
    )


def _article(
    *,
    url: str,
    title: str,
    markdown: str,
    published_at: str,
    source_relationship: str = "original",
) -> ExtractedArticle:
    return ExtractedArticle(
        article_id="test-article",
        url=url,
        url_canonical=url,
        domain=url.split("/")[2],
        title=title,
        published_at=published_at,
        extraction_status="success",
        verification_level="B",
        content_markdown=markdown,
        content_chars=len(markdown),
        candidate_disposition="formal_candidate",
        source_relationship=source_relationship,
        classification_version="collector-v0.5.6k",
        classification_reason="test_candidate",
        eligible_for_editor=True,
    )


def test_rejects_curated_member_digest() -> None:
    result = classify_candidate_v056k(
        url="https://warontherocks.com/member-digest",
        title="Why Egypt's Opinion of Ukraine Matters, Now and Later",
        markdown=(
            "# Why Egypt's Opinion of Ukraine Matters, Now and Later\n\n"
            "Welcome to The Ukraine Compass, a weekly digest only for War on the Rocks "
            "members. Each Monday, we bring you a curated selection of articles from "
            "Ukrainian media."
        ),
        verification_level="B",
        content_chars=4000,
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "curated_news_digest"


def test_rejects_financing_promotion() -> None:
    result = classify_candidate_v056k(
        url="https://mtz.china.com/touzi/2026/0804/255346.html",
        title="术也科技完成Pre-A轮融资，用Physical AI打造自驱动实验室",
        markdown=(
            "# 术也科技完成Pre-A轮融资，用Physical AI打造自驱动实验室\n\n"
            "公司宣布完成Pre-A轮融资。本轮融资由某基金领投，多家机构跟投。"
            "融资将用于产品研发、市场拓展和团队建设。" + _paragraph("公司介绍", 32)
        ),
        verification_level="B",
        content_chars=5000,
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "financing_promotion"


def test_rejects_student_social_practice_recap() -> None:
    result = classify_candidate_v056k(
        url="https://www.usst.edu.cn/2026/0803/c934a69751/page.htm",
        title="上理工健康学院社会实践团队走访调研脑机接口领域单位",
        markdown=(
            "# 上理工健康学院社会实践团队走访调研脑机接口领域单位\n\n"
            "暑期社会实践团队在带队老师指导下走访调研多家单位，学生代表分享学习体会。"
            "供稿单位：健康科学与工程学院。" + _paragraph("实践活动", 32)
        ),
        verification_level="B",
        content_chars=5000,
    )
    assert result.candidate_disposition == "reject"
    assert result.page_type == "institutional_activity"


def test_rejects_institutional_conference_recap() -> None:
    result = classify_candidate_v056k(
        url="https://example.edu.cn/news/conference.html",
        title="杏林萤火聚申城，共话样本创未来——生物样本库创新技术研讨活动成功举办",
        markdown=(
            "# 生物样本库创新技术研讨活动成功举办\n\n"
            "活动由多家单位主办，学院领导出席并致辞。会议设置主旨报告和三个分论坛，"
            "多位嘉宾发言，与会代表参加标准启动仪式。" + _paragraph("会议现场", 32)
        ),
        verification_level="B",
        content_chars=5000,
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "conference_recap"


def test_course_rule_ignores_navigation_template() -> None:
    markdown = (
        "课程 培训班 报名入口 学费说明\n\n"
        "# 多所高校财政学专业撤并背后\n\n"
        "记者调查多所高校财政学专业调整，采访院校负责人和学者，分析政策背景与就业变化。\n\n"
        + _paragraph("高校专业调整", 80)
    )
    result = classify_candidate_v056k(
        url="https://www.eeo.com.cn/2026/0803/984411.shtml",
        title="多所高校财政学专业撤并背后 - 经济观察网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.reason == "course_template_false_positive_recovered_v056k"


def test_rescues_registered_outlet_full_body_without_date() -> None:
    markdown = (
        "# 美联储最底层的运作方式将发生重大转变？如何影响市场\n\n"
        "作者：记者甲\n\n"
        "## 制度变化\n\n"
        + _paragraph("第一财经采访多名分析师", 90)
        + "## 市场影响\n\n机构回应称改革将影响利率预期。"
    )
    result = classify_candidate_v056k(
        url="https://www.yicai.com/news/103304692.html",
        title="美联储最底层的运作方式将发生重大转变？如何影响市场",
        author="记者甲",
        markdown=markdown,
        verification_level="C",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.reason == "strong_editorial_body_without_reliable_date_v056k"


def test_rescues_shorter_explicit_news_analysis() -> None:
    markdown = (
        "# 新闻分析｜AI对网络安全的“双刃剑”效应日益凸显\n\n"
        "新华社记者甲、乙\n\n"
        "## 攻防能力同步提升\n\n"
        + _paragraph("记者采访网络安全专家", 48)
        + "## 治理需要同步升级\n\n报告称企业需要建立新的风险控制体系。"
    )
    result = classify_candidate_v056k(
        url="https://www.news.cn/world/20260804/example/c.html",
        title="新闻分析｜AI对网络安全的“双刃剑”效应日益凸显-新华网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.reason == "strong_editorial_structure_v056k"


def test_preserves_market_data_card_reject() -> None:
    markdown = (
        "# A100ETF汇添富份额规模三年双降\n\n"
        "基金最新份额100亿份，近一年上涨17.92%，溢折率为0。以上内容基于公开资料，"
        "不构成投资建议。"
    )
    result = classify_candidate_v056k(
        url="https://www.eeo.com.cn/2026/0805/986935.shtml",
        title="A100ETF汇添富份额规模三年双降，近一年涨17.92%",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"


def test_complete_translation_is_direct_formal_candidate() -> None:
    markdown = (
        "# 激光技术如何为核反应堆提供燃料\n\n"
        + _paragraph("激光浓缩技术", 80)
        + "\n原文链接：\nhttps://www.technologyreview.com/2026/07/27/1140798/laser-nuclear-enrichment/\n"
    )
    result = classify_candidate_v056k(
        url="https://www.mittrchina.com/news/detail/16722",
        title="麻省理工科技评论-激光技术如何为核反应堆提供燃料",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "translated_republish"
    assert result.original_url.startswith("https://www.technologyreview.com/2026/07/27/")


def test_body_header_date_overrides_template_image_date() -> None:
    markdown = (
        "![template](https://example.com/fileftp/2025/07/2025-07-17/logo.png)\n\n"
        "# 郝珂灵：硅谷路径之外，AI的更多可能性\n\n"
        "2026-08-05 11:05:16 来源：中国青年报 作者：吴青潞\n\n"
        + _paragraph("人工智能报道", 32)
    )
    evidence = extract_body_publication_date(markdown)
    assert evidence is not None
    assert evidence.value.date().isoformat() == "2026-08-05"
    assert evidence.source == "body_header_date"

    discovered = DiscoveredURL(
        url="https://www.chinanews.com.cn/edu/2026/08-05/10672208.shtml",
        title="郝珂灵：硅谷路径之外，AI的更多可能性",
        published_at="2025-07-17",
        discovery_method="firecrawl_search",
    )
    article = _article(
        url=discovered.url,
        title=discovered.title,
        markdown=markdown,
        published_at="2025-07-17",
        source_relationship="secondary_republish",
    )
    result = apply_post_extraction_gates_v056k(
        discovered,
        article,
        now=datetime(2026, 8, 5, 22, 0, tzinfo=BJ),
    )
    assert result["freshness_rejected"] is False
    assert article.candidate_disposition == "formal_candidate"
    assert article.published_at.startswith("2026-08-05")
    assert article.metadata["freshness"]["published_at_source"] == "body_header_date"


def test_true_stale_article_projects_to_terminal_reject() -> None:
    discovered = DiscoveredURL(
        url="https://www.occrp.org/en/feature/what-it-means-to-be-sicilian",
        title="What It Means To Be Sicilian",
        published_at="2026-07-17T00:00:00+08:00",
    )
    article = _article(
        url=discovered.url,
        title=discovered.title,
        markdown="# What It Means To Be Sicilian\n\n" + _paragraph("Sicilian feature", 48),
        published_at="2026-07-17T00:00:00+08:00",
    )
    result = apply_post_extraction_gates_v056k(
        discovered,
        article,
        now=datetime(2026, 8, 5, 22, 0, tzinfo=BJ),
    )
    assert result["freshness_rejected"] is True
    assert article.candidate_disposition == "reject"
    assert article.reject_reason == "stale_article_over_14d"
    assert article.metadata["post_extraction_gate"]["terminal_projection"] is True


def test_translation_original_link_corrects_bad_site_metadata() -> None:
    markdown = (
        "# 激光技术如何为核反应堆提供燃料\n\n"
        + _paragraph("核燃料供应分析", 60)
        + "\n原文链接：\nhttps://www.technologyreview.com/2026/07/27/1140798/laser-nuclear-enrichment/\n"
    )
    discovered = DiscoveredURL(
        url="https://www.mittrchina.com/news/detail/16722",
        title="激光技术如何为核反应堆提供燃料",
        published_at="Sat, 12 Oct 2024 05:36:22 GMT",
        metadata={"purpose": "native_source_scan", "native_method": "reader_section"},
    )
    article = _article(
        url=discovered.url,
        title=discovered.title,
        markdown=markdown,
        published_at="Sat, 12 Oct 2024 05:36:22 GMT",
        source_relationship="translated_republish",
    )
    result = apply_post_extraction_gates_v056k(
        discovered,
        article,
        now=datetime(2026, 8, 5, 22, 0, tzinfo=BJ),
    )
    assert result["freshness_rejected"] is False
    assert article.candidate_disposition == "formal_candidate"
    assert article.published_at.startswith("2026-07-27")
    assert article.metadata["freshness"]["published_at_source"] == "body_original_url_date"
