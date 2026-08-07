import json
from pathlib import Path

import pytest

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
from longread_collector.v06.editorial import EditorialJudge


FIXTURE = Path(__file__).parent / "fixtures" / "v06_editorial_human_labels.json"
ACTIONABLE = {EditorialVerdict.RECOMMEND, EditorialVerdict.CONSIDER}


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260806-195235-BJT-zh_evening",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-06 17:50:00",
        started_at_bj="2026-08-06 19:52:35",
        collector_version="collector-v0.5.6m",
    )


@pytest.fixture(scope="module")
def cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _objects(case):
    article = CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="canonical-article-resolver-v0.6-pr2",
        run_id=_context().run_id,
        item_id=case["id"],
        content_id=f"content-{case['id']}",
        display_url=f"https://fixture.invalid/{case['id']}",
        canonical_content_url=f"https://fixture.invalid/{case['id']}",
        resolved_title=case["title"],
        published_at=case["published_at"],
        published_at_confidence=0.96,
        publisher="fixture-publisher",
        hosting_source="fixture-host",
        canonical_source="fixture-publisher",
        source_relationship=SourceRelationship.ORIGINAL,
        source_action=SourceAction.NONE,
        page_surface=PageSurface(case["page_surface"]),
        main_content_medium=ContentMedium(case["medium"]),
        editorial_genre=EditorialGenre(case["genre"]),
        asset_class=AssetClass(case["asset_class"]),
        freshness_facts={"policy_applied": False},
        confidence_by_field={
            "title": 0.95,
            "publication": 0.96,
            "source": 0.92,
            "page_surface": 0.94,
            "main_content_medium": 0.94,
            "editorial_genre": 0.88,
        },
    )
    sufficient = case.get("sufficient_for_editorial_judgment", True)
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="legacy-adapter-v0.6-pr1",
        run_id=_context().run_id,
        item_id=case["id"],
        status=TechnicalStatus.SUCCESS,
        body_text=case["body"],
        body_markdown=case["body"],
        raw_title=case["title"],
        raw_dates=(case["published_at"],),
        content_length=case["content_chars"],
        prose_length=case["prose_chars"],
        template_length=case["template_chars"],
        video_count=case["video_count"],
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=sufficient,
        sufficient_for_source_chase=not sufficient,
    )
    return article, bundle


def _result(case):
    article, bundle = _objects(case)
    return EditorialJudge().assess(_context(), article, bundle)


@pytest.mark.parametrize(
    "case_id",
    [
        "hello_world_ceuta",
        "turnintl_analysis",
        "turnintl_interview",
        "book_review",
        "legal_commentary",
        "pbc_primary",
        "academic_paper",
        "ideological_commentary",
        "cctv_transcript",
        "shanghai_bookfair_event",
        "training_event",
        "promotional_article",
        "straight_news_brief",
        "market_data_card",
    ],
)
def test_all_scores_are_continuous_and_bounded(cases, case_id):
    case = next(item for item in cases if item["id"] == case_id)
    result = _result(case)
    scores = (
        result.substance_score,
        result.original_reporting_score,
        result.analysis_score,
        result.argument_score,
        result.evidence_density_score,
        result.reader_value_score,
        result.timeliness_relevance_score,
        result.promotional_risk,
        result.event_risk,
        result.transcript_risk,
        result.template_risk,
        result.confidence,
    )
    assert all(0.0 <= score <= 1.0 for score in scores)


def test_human_actionable_cases_remain_actionable(cases):
    for case in cases:
        if case.get("human_actionable") is True:
            result = _result(case)
            assert result.verdict in ACTIONABLE, (case["id"], result)


def test_serious_false_accepts_are_not_actionable(cases):
    serious = [case for case in cases if case["serious_false_accept"]]
    assert serious
    for case in serious:
        result = _result(case)
        assert result.verdict not in ACTIONABLE, (case["id"], result)
        assert result.verdict in {EditorialVerdict.LOW_VALUE, EditorialVerdict.REJECT}


def test_low_value_commentary_is_not_conflated_with_policy_reject(cases):
    case = next(item for item in cases if item["id"] == "ideological_commentary")
    result = _result(case)
    assert result.verdict is EditorialVerdict.LOW_VALUE
    assert result.editorial_value == "low"
    assert result.substance_score >= 0.50
    assert max(
        result.promotional_risk,
        result.event_risk,
        result.transcript_risk,
        result.template_risk,
    ) < 0.60


def test_long_transcript_has_substance_but_high_transcript_risk(cases):
    case = next(item for item in cases if item["id"] == "cctv_transcript")
    result = _result(case)
    assert result.substance_score >= 0.55
    assert result.transcript_risk >= 0.95
    assert result.verdict is EditorialVerdict.REJECT


def test_long_event_preview_has_substance_but_event_risk_dominates(cases):
    case = next(item for item in cases if item["id"] == "shanghai_bookfair_event")
    result = _result(case)
    assert result.substance_score >= 0.50
    assert result.event_risk >= 0.90
    assert result.verdict is EditorialVerdict.REJECT


def test_embedded_video_count_alone_does_not_create_transcript_risk(cases):
    for case_id in ("turnintl_analysis", "turnintl_interview"):
        case = next(item for item in cases if item["id"] == case_id)
        assert case["video_count"] >= 11
        result = _result(case)
        assert result.transcript_risk <= 0.20
        assert result.verdict in ACTIONABLE


def test_primary_and_academic_material_are_not_penalized_for_low_reporting(cases):
    primary = _result(next(item for item in cases if item["id"] == "pbc_primary"))
    academic = _result(next(item for item in cases if item["id"] == "academic_paper"))
    assert primary.original_reporting_score <= 0.25
    assert academic.original_reporting_score <= 0.25
    assert primary.verdict in ACTIONABLE
    assert academic.verdict in ACTIONABLE
    assert academic.timeliness_relevance_score < 0.50


def test_external_link_shell_is_insufficient_evidence_not_low_value(cases):
    case = next(item for item in cases if item["id"] == "external_people_shell")
    result = _result(case)
    assert result.verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE
    assert result.editorial_value == "insufficient_evidence"
    assert result.confidence >= 0.95


def test_human_label_precision_and_recall_clear_pr3_floor(cases):
    judged = [
        case
        for case in cases
        if case.get("human_actionable") is not None
    ]
    predicted_actionable = [
        case for case in judged if _result(case).verdict in ACTIONABLE
    ]
    true_actionable = [
        case for case in judged if case["human_actionable"] is True
    ]
    true_positive = sum(case["human_actionable"] is True for case in predicted_actionable)

    precision = true_positive / len(predicted_actionable)
    recall = true_positive / len(true_actionable)
    serious_false_accepts = sum(
        case["serious_false_accept"] and _result(case).verdict in ACTIONABLE
        for case in judged
    )

    assert precision >= 0.85
    assert recall >= 0.75
    assert serious_false_accepts == 0


def test_evidence_covers_every_score_dimension(cases):
    case = next(item for item in cases if item["id"] == "hello_world_ceuta")
    result = _result(case)
    fields = {item.field for item in result.evidence}
    expected_fields = {
        "substance_score",
        "original_reporting_score",
        "analysis_score",
        "argument_score",
        "evidence_density_score",
        "reader_value_score",
        "timeliness_relevance_score",
        "promotional_risk",
        "event_risk",
        "transcript_risk",
        "template_risk",
        "verdict",
    }
    assert expected_fields <= fields
    assert all(item.source_stage.value == "editorial" for item in result.evidence)


def test_judge_does_not_mutate_inputs(cases):
    case = next(item for item in cases if item["id"] == "hello_world_ceuta")
    article, bundle = _objects(case)
    before_title = article.resolved_title
    before_body = bundle.body_markdown
    EditorialJudge().assess(_context(), article, bundle)
    assert article.resolved_title == before_title
    assert bundle.body_markdown == before_body
