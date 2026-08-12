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
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION
from longread_collector.v06.shadow.snapshot_persistence_v0738 import (
    SNAPSHOT_PERSISTENCE_VERSION,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260812-184527-BJT-zh_evening-pr739-replay",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-12 17:50:00",
        started_at_bj="2026-08-12 18:45:27",
        collector_version="collector-v0.6-pr7.3.9",
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


def test_jiemian_self_source_survives_long_rendered_header_line() -> None:
    title = "“实时估值”隐秘复活，暗藏开户、会员付费全套生意 | 基市乱象追踪⑩|界面新闻"
    url = "https://www.jiemian.com/article/14880171.html"
    record = _record(
        "jiemian-long-line-self-source-pr739",
        url=url,
        title=title,
        source_name="界面新闻·界面深度",
        source_id="jiemian-depth",
    )
    header_tail = " 图片模板元数据" * 50
    body = (
        "# “实时估值”隐秘复活，暗藏开户、会员付费全套生意 | 基市乱象追踪⑩\n"
        "[杜萌DM](https://a.jiemian.com/index.php?m=user&a=center&id=119674512)_·_ "
        "2026年08月06日 05:07 浏览 8.8w 来源：界面新闻 "
        "![Image](https://img.jiemian.com/example.jpg) 图片来源：界面图库"
        f"{header_tail}\n\n"
        "> 界面新闻记者 | 杜萌\n\n"
        + ("记者持续调查基金实时估值工具、商业合作与监管边界。" * 150)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    # PR-7.3.9 repairs canonical/original relationship semantics. It does not
    # invent a new human-readable hosting mapping when the base has only a domain.
    assert article.hosting_source != title
    assert article.canonical_source == "界面新闻"
    assert article.original_publisher == "界面新闻"
    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert article.source_action is SourceAction.NONE
    assert any(
        item.evidence_type == "self_source_title_metadata"
        and item.value == "界面新闻"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_jiemian_like_external_profile_does_not_trigger_self_source() -> None:
    title = "调查稿标题|界面新闻"
    record = _record(
        "jiemian-external-profile-negative-pr739",
        url="https://www.jiemian.com/article/example.html",
        title=title,
        source_name="界面新闻·界面深度",
        source_id="jiemian-depth",
    )
    body = (
        f"# {title}\n"
        "[外部作者](https://profile.example.org/user/1)_·_ "
        "2026年08月12日 09:00 浏览 2.1w 来源：界面新闻\n\n"
        + ("这是连续完整的调查稿正文。" * 160)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert not any(
        item.evidence_type == "self_source_title_metadata"
        for item in article.evidence
        if item.extractor == SOURCE_VERSION
    )


def test_bjnews_same_line_xinhua_dateline_and_markdown_source_is_wire() -> None:
    title = "何为对外贸易国家安全调查？为何说调查产品与国家安全利益密切相关？专家解读 — 新京报"
    url = "https://www.bjnews.com.cn/detail/1786024638129401.html"
    record = _record(
        "bjnews-xinhua-natural-pr739",
        url=url,
        title=title,
        source_name="新京报·深度",
        source_id="bjnews-depth",
    )
    body = (
        "# 何为对外贸易国家安全调查？为何说调查产品与国家安全利益密切相关？专家解读\n"
        "2026-08-06 21:58  据新华社北京8月6日电 商务部日前对美国系列涉华消极措施实施多项反制举措，"
        "其中一项为对相关进口打印复印办公设备发起对外贸易国家安全调查。\n\n"
        + ("相关专家接受新华社记者采访并解释制度背景与法律边界。" * 90)
        + "\n\n编辑 刘佳妮\n_来源：新华社_\n"
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    # Hosting can remain a machine domain if no stronger hosting identity was
    # carried into L4; the wire/original publisher facts are the acceptance target.
    assert article.hosting_source not in {"新华社", "新华网"}
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


def test_direct_xinhua_same_line_dateline_stays_original() -> None:
    title = "权威部门回应经济运行热点问题"
    record = _record(
        "direct-xinhua-same-line-negative-pr739",
        url="https://www.news.cn/politics/20260812/example.htm",
        title=title,
        source_name="新华社",
        source_id="xinhua",
    )
    body = (
        f"# {title}\n2026-08-12 09:15 新华社北京8月12日电 "
        "记者从有关部门获悉，相关政策将继续稳步推进。\n\n"
        + ("新华社记者进一步采访了有关部门和行业专家。" * 100)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.source_relationship is SourceRelationship.ORIGINAL
    assert article.source_action is SourceAction.NONE
    assert not any(
        item.evidence_type == "agency_dateline_evidence"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_mid_body_xinhua_dateline_does_not_become_wire() -> None:
    title = "国际传播案例中的来源识别"
    record = _record(
        "midbody-xinhua-negative-pr739",
        url="https://publisher.example/analysis/source",
        title=title,
    )
    body = (
        f"# {title}\n\n"
        + ("这是由记者独立采访形成的连续分析正文。" * 100)
        + "\n\n据新华社北京8月6日电，此前有关部门曾公开回应。\n"
        + ("文章随后继续展开独立采访和分析。" * 80)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.source_relationship is not SourceRelationship.WIRE_REPUBLISH
    assert not any(
        item.evidence_type == "agency_dateline_evidence"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_sina_external_official_account_article_replaces_title_fallback() -> None:
    title = "透视数据看清中国经济大逻辑——对话国家发展改革委宏观经济研究院院长黄汉权"
    url = "https://news.sina.com.cn/zx/gj/2026-08-12/doc-inimzivu5395205.shtml"
    original_url = "http://www.ce.cn/xwzx/gnsz/gdxw/202608/t20260812_3142319.shtml"
    record = _record("sina-ce-natural-pr739", url=url, title=title)
    body = (
        f"# {title}\n"
        "2026年08月12日 00:05 作者\n"
        f"[中国经济网]({original_url}) 中国经济网官方账号\n\n"
        "看懂当下的中国经济，既要观察宏观数据，也要把握微观感受。\n\n"
        + ("黄汉权围绕经济形势、结构、格局和政策展开系统分析。" * 170)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.hosting_source == "news.sina.com.cn"
    assert article.canonical_source == "中国经济网"
    assert article.original_publisher == "中国经济网"
    assert article.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert article.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert article.canonical_content_url == original_url
    assert article.canonical_source != title
    assert any(
        item.evidence_type == "external_official_account_source"
        and item.value == "中国经济网"
        and item.extractor == SOURCE_VERSION
        for item in article.evidence
    )


def test_external_link_without_official_account_cue_is_not_promoted() -> None:
    title = "国家经济治理访谈：结构变化与政策选择"
    record = _record(
        "external-link-without-account-negative-pr739",
        url="https://news.example.com/story/1",
        title=title,
    )
    body = (
        f"# {title}\n"
        "2026年08月12日 10:00\n"
        "[中国经济网](http://www.ce.cn/xwzx/example.shtml) 相关资料\n\n"
        + ("这是一篇独立采访和分析文章。" * 170)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert not any(
        item.evidence_type == "external_official_account_source"
        for item in article.evidence
    )


def test_same_host_official_account_link_is_not_external_original() -> None:
    title = "国家产业政策观察"
    url = "https://news.example.com/story/2"
    record = _record("same-host-account-negative-pr739", url=url, title=title)
    body = (
        f"# {title}\n"
        "2026年08月12日 10:00\n"
        "[本站财经](https://news.example.com/story/original) 本站财经官方账号\n\n"
        + ("这是本站内部栏目之间的普通关联。" * 170)
    )

    article = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title=title, body=body)
    )

    assert article.source_action is not SourceAction.REPLACE_WITH_ORIGINAL
    assert not any(
        item.evidence_type == "external_official_account_source"
        for item in article.evidence
    )


def test_pr739_changes_source_service_runtime_only() -> None:
    from longread_collector.v06.shadow.pipeline import (
        LEGACY_CONTROL_VERSION,
        PARALLEL_SHADOW_PIPELINE_VERSION,
    )

    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.9"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3.9"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.9"
    assert SNAPSHOT_PERSISTENCE_VERSION == "snapshot-persistence-v0.6-pr7.3.8"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.7"
    assert SURFACE_VERSION == "canonical-surface-v0.6-pr7.3.4"
    assert MEDIUM_VERSION == "canonical-medium-v0.6-pr2"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
    assert LEGACY_CONTROL_VERSION == "collector-v0.5.6m"
