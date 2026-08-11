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
        run_id="COL-20260810-185046-BJT-zh_evening-pr733-replay",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-10 17:50:00",
        started_at_bj="2026-08-10 18:50:46",
        collector_version="collector-v0.6-pr7.3.3",
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
        source_id="jiemian-depth",
        discovery_method="section_scan",
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


def test_jiemian_chinese_byline_datetime_resolves_publication_and_self_source() -> None:
    title = "“实时估值”隐秘复活，暗藏开户、会员付费全套生意 | 基市乱象追踪⑩|界面新闻"
    article_title = "“实时估值”隐秘复活，暗藏开户、会员付费全套生意 | 基市乱象追踪⑩"
    url = "https://www.jiemian.com/article/14880171.html"
    record = _record("jiemian-14880171-pr733", url=url, title=title)
    body = (
        f"正在阅读:\n\n{article_title}\n\n"
        f"# {article_title}\n\n"
        "经过半年的‘隐蔽’运营，一些非持牌机构已经完成商业闭环。\n\n"
        "[杜萌DM](https://a.jiemian.com/index.php?m=user&a=center&id=119674512)"
        "_·_ 2026年08月06日 05:07 浏览 8.7w 来源：界面新闻\n\n"
        "> 界面新闻记者 | 杜萌\n\n"
        + ("界面新闻记者调查发现，相关平台仍在提供实时估值服务。" * 120)
        + "\n\n[未经正式授权严禁转载本文，侵权必究。](https://www.jiemian.com/about/copyright.html)"
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert result.published_at == "2026-08-06"
    assert result.published_at_confidence == 0.97
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "body_header_byline_datetime"
    assert selected["article_local"] is True
    assert selected["provenance"] == "article_local_metadata"

    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.source_action is SourceAction.NONE
    assert result.canonical_content_url == url
    assert result.canonical_source == "界面新闻"
    assert result.original_publisher == "界面新闻"
    assert any(
        item.evidence_type == "self_source_title_metadata"
        and item.extractor == SOURCE_VERSION
        for item in result.evidence
    )


def test_jiemian_slash_byline_datetime_resolves_same_template() -> None:
    title = "【深度】长鑫上市浮盈万亿，“合肥经验”的真正内核是什么？|界面新闻"
    article_title = "【深度】长鑫上市浮盈万亿，“合肥经验”的真正内核是什么？"
    url = "https://www.jiemian.com/article/14887907.html"
    record = _record("jiemian-14887907-pr733", url=url, title=title)
    body = (
        f"# {article_title}\n\n"
        "分析人士指出，真正值得学习的是判断程序和制度建设。\n\n"
        "[王珍WZ](https://a.jiemian.com/index.php?m=user&a=center&id=120553280)"
        "_·_ 2026/08/07 09:34 浏览 12w 来源：界面新闻\n\n"
        "> **记者 王珍**\n\n"
        + ("中国金融四十人研究院相关人士对界面新闻表示，制度建设更重要。" * 120)
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert result.published_at == "2026-08-07"
    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.source_action is SourceAction.NONE
    assert result.canonical_source == "界面新闻"


def test_external_source_matching_title_brand_without_sibling_profile_stays_secondary() -> None:
    title = "Aggregator report|新华社"
    url = "https://aggregator.example/article/1"
    record = _record("external-source-negative-pr733", url=url, title=title)
    body = (
        "# Aggregator report\n\n"
        "[本站编辑](https://aggregator.example/authors/1) · "
        "2026年08月10日 10:00 浏览 1.2w 来源：新华社\n\n"
        + ("转载内容。" * 180)
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert result.published_at == "2026-08-10"
    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.RETAIN_CURRENT_DISPLAY_URL
    assert result.canonical_source == "新华社"
    assert not any(
        item.evidence_type == "self_source_title_metadata" for item in result.evidence
    )


def test_timezone_bearing_byline_datetime_is_not_lexically_promoted() -> None:
    title = "Timezone-bearing byline|Example Publisher"
    url = "https://example.test/article/2"
    record = _record("timezone-byline-negative-pr733", url=url, title=title)
    body = (
        "# Timezone-bearing byline\n\n"
        "[Author](https://a.example.test/authors/1) · "
        "2026-08-10 17:30Z 浏览 1w 来源：Example Publisher\n\n"
        + ("Independent article body. " * 180)
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert result.published_at != "2026-08-10"
    assert not any(
        item.evidence_type == "legacy_publication_date_candidate"
        and isinstance(item.value, dict)
        and item.value.get("source") == "body_header_byline_datetime"
        for item in result.evidence
    )


def test_distant_byline_metadata_does_not_reopen_body_wide_date_scan() -> None:
    title = "Independent analysis|Example Publisher"
    url = "https://example.test/article/1"
    record = _record("distant-metadata-negative-pr733", url=url, title=title)
    body = (
        "# Independent analysis\n\n"
        + ("Independent long-form analysis paragraph. " * 180)
        + "\n\n[Author](https://a.example.test/authors/1) · "
        "2026年08月10日 10:00 浏览 1w 来源：Example Publisher\n"
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert result.published_at == ""
    assert result.freshness_facts["publication_evidence_status"] in {
        "unknown",
        "non_publication_only",
    }


def test_current_pr736_keeps_pr733_publication_and_pr72_editorial_frozen() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.6"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.3"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.6"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.6"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
