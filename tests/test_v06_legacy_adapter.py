from copy import deepcopy

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.v06.contracts import (
    ContentMedium,
    EditorialVerdict,
    PageSurface,
    PolicyAction,
    RunContext,
    SelectionTrack,
    SourceAction,
    SourceRelationship,
    StageEventType,
)
from longread_collector.v06.legacy.adapter import LegacyV056mAdapter


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260806-195235-BJT-zh_evening",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-06 17:50:00",
        started_at_bj="2026-08-06 19:52:35",
        collector_version="collector-v0.5.6m",
    )


def _formal_pair() -> tuple[DiscoveredURL, ExtractedArticle]:
    discovered = DiscoveredURL(
        url="https://example.com/story?utm_source=x",
        title="A substantial reported feature",
        description="Description",
        published_at="2026-08-06T12:00:00+08:00",
        discovery_method="native_rss",
        query_or_source="source-1",
        rank=2,
        rank_score=88.0,
        metadata={
            "source_id": "source-1",
            "selection": {
                "selection_status": "accepted_for_extraction",
                "selection_phase": "first_stage",
                "selected_order": 3,
                "score_components": {
                    "article_confidence": 4,
                    "freshness": 3,
                },
            },
        },
    )
    article = ExtractedArticle(
        article_id="article-1",
        url=discovered.url,
        url_canonical="https://example.com/story",
        domain="example.com",
        title=discovered.title,
        author="Reporter",
        published_at="2026-08-06T12:00:00+08:00",
        canonical_source="Example News",
        hosting_source="Example News",
        source_relationship="original",
        page_role="standalone_content",
        page_type="article",
        content_type="reported_feature",
        candidate_disposition="formal_candidate",
        source_action="none",
        classification_confidence="high",
        classification_version="collector-v0.5.6m",
        classification_reason="legacy_formal",
        extractor_used="direct_html",
        extraction_status="success",
        verification_level="A",
        content_markdown="# Story\n\n" + "Body paragraph. " * 200,
        content_chars=3200,
        content_sha256="content-sha",
        eligible_for_editor=True,
        metadata={
            "valid_article_body": True,
            "content_metrics": {
                "body_prose_chars": 3000,
                "template_chars": 120,
                "image_count": 2,
                "video_count": 1,
            },
            "freshness": {
                "published_at_confidence": "high",
                "freshness_age_days": 0,
            },
        },
        extraction_attempts=[
            {
                "extractor": "jina",
                "success": False,
                "body_chars": 0,
                "error_type": "TimeoutError",
                "request_sent": True,
            },
            {
                "extractor": "direct_html",
                "success": True,
                "body_chars": 3200,
                "prose_chars": 3000,
                "latency_ms": 410,
                "request_sent": True,
            },
        ],
    )
    return discovered, article


def test_adapter_is_lossless_and_does_not_mutate_legacy_inputs() -> None:
    discovered, article = _formal_pair()
    discovery_before = deepcopy(discovered.metadata)
    article_before = deepcopy(article.metadata)
    attempts_before = deepcopy(article.extraction_attempts)

    result = LegacyV056mAdapter().adapt_item(
        context=_context(),
        discovered=discovered,
        article=article,
    )

    assert discovered.metadata == discovery_before
    assert article.metadata == article_before
    assert article.extraction_attempts == attempts_before
    assert result.discovery.title_hint == discovered.title
    assert result.gate.reason_code == "first_stage"
    assert result.acquisition.best_attempt_id.endswith("direct_html")
    assert result.acquisition.sufficient_for_editorial_judgment is True
    assert result.canonical.page_surface is PageSurface.ARTICLE_PAGE
    assert result.canonical.main_content_medium is ContentMedium.WRITTEN_ARTICLE
    assert result.canonical.source_relationship is SourceRelationship.ORIGINAL
    assert result.canonical.source_action is SourceAction.NONE
    assert result.editorial.editorial_value == "legacy_unscored"
    assert result.editorial.verdict is EditorialVerdict.RECOMMEND
    assert result.selection.policy_action is PolicyAction.SELECT_STANDARD
    assert result.selection.selection_track is SelectionTrack.STANDARD_LONGREAD
    assert result.selection.selection_rank == 3
    assert result.projection.candidate_disposition == "formal_candidate"
    assert result.projection.eligible_for_editor is True

    types = [event.event_type for event in result.events]
    assert types == [
        StageEventType.DISCOVERY_RESULT,
        StageEventType.GATE_RESULT,
        StageEventType.EXTRACTOR_ATTEMPT,
        StageEventType.EXTRACTOR_ATTEMPT,
        StageEventType.ACQUISITION_RESULT,
        StageEventType.CANONICAL_RESULT,
        StageEventType.EDITORIAL_RESULT,
        StageEventType.SELECTION_RESULT,
        StageEventType.PROJECTION_RESULT,
    ]
    for previous, current in zip(result.events, result.events[1:]):
        assert current.parent_event_id == previous.event_id


def test_original_source_required_maps_to_action_not_reject() -> None:
    discovered, article = _formal_pair()
    article.candidate_disposition = "original_source_required"
    article.eligible_for_editor = False
    article.reject_reason = ""
    article.source_action = "find_original_article"
    article.page_role = "discovery_lead"
    article.extraction_status = "rejected"

    result = LegacyV056mAdapter().adapt_item(
        context=_context(),
        discovered=discovered,
        article=article,
    )

    assert result.canonical.page_surface is PageSurface.EXTERNAL_LINK_STUB
    assert result.canonical.source_action is SourceAction.FIND_ORIGINAL_ARTICLE
    assert result.editorial.verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE
    assert result.selection.policy_action is PolicyAction.SOURCE_CHASE
    assert result.selection.selection_track is SelectionTrack.SOURCE_CHASE
    assert result.projection.candidate_disposition == "original_source_required"
