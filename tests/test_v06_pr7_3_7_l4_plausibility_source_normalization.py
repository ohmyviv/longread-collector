from __future__ import annotations

from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    MEDIUM_VERSION,
    PUBLICATION_VERSION,
    SOURCE_VERSION,
    SURFACE_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.canonical.publication_v0737 import resolve_publication
from longread_collector.v06.canonical.source_resolution_v0736 import (
    resolve_source as resolve_source_pr736,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    Evidence,
    RunContext,
    StageName,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION
from longread_collector.v06.shadow.snapshot_persistence_v0735 import (
    SNAPSHOT_PERSISTENCE_VERSION,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260811-183734-BJT-zh_evening-pr737-replay",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-11 17:50:00",
        started_at_bj="2026-08-11 18:37:34",
        collector_version="collector-v0.6-pr7.3.7",
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
        discovery_method="section_scan",
        raw_metadata={},
    )


def _legacy_date_evidence(
    item_id: str,
    *,
    value: str,
    source: str,
    confidence: str = "medium",
    raw: str = "",
) -> Evidence:
    numeric_confidence = {"high": 0.98, "medium": 0.86, "low": 0.58}[confidence]
    return Evidence(
        evidence_id=f"{item_id}-{source}",
        evidence_type="legacy_publication_date_candidate",
        source_stage=StageName.ACQUISITION,
        field="publication_date_candidate",
        value={
            "value": value,
            "source": source,
            "role": "published",
            "confidence": confidence,
            "priority": 70,
            "raw": raw or value,
        },
        confidence=numeric_confidence,
        extractor="legacy-publication-evidence-bridge-v0.6-pr7.3.1",
    )


def _bundle(
    item_id: str,
    *,
    title: str,
    body: str,
    evidence: tuple[Evidence, ...] = (),
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
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
        evidence=evidence,
    )


def test_yicai_future_effective_date_cannot_become_publication_date() -> None:
    title = "推动AI强化安全治理能力，行业标准明确可问责性等八大维度"
    record = _record(
        "yicai-future-effective-date-pr737",
        url="https://www.yicai.com/news/103313675.html",
        title=title,
    )
    evidence = (
        _legacy_date_evidence(
            record.item_id,
            value="2026-11-01T00:00:00+08:00",
            source="discovery_metadata",
            confidence="medium",
            raw="2026-11-01T00:00:00",
        ),
    )
    body = (
        f"# {title}\n\n第一财经\n作者：宋婕 责编：秦新安\n\n"
        "首个面向产业的人工智能风险管理行业标准将于11月1日起正式实施。\n\n"
        "标准在7月获工业和信息化部批准发布，将于2026年11月1日起正式实施。\n\n"
        + ("文章继续解释人工智能风险识别、分级评估和治理要求。" * 140)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body, evidence=evidence)
    )

    assert article.published_at == ""
    assert article.published_at_confidence == 0.0
    assert article.freshness_facts["publication_evidence_status"] == "unknown"
    assert any(
        item.evidence_type == "publication_date_plausibility_guard"
        and "2026-11-01" in str(item.value)
        and item.extractor == PUBLICATION_VERSION
        for item in article.evidence
    )
    assert any(
        row["normalized"] == "2026-11-01" and row["relation"] == "contextual"
        for row in article.freshness_facts["publication_evidence_profile"]
    )


def test_future_article_local_candidate_falls_back_to_plausible_page_metadata() -> None:
    title = "人工智能安全治理标准解读"
    record = _record(
        "future-with-valid-alternative-pr737",
        url="https://publisher.example/story/ai-safety",
        title=title,
    )
    evidence = (
        _legacy_date_evidence(
            record.item_id,
            value="2026-11-01",
            source="body_header_standalone_date",
            confidence="high",
        ),
        _legacy_date_evidence(
            record.item_id,
            value="2026-08-11T09:30:00+08:00",
            source="page_metadata_published",
            confidence="medium",
        ),
    )
    body = (
        f"# {title}\n2026-11-01\n\n"
        "正文说明某项标准将在未来生效，而本文当前已经发布。\n\n"
        + ("连续正文讨论风险治理、标准应用和实施边界。" * 150)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body, evidence=evidence)
    )

    assert article.published_at == "2026-08-11"
    assert article.freshness_facts["published_at_source"] == "page_metadata_published"
    profile = article.freshness_facts["publication_evidence_profile"]
    assert any(row["normalized"] == "2026-11-01" and row["relation"] == "contextual" for row in profile)
    assert any(row["normalized"] == "2026-08-11" and row["relation"] == "selected" for row in profile)


def test_date_only_next_day_keeps_one_day_timezone_boundary_tolerance() -> None:
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="date-only-boundary-pr737",
        discovery_id="discovery-date-only-boundary-pr737",
        url="https://publisher.example/story/timezone-boundary",
        title_hint="Timezone boundary article",
        published_at_hints=("2026-08-12",),
        discovery_method="rss",
        raw_metadata={},
    )
    bundle = _bundle(
        record.item_id,
        title=record.title_hint,
        body="# Timezone boundary article\n\n" + ("Substantive article body. " * 180),
    )

    result = resolve_publication(record, bundle, observed_at_bj="2026-08-11 23:30:00")

    assert result.value == "2026-08-12"
    assert not any(item.evidence_type == "publication_date_plausibility_guard" for item in result.evidence)


def test_markdown_explicit_source_normalizes_to_visible_publisher_only() -> None:
    title = "产业投资的新变化"
    record = _record(
        "china-markdown-source-pr737",
        url="https://mtz.china.com/touzi/2026/0810/256676.html",
        title=title,
    )
    body = (
        f"# {title}\n\n来源：[实况网](http://www.cqtimes.cn/)\n\n"
        + ("这是一篇围绕产业投资与市场变化展开的连续报道正文。" * 150)
    )
    bundle = _bundle(record.item_id, title=title, body=body)
    prior = resolve_source_pr736(
        record,
        bundle,
        resolved_title=title,
        primary_document_hint=False,
        transcript_hint=False,
    )
    article = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert prior.canonical_source == "[实况网](http://www.cqtimes.cn/)"
    assert article.canonical_source == "实况网"
    assert article.original_publisher == "实况网"
    assert article.source_relationship is prior.relationship
    assert article.source_action is prior.action
    assert article.canonical_content_url == prior.canonical_content_url
    assert any(
        item.evidence_type == "explicit_source_identity_normalized"
        and item.value == "实况网"
        and "markdown_link_label" in item.excerpt
        for item in article.evidence
    )


def test_newspaper_issue_suffix_is_removed_from_publisher_identity() -> None:
    title = "在数字时代重新理解公共文化"
    record = _record(
        "sinoss-guangming-source-pr737",
        url="https://www.sinoss.net/c/2026-08-10/666001.shtml",
        title=title,
    )
    body = (
        f"# {title}\n\n来源：《光明日报》（2026年08月10日 13版）\n\n"
        + ("文章围绕公共文化、数字技术和社会参与展开系统讨论。" * 150)
    )
    bundle = _bundle(record.item_id, title=title, body=body)
    prior = resolve_source_pr736(
        record,
        bundle,
        resolved_title=title,
        primary_document_hint=False,
        transcript_hint=False,
    )
    article = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert prior.canonical_source == "《光明日报》（2026年08月10日 13版）"
    assert article.canonical_source == "光明日报"
    assert article.original_publisher == "光明日报"
    assert article.source_relationship is prior.relationship
    assert article.source_action is prior.action
    assert any(
        item.evidence_type == "explicit_source_identity_normalized"
        and item.value == "光明日报"
        and "newspaper_issue_citation" in item.excerpt
        for item in article.evidence
    )


def test_non_issue_parenthetical_publisher_name_is_not_broadly_trimmed() -> None:
    title = "区域经济观察"
    record = _record(
        "publisher-parenthetical-negative-pr737",
        url="https://example.test/story/regional-economy",
        title=title,
    )
    body = (
        f"# {title}\n\n来源：中国经营报（北京版）\n\n"
        + ("文章连续分析区域产业、就业和投资结构变化。" * 160)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.canonical_source == "中国经营报（北京版）"
    assert not any(
        item.evidence_type == "explicit_source_identity_normalized" for item in article.evidence
    )


def test_pr737_versions_change_only_l4_publication_and_source_wrappers() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.7"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.7"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.7"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.7"
    assert SURFACE_VERSION == "canonical-surface-v0.6-pr7.3.4"
    assert SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.5"
    assert MEDIUM_VERSION == "canonical-medium-v0.6-pr2"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
