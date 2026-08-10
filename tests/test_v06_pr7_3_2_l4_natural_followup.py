from __future__ import annotations

from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    PUBLICATION_VERSION,
    SOURCE_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260810-131135-BJT-zh_midday-pr732-replay",
        group_id="zh_midday",
        scheduled_at_bj="2026-08-10 11:50:00",
        started_at_bj="2026-08-10 13:11:35",
        collector_version="collector-v0.6-pr7.3.2",
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
        source_id="fixture",
        discovery_method="fixture",
    )


def _bundle(
    item_id: str,
    *,
    title: str,
    body: str,
    dates: tuple[str, ...] = (),
) -> AcquisitionBundle:
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        raw_dates=dates,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_bydrug_title_adjacent_absolute_datetime_is_article_local_publication() -> None:
    title = (
        "独家访谈杨永广教授：深耕移植免疫三十载，解析异种移植技术迭代与发展前景"
        "医药新闻-ByDrug-一站式医药资源共享中心-医药魔方"
    )
    article_title = "独家访谈杨永广教授：深耕移植免疫三十载，解析异种移植技术迭代与发展前景"
    original = "https://www.vbdata.cn/1519089165"
    record = _record(
        "bydrug-natural-pr732",
        url="https://bydrug.pharmcube.com/news/detail/4412767c4149e290d91ca8645e681448",
        title=title,
    )
    body = (
        "ByDrug首页 > 医药新闻 > 新闻详情\n\n"
        f"{article_title}\n\n"
        f"2026-08-10 08:00 [查看原文]({original})\n\n"
        + ("异种移植深度访谈正文。" * 220)
    )
    bundle = _bundle(
        record.item_id,
        title=title,
        body=body,
        dates=("2026-08-10 08:00",),
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-10"
    assert result.published_at_confidence == 0.96
    assert result.freshness_facts["publication_evidence_status"] == "resolved"
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "body_header_standalone_datetime"
    assert selected["article_local"] is True
    assert selected["provenance"] == "article_local_metadata"
    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == original


def test_huxiu_wechat_attribution_replaces_host_with_named_original() -> None:
    title = "OpenAI、Anthropic、Meta AI模型安全测试中攻入真实系统，背后是营销剧本"
    original = (
        "https://mp.weixin.qq.com/s?__biz=MzkyNjU2ODM2NQ==&mid=2247631668"
        "&idx=2&sn=0f271329861e08e8504ffae76c66c271"
    )
    record = _record(
        "huxiu-wechat-natural-pr732",
        url="https://www.huxiu.com/article/4881892.html",
        title=title,
    )
    body = (
        f"# {title}\n\n2026-08-10 03:45\n\n"
        f"本文来自微信公众号：[硅星人Pro]({original})，作者：周一笑。\n\n"
        + ("AI安全测试与监管分析正文。" * 180)
        + "\n\n本内容来源于网络，观点仅代表作者本人，不代表虎嗅立场。"
    )
    bundle = _bundle(record.item_id, title=title, body=body)

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == original
    assert result.canonical_source == "硅星人Pro"
    assert result.original_publisher == "硅星人Pro"
    assert any(
        item.evidence_type == "explicit_original_source_link"
        and item.extractor == SOURCE_VERSION
        for item in result.evidence
    )


def test_authorized_huxiu_republish_is_still_external_original_relationship() -> None:
    title = "坦克几乎不用Windows：系统状态可预测性与断电韧性分析"
    original = "https://mp.weixin.qq.com/s/Y9nx1HJL5KWXdOHc0ucyLA"
    record = _record(
        "huxiu-authorized-natural-pr732",
        url="https://www.huxiu.com/article/4881603.html?type=text",
        title=title,
    )
    body = (
        f"# {title}\n\n2026-08-08 00:17\n\n"
        f"本文来自微信公众号：[宇众不同的露萱]({original})，作者：宇众不同的露萱。\n\n"
        + ("操作系统与军工可靠性分析。" * 180)
        + "\n\n本内容由作者授权发布，观点仅代表作者本人，不代表虎嗅立场。"
    )
    bundle = _bundle(record.item_id, title=title, body=body)

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == original
    assert result.original_publisher == "宇众不同的露萱"


def test_title_local_view_original_link_is_source_evidence_without_publisher_label() -> None:
    title = "独家访谈杨永广教授：解析异种移植技术迭代与发展前景"
    original = "https://www.vbdata.cn/1519089165"
    record = _record(
        "bydrug-source-natural-pr732",
        url="https://bydrug.pharmcube.com/news/detail/example",
        title=title,
    )
    body = (
        f"# {title}\n\n"
        f"2026-08-10 08:00 [查看原文]({original})\n\n"
        + ("访谈正文。" * 240)
    )
    bundle = _bundle(record.item_id, title=title, body=body)

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == original
    assert result.original_publisher == "vbdata.cn"


def test_late_reference_named_original_does_not_flip_source_relationship() -> None:
    title = "Independent analysis with a references section"
    record = _record(
        "late-reference-negative-pr732",
        url="https://publisher.example/analysis/1",
        title=title,
    )
    body = (
        f"# {title}\n\nPublished: August 10, 2026\n\n"
        + ("Independent analysis paragraph. " * 220)
        + "\n\nReferences\n[原文](https://research.example/paper/123)\n"
    )
    bundle = _bundle(record.item_id, title=title, body=body)

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.source_action is SourceAction.NONE


def test_pr732_versions_are_l4_only_and_keep_pr72_editorial_frozen() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.2"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.2"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.2"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.2"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
