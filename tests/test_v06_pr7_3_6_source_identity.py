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
    DiscoveryRecord,
    SourceAction,
    SourceRelationship,
    RunContext,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION
from longread_collector.v06.shadow.snapshot_persistence_v0735 import (
    SNAPSHOT_PERSISTENCE_VERSION,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260811-125504-BJT-zh_midday-pr736-replay",
        group_id="zh_midday",
        scheduled_at_bj="2026-08-11 11:50:00",
        started_at_bj="2026-08-11 12:55:04",
        collector_version="collector-v0.6-pr7.3.6",
    )


def _record(
    item_id: str,
    *,
    url: str,
    title: str,
    source_name: str = "",
    source_id: str = "",
) -> DiscoveryRecord:
    metadata = {}
    if source_name:
        metadata["source_name"] = source_name
    if source_id:
        metadata["source_id"] = source_id
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        title_hint=title,
        source_id=source_id,
        discovery_method="section_scan" if source_id else "firecrawl_search",
        raw_metadata=metadata,
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


def test_bjnews_registered_source_replaces_institution_like_title_fallback() -> None:
    title = "国家科技伦理委员会委员翟晓梅：女童基因编辑悲剧中伦理为何失守"
    record = _record(
        "bjnews-interview-pr736",
        url="https://www.bjnews.com.cn/detail/1785892533169279.html",
        title=title,
        source_name="新京报·深度",
        source_id="bjnews-depth",
    )
    body = (
        f"# {title}\n\n"
        "在接受新京报专访时，翟晓梅教授再次强调，坚守科研伦理是开展探索性人体试验不容突破的底线。\n\n"
        + ("这是围绕科研伦理、临床研究和受试者保护的连续访谈正文。" * 120)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source == "新京报·深度"
    assert article.canonical_source == "新京报·深度"
    assert article.original_publisher == "新京报·深度"
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert article.source_action is SourceAction.NONE
    assert article.canonical_source != title
    assert any(
        item.evidence_type == "registered_hosting_source"
        and item.value == "新京报·深度"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_lnd_source_label_stops_before_author_and_editor_metadata() -> None:
    title = "让人工智能赋能千行百业-新闻-北国网"
    record = _record(
        "lnd-source-boundary-pr736",
        url="http://news.lnd.com.cn/system/2026/08/11/030570160.shtml",
        title=title,
    )
    body = (
        "[首页](http://www.lnd.com.cn/)\n\n"
        "让人工智能赋能千行百业\n"
        "理论│2026-08-11 08:01 来源：辽宁日报 作者： 编辑：栾溪\n\n"
        "本报记者 宋东泽 张瑜\n\n"
        + ("人工智能是推动产业升级、经济转型的重要战略引擎。" * 140)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.canonical_source == "辽宁日报"
    assert article.original_publisher == "辽宁日报"
    assert "作者" not in article.canonical_source
    assert "编辑" not in article.canonical_source
    assert article.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert article.source_action is SourceAction.RETAIN_CURRENT_DISPLAY_URL
    assert any(
        item.evidence_type == "explicit_source_label_boundary"
        and item.value == "辽宁日报"
        for item in article.evidence
    )


def test_bjnews_strict_xinhua_lead_dateline_is_wire_republish() -> None:
    title = "何为对外贸易国家安全调查？为何说调查产品与国家安全利益密切相关？专家解读"
    url = "https://www.bjnews.com.cn/detail/1786024638129401.html"
    record = _record(
        "bjnews-xinhua-pr736",
        url=url,
        title=title,
        source_name="新京报·深度",
        source_id="bjnews-depth",
    )
    body = (
        f"# {title}\n\n"
        "据新华社北京8月6日电 商务部日前对美国系列涉华消极措施实施多项反制举措，"
        "其中一项为对相关进口打印复印办公设备发起对外贸易国家安全调查。\n\n"
        + ("相关专家接受新华社记者采访并解释制度背景与法律边界。" * 100)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source == "新京报·深度"
    assert article.canonical_source == "新华社"
    assert article.original_publisher == "新华社"
    assert article.source_relationship is SourceRelationship.WIRE_REPUBLISH
    assert article.source_action is SourceAction.FIND_ORIGINAL_ARTICLE
    assert article.canonical_content_url == url
    assert any(
        item.evidence_type == "agency_dateline_evidence"
        and item.value == "新华社"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_direct_xinhua_page_with_same_dateline_remains_original() -> None:
    title = "权威部门回应经济运行热点问题"
    record = _record(
        "xinhua-direct-negative-pr736",
        url="https://www.news.cn/politics/20260811/example.htm",
        title=title,
        source_name="新华社",
        source_id="xinhua",
    )
    body = (
        f"# {title}\n\n"
        "新华社北京8月11日电 记者从有关部门获悉，相关政策将继续稳步推进。\n\n"
        + ("新华社记者进一步采访了相关部门和行业专家。" * 100)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    # The guard is about relationship semantics, not a new global mapping from
    # official domains to human publisher labels. Preserve the prior host identity.
    assert article.hosting_source == "news.cn"
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert article.source_action is SourceAction.NONE
    assert not any(
        item.evidence_type == "agency_dateline_evidence" for item in article.evidence
    )


def test_mid_body_xinhua_mention_does_not_trigger_agency_relationship() -> None:
    title = "国家治理案例中的信息来源与传播路径"
    record = _record(
        "xinhua-midbody-negative-pr736",
        url="https://www.bjnews.com.cn/detail/1786000000000000.html",
        title=title,
        source_name="新京报·深度",
        source_id="bjnews-depth",
    )
    body = (
        f"# {title}\n\n"
        + ("这是一篇由记者独立采访形成的连续分析正文。" * 90)
        + "\n\n根据新华社此前报道，相关部门曾公开回应这一问题。\n"
        + ("文章随后继续展开独立采访和分析。" * 80)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source == "新京报·深度"
    assert article.canonical_source == "新京报·深度"
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert not any(
        item.evidence_type == "agency_dateline_evidence" for item in article.evidence
    )


def test_institution_like_title_without_registered_source_keeps_prior_behavior() -> None:
    title = "国家数据治理委员会年度观察：制度如何演化"
    record = _record(
        "unregistered-title-negative-pr736",
        url="https://publisher.example/analysis/governance",
        title=title,
    )
    body = f"# {title}\n\n" + ("独立分析正文持续展开制度与实践之间的关系。" * 160)

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.canonical_source == title
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert not any(
        item.evidence_type == "registered_hosting_source" for item in article.evidence
    )


def test_normal_publisher_label_is_not_truncated_without_metadata_label() -> None:
    title = "地方产业升级进入新阶段"
    record = _record(
        "publisher-label-negative-pr736",
        url="https://example.test/story/1",
        title=title,
    )
    body = (
        f"# {title}\n\n2026-08-11 08:30 来源：辽宁日报社评论部\n\n"
        + ("这是一篇连续完整的评论与分析正文。" * 140)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.canonical_source == "辽宁日报社评论部"
    assert article.original_publisher == "辽宁日报社评论部"


def test_pr736_versions_change_source_only_and_preserve_other_layers() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.6"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.6"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.6"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.3"
    assert SURFACE_VERSION == "canonical-surface-v0.6-pr7.3.4"
    assert SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.5"
    assert MEDIUM_VERSION == "canonical-medium-v0.6-pr2"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
