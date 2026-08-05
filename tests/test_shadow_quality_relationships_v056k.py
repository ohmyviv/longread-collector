from __future__ import annotations

from longread_collector.classification_v056k_final import (
    classify_candidate_v056k_final as classify_candidate_v056k,
)


def _paragraph(seed: str, repeat: int = 36) -> str:
    return "".join(
        f"{seed} 第{i}段包含数据、案例、采访和背景分析，形成完整正文。"
        "记者进一步核对政策文件、行业统计和多方回应，并讨论变化的原因、影响与限制。\n\n"
        for i in range(repeat)
    )


def test_event_recap_uses_body_heading_when_cache_title_is_generic() -> None:
    markdown = (
        "导航中的研究报告、培训班和成果栏目\n\n"
        "# 中国社会科学院举办科技考古与文化遗产保护国际学术研讨会\n\n"
        "会议由中国社会科学院主办，多位领导出席开幕式并致辞。"
        "多位专家作主旨发言，来自多国的300余位专家学者与会，会议设置六大议题。\n\n"
        + _paragraph("会议现场", 30)
        + "来源：中国社会科学网\n"
    )
    result = classify_candidate_v056k(
        url="http://naes.cssn.cn/cj_zwz/hd/cjysx/202608/example.shtml",
        title="财经院时讯 | 财经战略研究院",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "conference_recap"
    assert result.source_relationship == "original"


def test_government_hosted_media_republish_returns_to_article_lane() -> None:
    markdown = (
        "# 职教出海，为西部陆海新通道注入持久动能\n\n"
        "来源：新华财经 发布时间：2026-08-04 17:21\n\n"
        "记者结合海关数据、职业院校案例和主管部门回应展开报道。\n\n"
        + _paragraph("职业教育出海", 50)
    )
    result = classify_candidate_v056k(
        url="https://www.cq.gov.cn/zt/xblhxtd/tpxw/202608/example.html",
        title="职教出海，为西部陆海新通道注入持久动能重庆市人民政府网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.page_type == "article"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "新华财经"


def test_cnr_media_republish_is_not_an_institutional_report() -> None:
    markdown = (
        "# 人工智能技术产业迎来爆发式增长\n\n"
        "2026-08-05 09:38:44 来源：人民邮电报\n\n"
        "工业和信息化部数据显示产业规模增长，中国信通院研究报告提供行业背景。\n\n"
        + _paragraph("人工智能产业", 36)
        + "（记者 张鸣）\n"
    )
    result = classify_candidate_v056k(
        url="https://www.cnr.cn/tech/gstj/20260805/example.shtml",
        title="人工智能技术产业迎来爆发式增长央广网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "人民邮电报"


def test_primary_government_document_stays_special_on_secondary_host() -> None:
    markdown = (
        "# 国务院关于印发《知识产权保护和运用‘十五五’规划》的通知\n\n"
        "发布时间：2026-08-04 来源：中国政府网\n\n"
        "国发〔2026〕30号\n\n各省、自治区、直辖市人民政府：现将规划印发给你们。\n\n"
        + _paragraph("知识产权规划", 70)
    )
    result = classify_candidate_v056k(
        url="https://www.mee.gov.cn/zcwj/gwywj/202608/example.shtml",
        title="国务院关于印发《知识产权保护和运用‘十五五’规划》的通知",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "special_candidate"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "中国政府网"


def test_contextual_translation_reference_does_not_relabel_original_article() -> None:
    markdown = (
        "# A Trojan Horse Is Supposed to Have Humans Inside It\n\n"
        "By Emily Wilson\n\n"
        + _paragraph("Original cultural criticism", 50)
        + "### About the Author\n\n"
        "Emily Wilson has published verse translations of The Odyssey and The Iliad.\n"
    )
    result = classify_candidate_v056k(
        url="https://www.theatlantic.com/ideas/2026/08/odyssey-movie-trojan-horse/",
        title="A Trojan Horse Is Supposed to Have Humans Inside It",
        author="Emily Wilson",
        markdown=markdown,
        verification_level="A",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "original"
    assert result.original_publisher == ""


def test_financing_reject_keeps_transparent_source_relationship() -> None:
    markdown = (
        "# 术也科技完成Pre-A轮融资，用Physical AI打造自驱动实验室\n\n"
        "2026-08-04 19:20:41 来源：财讯网\n\n"
        "公司完成Pre-A轮融资，本轮融资由某基金领投，多家机构跟投。"
        "融资资金将主要用于研发、市场拓展和团队建设。\n\n"
        + _paragraph("公司产品和团队", 45)
    )
    result = classify_candidate_v056k(
        url="https://mtz.china.com/touzi/2026/0804/example.html",
        title="术也科技完成Pre-A轮融资，用Physical AI打造自驱动实验室中华网",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "财讯网"
