from __future__ import annotations

from dataclasses import replace

from longread_collector.v06.canonical import CanonicalArticleResolver
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    DiscoveryRecord,
    EditorialAssessment,
    EditorialGenre,
    EditorialVerdict,
    PageSurface,
    PolicyAction,
    RunContext,
    SelectionTrack,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EditorialJudge
from longread_collector.v06.selection import PolicyPortfolioSelector, SelectionCandidate


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260808-124058-BJT-zh_midday",
        group_id="zh_midday",
        scheduled_at_bj="2026-08-08 11:50:00",
        started_at_bj="2026-08-08 12:40:20",
        collector_version="collector-v0.6-pr7",
    )


def _record(
    *,
    item_id: str,
    title: str,
    body_date_hint: str = "",
    resolved_date: str = "",
    resolved_source: str = "",
    body_evidence: dict | None = None,
) -> DiscoveryRecord:
    freshness = {}
    if resolved_date:
        freshness.update(
            {
                "published_at_resolved": resolved_date,
                "published_at_source": resolved_source,
                "published_at_confidence": "high",
            }
        )
    if body_evidence:
        freshness["body_publication_evidence"] = body_evidence
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=f"https://fixture.invalid/{item_id}",
        title_hint=title,
        published_at_hints=(body_date_hint,) if body_date_hint else (),
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata={"freshness": freshness},
    )


def _bundle(item_id: str, title: str, body: str, raw_dates=()) -> AcquisitionBundle:
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        raw_dates=tuple(raw_dates),
        content_length=len(body),
        prose_length=len("".join(body.split())),
        template_length=0,
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_article_local_date_beats_stale_template_timestamp():
    title = "AI模型如何改变科学发现"
    record = _record(
        item_id="local-over-template",
        title=title,
        body_date_hint="2026-08-06",
        resolved_date="Sat, 12 Oct 2024 05:36:22 GMT",
        resolved_source="page_meta_timestamp",
    )
    bundle = _bundle(
        record.item_id,
        title,
        f"# {title}\n发布时间：2026-08-06\n记者采访多位研究人员，分析模型能力与局限。",
        raw_dates=("Sat, 12 Oct 2024 05:36:22 GMT",),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.published_at == "2026-08-06"
    assert result.published_at_confidence >= 0.90
    assert result.freshness_facts["publication_conflict"] is False
    assert result.freshness_facts["resolved_freshness_age_days"] == 2


def test_conflicting_article_local_dates_are_explicit_and_low_confidence():
    title = "一篇存在日期冲突的报道"
    record = _record(
        item_id="local-conflict",
        title=title,
        body_evidence={
            "value": "2026-08-05",
            "source": "body_header_chinese_byline_date",
            "confidence": "high",
            "raw": "日期：2026-08-05",
        },
    )
    bundle = _bundle(
        record.item_id,
        title,
        f"# {title}\n发布时间：2026-08-07\n正文。",
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.freshness_facts["publication_conflict"] is True
    assert set(result.freshness_facts["publication_conflict_values"]) == {
        "2026-08-05",
        "2026-08-07",
    }
    assert result.published_at_confidence <= 0.45


def test_english_created_date_is_parsed_as_article_local_publication():
    title = "A Guided Walkthrough"
    record = _record(item_id="english-created", title=title)
    bundle = _bundle(
        record.item_id,
        title,
        f"# {title}\nCreated in July 14, 2023 by author\nLong technical essay.",
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.published_at == "2023-07-14"
    assert result.freshness_facts["resolved_freshness_age_days"] > 1000


def _article(
    item_id: str,
    *,
    published_at: str,
    genre: EditorialGenre = EditorialGenre.ANALYSIS,
    medium: ContentMedium = ContentMedium.WRITTEN_ARTICLE,
    asset_class: AssetClass = AssetClass.MEDIA_ARTICLE,
    conflict: bool = False,
) -> CanonicalArticle:
    return CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        content_id=f"content-{item_id}",
        display_url=f"https://fixture.invalid/{item_id}",
        canonical_content_url=f"https://fixture.invalid/{item_id}",
        resolved_title=f"深度报道 {item_id}",
        published_at=published_at,
        published_at_confidence=0.96 if published_at else 0.0,
        publisher="fixture",
        hosting_source="fixture",
        canonical_source="fixture",
        source_relationship=SourceRelationship.ORIGINAL,
        source_action=SourceAction.NONE,
        page_surface=PageSurface.ARTICLE_PAGE,
        main_content_medium=medium,
        editorial_genre=genre,
        asset_class=asset_class,
        freshness_facts={"publication_conflict": conflict, "policy_applied": False},
        confidence_by_field={
            "title": 0.95,
            "publication": 0.96 if published_at else 0.0,
            "source": 0.92,
            "page_surface": 0.94,
            "main_content_medium": 0.94,
            "editorial_genre": 0.90,
        },
    )


def test_navigation_and_footer_event_words_do_not_poison_reported_article():
    article = _article("main-content-risk", published_at="2026-08-08")
    title = article.resolved_title
    nav = ("活动 论坛 峰会 发布会 打造 赋能 助力 成果展示 " * 8) + "\n"
    core = (
        "记者采访了六家企业和三位研究人员。根据调查，60家企业中有42家已经部署AI。"
        "受访者表示，成本下降与组织流程重构同时发生。文章进一步分析营销、销售和内部运营为何率先落地，"
        "并比较制造、金融和医疗行业的差异。数据显示，2025年至2026年部署周期从12个月缩短到5个月。"
        "然而，模型可靠性、数据治理和员工培训仍是主要瓶颈。值得注意的是，不同行业的投资回报差异明显。\n"
    ) * 10
    footer = "\n相关阅读\n" + ("活动 论坛 峰会 报名 优惠 推介会 成果展示 " * 10)
    bundle = _bundle(article.item_id, title, nav + title + "\n" + core + footer)
    result = EditorialJudge().assess(_context(), article, bundle)
    assert result.promotional_risk < 0.55
    assert result.event_risk < 0.55
    assert result.verdict in {EditorialVerdict.RECOMMEND, EditorialVerdict.CONSIDER}


def test_intrinsic_event_recap_remains_rejected_after_calibration():
    article = _article(
        "intrinsic-event",
        published_at="2026-08-08",
        genre=EditorialGenre.EVENT_RECAP,
    )
    body = "活动成功举办。论坛开幕式上，多位嘉宾致辞，随后举行成果展示和签约仪式。" * 50
    result = EditorialJudge().assess(
        _context(), article, _bundle(article.item_id, article.resolved_title, body)
    )
    assert result.event_risk >= 0.90
    assert result.verdict is EditorialVerdict.REJECT


def _assessment(item_id: str, *, deep: bool = False) -> EditorialAssessment:
    if deep:
        values = dict(
            substance_score=0.95,
            original_reporting_score=0.88,
            analysis_score=0.92,
            argument_score=0.88,
            evidence_density_score=0.92,
            reader_value_score=0.94,
        )
    else:
        values = dict(
            substance_score=0.78,
            original_reporting_score=0.72,
            analysis_score=0.74,
            argument_score=0.68,
            evidence_density_score=0.76,
            reader_value_score=0.78,
        )
    return EditorialAssessment(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        timeliness_relevance_score=0.86,
        promotional_risk=0.05,
        event_risk=0.05,
        transcript_risk=0.05,
        template_risk=0.05,
        editorial_value="high",
        verdict=EditorialVerdict.RECOMMEND,
        confidence=0.95,
        **values,
    )


def _candidate(article: CanonicalArticle, *, deep: bool = False) -> SelectionCandidate:
    return SelectionCandidate(article=article, assessment=_assessment(article.item_id, deep=deep))


def test_known_stale_standard_longread_cannot_be_saved_by_high_utility():
    article = _article("stale-standard", published_at="2026-02-23")
    result = PolicyPortfolioSelector().select(
        _context(), [_candidate(article, deep=True)], max_selected=1
    )
    decision = result.decisions[0]
    assert decision.policy_action is PolicyAction.REJECT
    assert decision.selected is False
    assert decision.reason_code == "standard_longread_stale_over_14d"


def test_unknown_or_conflicting_standard_date_is_deferred_not_neutral_selected():
    unknown = _article("unknown-date", published_at="")
    conflict = _article("conflict-date", published_at="2026-08-07", conflict=True)
    result = PolicyPortfolioSelector().select(
        _context(), [_candidate(unknown), _candidate(conflict)], max_selected=2
    )
    decisions = {item.item_id: item for item in result.decisions}
    assert decisions["unknown-date"].policy_action is PolicyAction.DEFER
    assert decisions["conflict-date"].policy_action is PolicyAction.DEFER
    assert not result.selected_item_ids


def test_old_academic_material_stays_on_separate_special_track():
    article = _article(
        "old-academic",
        published_at="2026-07-10",
        medium=ContentMedium.ACADEMIC_PAPER,
        asset_class=AssetClass.ACADEMIC_PAPER,
    )
    result = PolicyPortfolioSelector().select(
        _context(), [_candidate(article, deep=True)], max_selected=1
    )
    decision = result.decisions[0]
    assert decision.policy_action is PolicyAction.SELECT_SPECIAL
    assert decision.selection_track is SelectionTrack.ACADEMIC
    assert decision.selected is True


def test_8_14_day_deep_read_exception_is_quality_gated_and_capped_at_two():
    timely = _candidate(_article("timely", published_at="2026-08-07"))
    deep_candidates = [
        _candidate(_article(f"deep-{index}", published_at="2026-07-30"), deep=True)
        for index in range(3)
    ]
    low_quality = _candidate(_article("deep-low", published_at="2026-07-30"), deep=False)
    result = PolicyPortfolioSelector().select(
        _context(), [timely, *deep_candidates, low_quality], max_selected=4
    )
    decisions = {item.item_id: item for item in result.decisions}
    selected_deep = [item_id for item_id in result.selected_item_ids if item_id.startswith("deep-")]
    assert len(selected_deep) <= 2
    assert decisions["deep-low"].policy_action is PolicyAction.REJECT
    assert decisions["deep-low"].reason_code == "deep_read_8_14d_quality_floor_not_met"
    capped = [
        item for item in deep_candidates
        if decisions[item.article.item_id].reason_code == "deep_read_exception_daily_cap"
    ]
    assert len(capped) == 1
