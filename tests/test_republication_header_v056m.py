from __future__ import annotations

from longread_collector.classification_v056m import classify_candidate_v056m
from longread_collector.content_identity_v056j import evaluate_content_identity


def _analysis_body(count: int = 28) -> str:
    return "\n\n".join(
        f"第{i}段。专家表示，数据显示人工智能的数据、算力和算法正在协同变化。"
        "研究机构指出，产业应用需要结合基础设施、治理规则和长期投入进行分析。"
        for i in range(count)
    )


def test_dated_external_publisher_link_marks_complete_republication() -> None:
    title = "底层突破筑牢人工智能技术根基"
    markdown = (
        f"# {title}\n\n"
        "2026年08月06日 06:04[经济日报](http://ipaper.ce.cn/pc/content/202608/06/content_336861.html)\n\n"
        "## 释放数据价值\n\n"
        + _analysis_body(24)
        + "\n\n## 夯实算力底座\n\n"
        + _analysis_body(20)
        + "\n\n## 提升算法优势\n\n"
        + _analysis_body(16)
        + "\n\n新浪财经声明：此消息系转载自合作媒体，文章内容仅供参考。"
    )
    identity = evaluate_content_identity(title=title, markdown=markdown)
    assert identity.body_prose_chars >= 3400
    result = classify_candidate_v056m(
        url="https://finance.example.com/article/ai-foundation",
        title=title,
        markdown=markdown,
        published_at="2026-08-06T06:04:00+08:00",
        verification_level="C",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "secondary_republish"
    assert result.original_publisher == "经济日报"
    assert result.source_action == "retain_with_source_label"
    assert result.reason == "complete_transparent_republication_v056m"


def test_same_host_dated_link_does_not_create_false_republication() -> None:
    title = "一篇原创深度报道"
    markdown = (
        f"# {title}\n\n"
        "2026年08月06日 06:04[本站](https://news.example.com/about)\n\n"
        + _analysis_body(60)
    )
    result = classify_candidate_v056m(
        url="https://news.example.com/article/original",
        title=title,
        markdown=markdown,
        published_at="2026-08-06T06:04:00+08:00",
        verification_level="B",
        content_chars=len(markdown),
    )
    assert not (
        result.source_relationship == "secondary_republish"
        and result.original_publisher == "本站"
    )
