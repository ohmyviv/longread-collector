from __future__ import annotations

from longread_collector.v06.contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    EditorialGenre,
    EditorialVerdict,
    PageSurface,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial.service_v071 import EditorialJudge as PR71EditorialJudge
from longread_collector.v06.editorial.service_v072 import EditorialJudge as PR72EditorialJudge


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260809-041344-BJT-pre_report",
        group_id="pre_report",
        scheduled_at_bj="2026-08-09 03:57:00",
        started_at_bj="2026-08-09 04:13:44",
        collector_version="collector-v0.6-pr7.2",
        max_acquisition_attempts=32,
        firecrawl_daily_limit=3,
    )


def _article(
    item_id: str,
    title: str,
    *,
    genre: EditorialGenre = EditorialGenre.REPORTED_FEATURE,
) -> CanonicalArticle:
    return CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        content_id=f"content-{item_id}",
        display_url=f"https://example.com/{item_id}",
        canonical_content_url=f"https://example.com/{item_id}",
        resolved_title=title,
        published_at="2026-08-08",
        published_at_confidence=0.96,
        publisher="Example",
        hosting_source="Example",
        canonical_source="Example",
        source_relationship=SourceRelationship.ORIGINAL,
        source_action=SourceAction.NONE,
        page_surface=PageSurface.ARTICLE_PAGE,
        main_content_medium=ContentMedium.WRITTEN_ARTICLE,
        editorial_genre=genre,
        asset_class=AssetClass.MEDIA_ARTICLE,
        freshness_facts={"publication_conflict": False, "resolved_freshness_age_days": 1},
        confidence_by_field={
            "title": 0.95,
            "publication": 0.96,
            "source": 0.92,
            "page_surface": 0.94,
            "main_content_medium": 0.94,
            "editorial_genre": 0.88,
        },
    )


def _bundle(
    article: CanonicalArticle,
    body: str,
    *,
    template_length: int = 0,
) -> AcquisitionBundle:
    prose = len("".join(body.split()))
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=article.item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=article.resolved_title,
        raw_dates=("2026-08-08",),
        content_length=len(body),
        prose_length=prose,
        template_length=template_length,
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def _rich_english_body(title: str) -> str:
    paragraph = (
        "According to researchers and public records, the shift did not happen for one simple reason. "
        "A historian told me that policy, market structure, and risk aversion reinforced one another over time. "
        "However, survey data and industry documents suggest that consumers often prefer more variety than suppliers offer. "
        "The evidence matters because the market can become self-reinforcing: fewer choices create less information about demand. "
        "A 2024 survey of 1.2 million products found a 60 percent difference across categories, and a "
        "[public dataset](https://example.com/data) documents the trend. “The market is narrower than preference,” one expert said. "
        "In contrast, several case studies show that people respond positively when they are given credible alternatives. "
        "The broader implication is that an apparent preference may actually reflect institutional constraints rather than stable taste."
    )
    return f"# {title}\n\n" + "\n\n".join(paragraph for _ in range(14))


def test_midrange_template_contamination_is_recovered_for_substantive_longread() -> None:
    title = "The Color Recession May Be Permanent"
    article = _article("atlantic-template", title, genre=EditorialGenre.ANALYSIS)
    body = _rich_english_body(title)
    prose = len("".join(body.split()))
    template_length = int(prose * 2.35)
    bundle = _bundle(article, body, template_length=template_length)

    before = PR71EditorialJudge().assess(_context(), article, bundle)
    after = PR72EditorialJudge().assess(_context(), article, bundle)

    assert 0.25 <= before.template_risk <= 0.55
    assert after.template_risk <= 0.22
    assert after.template_risk < before.template_risk
    assert after.verdict in {EditorialVerdict.RECOMMEND, EditorialVerdict.CONSIDER}
    assert any(item.evidence_type == "editorial_template_recovery" for item in after.evidence)


def test_moderate_template_recovery_does_not_rescue_short_low_depth_page() -> None:
    title = "Short update"
    article = _article("short-template", title)
    body = (
        f"# {title}\n\n"
        "Officials said the meeting happened Tuesday. The city announced a change after the meeting. "
        "The statement confirmed the new schedule. "
    ) * 8
    prose = len("".join(body.split()))
    bundle = _bundle(article, body, template_length=int(prose * 2.35))

    result = PR72EditorialJudge().assess(_context(), article, bundle)

    assert result.template_risk > 0.22
    assert not any(item.evidence_type == "editorial_template_recovery" for item in result.evidence)


def test_self_identified_multi_story_newsletter_is_rejected() -> None:
    title = "Crab Odyssey"
    article = _article("roundup", title)
    body = f"""# {title}

Welcome to The Abstract, a special edition covering several new studies.
In this edition, here are the studies that caught our attention.

## A crab in a bottle
Researchers described a crab that survived for months at sea. According to the study, algae supplied food.

## Radioactive boars
Another study examined contamination in wild boars and reported a different environmental mechanism.

## Early snakes
In other news, researchers published a paper about the evolution of early snakes.

## A stellar explosion
Next up, astronomers reported a separate paper about a binary-star supernova.
""" * 5
    result = PR72EditorialJudge().assess(_context(), article, _bundle(article, body))

    assert result.verdict is EditorialVerdict.REJECT
    assert any(
        item.field == "format_guard_reason"
        and item.value == "english_roundup_self_identified_multi_story"
        for item in result.evidence
    )


def test_single_newsletter_mention_does_not_trigger_roundup_guard() -> None:
    title = "Why Long-Form Reporting Still Matters"
    article = _article("newsletter-mention", title)
    paragraph = (
        "A newsletter can distribute a reported feature, but the delivery format does not determine the depth of the work. "
        "According to editors I interviewed, the important distinction is whether one argument is developed with evidence. "
        "However, the economics of publishing also matter because subscription incentives shape commissioning decisions. "
        "The evidence from several publications suggests that sustained reporting and analysis can coexist with direct distribution."
    )
    body = f"# {title}\n\n" + "\n\n".join(paragraph for _ in range(15))
    result = PR72EditorialJudge().assess(_context(), article, _bundle(article, body))

    assert result.verdict is not EditorialVerdict.REJECT
    assert not any(item.field == "format_guard_reason" for item in result.evidence)


def test_short_low_depth_reported_feature_fallback_is_rejected() -> None:
    title = "City Moves Meetings Online After Threats"
    article = _article("short-news", title)
    paragraph = (
        "The city council announced that its public meeting will now be held online after officials said they received threats. "
        "According to a statement, the change follows an earlier meeting where a person was arrested. "
        "Officials confirmed the schedule and said the town hall format would remain virtual for now."
    )
    body = f"# {title}\n\n" + "\n\n".join(paragraph for _ in range(8))
    result = PR72EditorialJudge().assess(_context(), article, _bundle(article, body))

    assert result.verdict is EditorialVerdict.REJECT
    assert any(
        item.field == "format_guard_reason"
        and item.value == "short_low_depth_news_update"
        for item in result.evidence
    )


def test_concise_investigation_is_exempt_from_short_news_fallback_guard() -> None:
    title = "Leaked Guide Shows How Police Hide Surveillance"
    article = _article("concise-investigation", title, genre=EditorialGenre.INVESTIGATION)
    paragraph = (
        "Internal documents obtained by reporters show how a vendor instructed police departments to describe surveillance use. "
        "According to records and interviews, the guidance conflicted with public statements. "
        "The investigation compares the leaked material with procurement files and testimony from officials."
    )
    body = f"# {title}\n\n" + "\n\n".join(paragraph for _ in range(8))
    result = PR72EditorialJudge().assess(_context(), article, _bundle(article, body))

    assert not any(
        item.field == "format_guard_reason"
        and item.value == "short_low_depth_news_update"
        for item in result.evidence
    )


def test_runtime_version_advances_without_changing_pr72_l5_or_control_authority() -> None:
    from longread_collector.v06.editorial.service_v072 import EDITORIAL_JUDGE_VERSION
    from longread_collector.v06.shadow.pipeline import (
        LEGACY_CONTROL_VERSION,
        PARALLEL_SHADOW_PIPELINE_VERSION,
    )

    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.9"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
    assert LEGACY_CONTROL_VERSION == "collector-v0.5.6m"
