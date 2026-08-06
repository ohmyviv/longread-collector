from __future__ import annotations

import asyncio
from datetime import datetime
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from longread_collector.classification_v056m import classify_candidate_v056m
from longread_collector.direct_html_v056m import parse_direct_html_v056m
from longread_collector.extraction import FallbackBudget
from longread_collector.extraction_v056m import extract_article_v056m
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.page_gate_policy_v056m import (
    evaluate_page_gate_policy_v056m,
)
from longread_collector.post_extraction_gates_v056m import (
    apply_post_extraction_gates_v056m,
)
from longread_collector.publication_date_v056m import (
    extract_body_publication_date_v056m,
)
from longread_collector.selection_plan_v056 import SelectionReservePlan
from longread_collector.staged_reserve_v056m import build_second_stage_v056m

BJ = ZoneInfo("Asia/Shanghai")


def _long_body(seed: str, count: int = 24) -> str:
    return "\n\n".join(
        (
            f"{seed}第{i}段。记者采访了多位研究者和行业人士，数据显示这一变化"
            "正在影响政策、产业和普通人的选择。受访者表示，需要结合历史背景、"
            "实施约束和不同观点进行分析，不能只看单一指标。"
        )
        for i in range(count)
    )


def test_nanfang_chinese_labelled_date_overrides_live_clock() -> None:
    markdown = """
2026-08-06 14:21:28

[南风窗 2026年 第 5 期](https://example.com/magazine/530.html)
[出版时间：2026-02-23](https://example.com/magazine/530.html)

### 走向世界，做一个难缠的女人 ——专访海伦·刘易斯

作者：赵淑荷 来源：南风窗 日期：2026-02-23

""" + _long_body("女性主义访谈")
    evidence = extract_body_publication_date_v056m(markdown)
    assert evidence is not None
    assert evidence.value.date().isoformat() == "2026-02-23"
    assert evidence.source in {
        "body_header_chinese_byline_date",
        "body_header_chinese_labeled_date",
    }


def test_nanfang_old_article_is_terminally_rejected() -> None:
    markdown = """
2026-08-06 14:21:28

### 走向世界，做一个难缠的女人 ——专访海伦·刘易斯

作者：赵淑荷 来源：南风窗 日期：2026-02-23

""" + _long_body("女性主义访谈")
    discovered = DiscoveredURL(
        url="https://www.nfcmag.com/article/9545.html",
        title="走向世界，做一个难缠的女人 ——专访海伦·刘易斯",
        published_at="2026-08-06T14:21:28+08:00",
    )
    article = ExtractedArticle(
        article_id="nfcmag-old",
        url=discovered.url,
        url_canonical=discovered.url,
        domain="nfcmag.com",
        title=discovered.title,
        published_at=discovered.published_at,
        extraction_status="success",
        verification_level="B",
        content_markdown=markdown,
        content_chars=len(markdown),
        page_type="article",
        content_type="interview",
        candidate_disposition="formal_candidate",
        source_relationship="original",
        classification_reason="reported_interview",
        eligible_for_editor=True,
        metadata={"content_metrics": {"body_prose_chars": 5000}},
    )
    result = apply_post_extraction_gates_v056m(
        discovered,
        article,
        now=datetime(2026, 8, 6, 14, 30, tzinfo=BJ),
    )
    assert result["freshness_rejected"] is True
    assert article.published_at.startswith("2026-02-23")
    assert article.candidate_disposition == "reject"


def test_training_opening_recap_is_not_regulatory_guidance() -> None:
    markdown = """
# 全市镇（街道）党（工）委书记能力建设专题培训班开班

开班仪式上，市领导出席并作开班动员讲话。全体学员参加活动。

培训期间将安排专题授课、现场教学和交流研讨，课程安排覆盖基层治理。
本次培训班由市委组织部主办，相关单位承办。
"""
    result = classify_candidate_v056m(
        url="https://www.wuxi.gov.cn/doc/2026/training.html",
        title="全市镇（街道）党（工）委书记能力建设专题培训班开班",
        markdown=markdown,
        published_at="2026-08-06",
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "training_event_recap"
    assert result.page_type == "event_news"


def test_complete_transparent_republication_is_formal() -> None:
    title = "底层突破筑牢人工智能技术根基"
    markdown = (
        f"# {title}\n\n"
        "来源：经济日报\n\n"
        "原文链接：[经济日报原文](https://example.com/original/ai-foundation)\n\n"
        "## 数据基础\n\n"
        + _long_body("人工智能数据基础", 10)
        + "\n\n## 算力和算法\n\n"
        + _long_body("算力算法分析", 10)
    )
    result = classify_candidate_v056m(
        url="https://example-republisher.com/article/ai-foundation",
        title=title,
        markdown=markdown,
        published_at="2026-08-06",
        verification_level="C",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "secondary_republish"
    assert result.duplicate_type == "syndicated_republish"
    assert result.source_action == "retain_with_source_label"
    assert result.original_publisher == "经济日报"


def test_magazine_issue_landing_is_rejected_before_extraction() -> None:
    item = DiscoveredURL(
        url="https://www.nfcmag.com/magazine/545.html",
        title="2026年16期 - 南风窗",
    )
    decision = evaluate_page_gate_policy_v056m(item)
    assert decision.rejected is True
    assert decision.reject_reason == "magazine_issue_landing"
    assert item.metadata["page_gate"]["page_type"] == "magazine_issue_landing"


def test_direct_html_parser_prefers_jsonld_article_body() -> None:
    body = _long_body("基因编辑伦理", 20)
    payload = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": "国家科技伦理委员会委员：伦理为何失守",
        "datePublished": "2026-08-06T10:00:00+08:00",
        "author": {"@type": "Person", "name": "新京报记者"},
        "articleBody": body,
    }
    html = (
        '<script type="application/ld+json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )
    data = parse_direct_html_v056m(html, url="https://example.com/detail/1.html")
    assert data["title"].startswith("国家科技伦理委员会委员")
    assert len(data["markdown"]) > 1600
    assert data["published_at"].startswith("2026-08-06")
    assert data["metadata"]["direct_html_method"] == "embedded_json"


def test_zero_credit_direct_html_recovery_precedes_firecrawl(monkeypatch) -> None:
    title = "文和友败走广深，景点式餐饮为何火爆不再"
    body = f"# {title}\n\n" + _long_body("餐饮商业调查", 24)

    async def fake_direct(url: str):
        return (
            {
                "markdown": body,
                "title": title,
                "published_at": "2026-08-06T09:00:00+08:00",
                "author": "新京报记者",
                "description": "",
                "metadata": {"direct_html_method": "embedded_json"},
            },
            {"http_status": 200, "latency_ms": 10, "request_sent": True},
        )

    monkeypatch.setattr(
        "longread_collector.extraction_v056m.read_direct_html_v056m",
        fake_direct,
    )

    class EmptyJina:
        async def read(self, url: str):
            return {"markdown": "", "title": title, "published_at": "2026-08-06"}, {
                "http_status": 200,
                "latency_ms": 1,
            }

    class ForbiddenFirecrawl:
        async def scrape(self, url: str):
            raise AssertionError("Firecrawl must not be called after direct recovery")

    settings = SimpleNamespace(
        min_body_chars=900,
        editor_min_body_chars=1600,
        content_cell_limit=50000,
    )
    budget = FallbackBudget(remaining=1)
    article = asyncio.run(
        extract_article_v056m(
            DiscoveredURL(url="https://example.com/detail/1.html", title=title),
            EmptyJina(),
            ForbiddenFirecrawl(),
            settings,
            budget,
        )
    )
    assert article.extractor_used == "direct_html"
    assert article.extraction_status == "success"
    assert budget.remaining == 1
    assert not any(
        attempt.get("extractor") == "firecrawl"
        for attempt in article.extraction_attempts
    )


def _selected_item(index: int, *, status: str, priority: int = 45) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://source{index}.example.com/article/{index}.html",
        title=f"深度调查文章标题第{index}篇",
        metadata={
            "page_gate": {"reject_reason": ""},
            "selection": {
                "selection_bucket": "open",
                "selection_group": f"group-{index}",
                "selection_status": status,
                "selected_order": index if status == "selected" else 0,
                "score_components": {
                    "editorial_priority": priority,
                    "quality": 5,
                    "freshness_ordinal": 5,
                    "article_confidence": 3,
                    "depth": 3,
                    "title_richness": 3,
                    "description_richness": 2,
                    "rank_score": 100 - index,
                },
            },
        },
    )


def _usable_article(index: int, item: DiscoveredURL) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=f"article-{index}",
        url=item.url,
        url_canonical=item.url,
        domain=f"source{index}.example.com",
        title=item.title,
        extraction_status="success",
        verification_level="B",
        candidate_disposition="formal_candidate",
        eligible_for_editor=True,
    )


def test_unused_first_stage_capacity_can_reach_32_attempts() -> None:
    first = [_selected_item(i, status="selected") for i in range(12)]
    reserves = [
        _selected_item(i, status="editorial_priority_reserve")
        for i in range(12, 32)
    ]
    plan = SelectionReservePlan(max_urls=32, selected=first, reserves=reserves)
    decision = build_second_stage_v056m(
        plan=plan,
        first_stage=first,
        deferred=[],
        first_articles=[
            _usable_article(i, item) for i, item in enumerate(first)
        ],
        max_attempts=32,
    )
    assert len(first) + len(decision.second_stage) == 32
    assert len(decision.second_stage) == 20
