from __future__ import annotations

from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    MEDIUM_VERSION,
    PUBLICATION_VERSION,
    SOURCE_VERSION,
    SURFACE_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    ContentMedium,
    DiscoveryRecord,
    EditorialVerdict,
    PageSurface,
    PolicyAction,
    RunContext,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION, EditorialJudge
from longread_collector.v06.selection import evaluate_policy


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260811-042738-BJT-pre_report-pr734-replay",
        group_id="pre_report",
        scheduled_at_bj="2026-08-11 03:57:00",
        started_at_bj="2026-08-11 04:27:38",
        collector_version="collector-v0.6-pr7.3.4",
    )


def _record(item_id: str, *, url: str, title: str) -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        title_hint=title,
        source_id="pre-report-fixture",
        discovery_method="web",
        raw_metadata={},
    )


def _bundle(item_id: str, *, title: str, body: str) -> AcquisitionBundle:
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def _issue_body() -> str:
    pages = "\n".join(
        (
            "#### 01版：要闻",
            "#### 02版：要闻",
            "#### 03版：经济",
            "#### 04版：影像",
            "#### 05版：新华智见",
            "#### 06版：各地",
            "#### 07版：成风化人",
            "#### 08版：国际",
        )
    )
    links = "\n".join(
        f"* [第{i}篇文章](http://mrdx.cn/h5/mrdx/content/20260810/Articel{i:02d}002NR.htm)"
        for i in range(1, 9)
    )
    article_blocks = "\n\n".join(
        f"## 独立文章{i}\n" + (f"这是第{i}篇独立稿件的正文内容。" * 90)
        for i in range(1, 5)
    )
    return (
        "公告公示\n\n"
        "| 日 | 一 | 二 | 三 | 四 | 五 | 六 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 9 | 10 | 11 | 12 | 13 | 14 | 15 |\n\n"
        f"{pages}\n\n{links}\n\n{article_blocks}"
    )


def test_natural_mrdx_issue_index_is_listing_and_cannot_reach_standard_selection() -> None:
    title = "新华每日电讯 -微报纸-2026年08月10日"
    record = _record(
        "mrdx-issue-index-pr734",
        url="http://mrdx.cn/h5/mrdx/content/20260810/PageArticleIndexLB.htm?pagetonum=01",
        title=title,
    )
    bundle = _bundle(record.item_id, title=title, body=_issue_body())

    article = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert article.page_surface is PageSurface.LISTING
    assert article.main_content_medium is ContentMedium.UNKNOWN
    assert article.confidence_by_field["page_surface"] == 0.99
    assert article.confidence_by_field["main_content_medium"] == 0.99
    assert any(
        item.evidence_type == "newspaper_issue_listing_surface"
        and item.extractor == SURFACE_VERSION
        for item in article.evidence
    )
    assert not any(item.evidence_type == "medium_resolution" for item in article.evidence)

    assessment = EditorialJudge().assess(_context(), article, bundle)
    assert assessment.verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE
    assert assessment.stage_version == EDITORIAL_JUDGE_VERSION

    policy = evaluate_policy(article, assessment)
    assert policy.provisional_action is PolicyAction.DEFER
    assert policy.reason_code == "insufficient_editorial_evidence"


def test_issue_words_in_a_real_longread_do_not_trigger_listing_without_structure() -> None:
    title = "电子报时代的新闻生产如何改变"
    record = _record(
        "issue-word-negative-pr734",
        url="https://publisher.example/analysis/e-paper-newsrooms",
        title=title,
    )
    body = f"# {title}\n\n" + ("这是围绕数字新闻生产的一篇连续深度分析正文。" * 220)

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.page_surface is PageSurface.ARTICLE_PAGE
    assert article.main_content_medium is ContentMedium.WRITTEN_ARTICLE
    assert not any(
        item.evidence_type == "newspaper_issue_listing_surface"
        for item in article.evidence
    )


def test_multi_heading_article_links_do_not_trigger_listing_without_issue_identity() -> None:
    title = "A comparative analysis of eight newspaper sections"
    record = _record(
        "multi-link-negative-pr734",
        url="https://publisher.example/analysis/eight-sections",
        title=title,
    )
    structure = "\n".join(
        f"#### {i:02d}版：案例\n"
        f"[案例链接](https://archive.example/content/20260810/Article{i:02d}002NR.htm)"
        for i in range(1, 7)
    )
    body = f"# {title}\n\n{structure}\n\n" + ("The analysis compares structure and reporting choices. " * 180)

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.page_surface is PageSurface.ARTICLE_PAGE
    assert article.main_content_medium is ContentMedium.WRITTEN_ARTICLE


def test_index_like_url_alone_does_not_trigger_without_multi_article_structure() -> None:
    title = "Daily briefing article"
    record = _record(
        "path-only-negative-pr734",
        url="https://publisher.example/PageArticleIndex.htm",
        title=title,
    )
    body = f"# {title}\n\n" + ("One continuous reported article body. " * 220)

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.page_surface is PageSurface.ARTICLE_PAGE
    assert article.main_content_medium is ContentMedium.WRITTEN_ARTICLE


def test_pr734_surface_remains_frozen_under_current_pr738_runtime() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.8"
    assert SURFACE_VERSION == "canonical-surface-v0.6-pr7.3.4"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.8"
    assert MEDIUM_VERSION == "canonical-medium-v0.6-pr2"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.7"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.8"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
