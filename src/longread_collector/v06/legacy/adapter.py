"""Lossless v0.5.6m-to-v0.6 compatibility adapter.

The adapter is deliberately conservative. It preserves legacy facts and terminal
state, emits a complete StageEvent stream, and leaves new semantic scoring to
later v0.6 phases.

This module is not imported by :mod:`longread_collector.v06`; callers must opt
in through :mod:`longread_collector.v06.legacy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ...models import DiscoveredURL, ExtractedArticle
from ...normalization import canonicalize_url, stable_id
from ...operational_audit_v056 import classify_firecrawl_attempt
from ..audit.events import make_stage_event
from ..audit.metrics import (
    LegacySummaryComparison,
    StageEventMetrics,
    compare_legacy_summary,
    summarize_stage_events,
)
from ..contracts import (
    AcquisitionAttempt,
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    DiscoveryRecord,
    EditorialAssessment,
    EditorialGenre,
    EditorialVerdict,
    Evidence,
    FinalProjection,
    FlowStatus,
    GateAction,
    GateDecision,
    PageSurface,
    PolicyAction,
    RunContext,
    SelectionDecision,
    SelectionTrack,
    SourceAction,
    SourceRelationship,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)

LEGACY_ADAPTER_VERSION = "v06-legacy-v056m-adapter-v1"
CONTRACT_SCHEMA_VERSION = "v06-contracts-v1"
_STAGE_VERSIONS = {
    StageName.DISCOVERY: "legacy-v056m-discovery-projection-v1",
    StageName.ACQUISITION_GATE: "legacy-v056m-gate-projection-v1",
    StageName.ACQUISITION: "legacy-v056m-acquisition-projection-v1",
    StageName.CANONICAL: "legacy-v056m-canonical-projection-v1",
    StageName.EDITORIAL: "legacy-v056m-editorial-projection-v1",
    StageName.SELECTION: "legacy-v056m-selection-projection-v1",
    StageName.PROJECTION: "legacy-v056m-final-projection-v1",
}

_PAGE_SURFACES = {
    "article": PageSurface.ARTICLE_PAGE,
    "event_news": PageSurface.ARTICLE_PAGE,
    "video_program_page": PageSurface.ARTICLE_PAGE,
    "document": PageSurface.DOCUMENT_PAGE,
    "pdf": PageSurface.DOCUMENT_PAGE,
    "homepage": PageSurface.HOMEPAGE,
    "channel_or_listing": PageSurface.LISTING,
    "search_or_tag": PageSurface.LISTING,
    "listing": PageSurface.LISTING,
    "login_or_auth": PageSurface.LOGIN,
    "login": PageSurface.LOGIN,
    "blocked_or_captcha": PageSurface.CAPTCHA,
    "captcha": PageSurface.CAPTCHA,
    "social_or_ugc": PageSurface.SOCIAL_POST,
    "paywall": PageSurface.PAYWALL,
}
_CONTENT_MEDIA = {
    "academic_paper": ContentMedium.ACADEMIC_PAPER,
    "primary_document": ContentMedium.PRIMARY_DOCUMENT,
    "government_primary_document": ContentMedium.PRIMARY_DOCUMENT,
    "regulatory_guidance": ContentMedium.PRIMARY_DOCUMENT,
    "television_transcript": ContentMedium.TELEVISION_TRANSCRIPT,
    "program_transcript": ContentMedium.TELEVISION_TRANSCRIPT,
    "video_program_page": ContentMedium.VIDEO_PAGE,
    "podcast_transcript": ContentMedium.PODCAST_TRANSCRIPT,
    "photo_essay": ContentMedium.PHOTO_ESSAY,
    "market_data": ContentMedium.DATA_CARD,
    "stock_data": ContentMedium.DATA_CARD,
    "data_card": ContentMedium.DATA_CARD,
    "event_listing": ContentMedium.EVENT_LISTING,
}
_EDITORIAL_GENRES = {
    "investigation": EditorialGenre.INVESTIGATION,
    "reported_investigative_followup": EditorialGenre.INVESTIGATION,
    "reported_feature": EditorialGenre.REPORTED_FEATURE,
    "reported_longread": EditorialGenre.REPORTED_FEATURE,
    "government_feature": EditorialGenre.REPORTED_FEATURE,
    "analysis_or_commentary": EditorialGenre.ANALYSIS,
    "analysis": EditorialGenre.ANALYSIS,
    "commentary": EditorialGenre.COMMENTARY,
    "interview_or_speech": EditorialGenre.INTERVIEW,
    "interview": EditorialGenre.INTERVIEW,
    "book_review": EditorialGenre.BOOK_REVIEW,
    "primary_document": EditorialGenre.POLICY_DOCUMENT,
    "government_primary_document": EditorialGenre.POLICY_DOCUMENT,
    "regulatory_guidance": EditorialGenre.POLICY_DOCUMENT,
    "institutional_report": EditorialGenre.INSTITUTIONAL_REPORT,
    "event_preview": EditorialGenre.EVENT_PREVIEW,
    "event_listing": EditorialGenre.EVENT_PREVIEW,
    "event_news": EditorialGenre.EVENT_RECAP,
    "event_recap": EditorialGenre.EVENT_RECAP,
    "training_event_recap": EditorialGenre.EVENT_RECAP,
    "promotional_content": EditorialGenre.PROMOTION,
    "promotion": EditorialGenre.PROMOTION,
    "short_news": EditorialGenre.STRAIGHT_NEWS,
    "straight_news": EditorialGenre.STRAIGHT_NEWS,
    "market_data": EditorialGenre.MARKET_DATA,
    "stock_data": EditorialGenre.MARKET_DATA,
    "data_card": EditorialGenre.MARKET_DATA,
}
_SOURCE_RELATIONSHIPS = {
    "original": SourceRelationship.ORIGINAL,
    "translated_republish": SourceRelationship.TRANSLATED_REPUBLISH,
    "wire_republish": SourceRelationship.WIRE_REPUBLISH,
    "secondary_republish": SourceRelationship.SECONDARY_REPUBLISH,
}
_SOURCE_ACTIONS = {
    "none": SourceAction.NONE,
    "retain_with_source_label": SourceAction.RETAIN_CURRENT_DISPLAY_URL,
    "retain_current_display_url": SourceAction.RETAIN_CURRENT_DISPLAY_URL,
    "find_original_article": SourceAction.FIND_ORIGINAL_ARTICLE,
    "find_primary_document": SourceAction.FIND_PRIMARY_DOCUMENT,
    "replace_with_original_source": SourceAction.REPLACE_WITH_ORIGINAL,
    "replace_with_original": SourceAction.REPLACE_WITH_ORIGINAL,
}


@dataclass(frozen=True, slots=True)
class LegacyAdaptedItem:
    discovery: DiscoveryRecord
    gate: GateDecision
    acquisition: AcquisitionBundle
    canonical: CanonicalArticle
    editorial: EditorialAssessment
    selection: SelectionDecision
    projection: FinalProjection
    events: tuple[StageEvent, ...]


@dataclass(frozen=True, slots=True)
class LegacyAdaptedRun:
    context: RunContext
    items: tuple[LegacyAdaptedItem, ...]
    events: tuple[StageEvent, ...]
    metrics: StageEventMetrics
    legacy_summary_comparison: LegacySummaryComparison | None = None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    return int(_number(value, float(default)))


def _unique(*values: Any) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        candidates = (
            value
            if isinstance(value, (list, tuple, set, frozenset))
            else (value,)
        )
        for candidate in candidates:
            normalized = _text(candidate)
            if normalized and normalized not in result:
                result.append(normalized)
    return tuple(result)


def _confidence(value: Any) -> float:
    normalized = _text(value).lower()
    if normalized in {"high", "a", "verified"}:
        return 0.9
    if normalized in {"medium", "b"}:
        return 0.6
    if normalized in {"low", "c"}:
        return 0.3
    if normalized == "d":
        return 0.1
    numeric = _number(value, -1.0)
    return max(0.0, min(numeric, 1.0)) if numeric >= 0 else 0.0


def _evidence(item_id: str, stage: StageName, field: str, value: Any) -> Evidence:
    evidence_id = stable_id(
        f"{item_id}|{stage.value}|{field}|{value}",
        length=16,
    )
    return Evidence(
        evidence_id=f"legacy-{evidence_id}",
        evidence_type="legacy_compatibility_projection",
        source_stage=stage,
        field=field,
        value=value,
        confidence=1.0,
    )


def _attempt_outcome(attempt: Mapping[str, Any]) -> tuple[bool, str]:
    extractor = _text(attempt.get("extractor")).lower()
    if extractor == "firecrawl":
        outcome = classify_firecrawl_attempt(dict(attempt))
        return outcome in {"request_succeeded", "request_failed"}, outcome
    request_sent = bool(attempt.get("request_sent", True))
    if not request_sent:
        return False, _text(attempt.get("request_outcome")) or "skipped_not_sent"
    if _text(attempt.get("request_outcome")):
        return True, _text(attempt.get("request_outcome"))
    if attempt.get("error_type") or attempt.get("error_message"):
        return True, "request_failed"
    if bool(attempt.get("success")) or _integer(attempt.get("body_chars")) > 0:
        return True, "request_succeeded"
    return True, "request_failed"


def _adapt_attempt(
    item_id: str,
    attempt: Mapping[str, Any],
    ordinal: int,
) -> AcquisitionAttempt:
    extractor = _text(attempt.get("extractor")) or "unknown"
    request_sent, outcome = _attempt_outcome(attempt)
    status = (
        TechnicalStatus.SKIPPED
        if not request_sent or outcome.startswith("skipped_")
        else TechnicalStatus.SUCCESS
        if outcome == "request_succeeded"
        else TechnicalStatus.FAILED
        if outcome == "request_failed"
        else TechnicalStatus.PARTIAL
    )
    return AcquisitionAttempt(
        attempt_id=f"{item_id}-attempt-{ordinal:02d}-{extractor.lower()}",
        extractor=extractor,
        status=status,
        request_sent=request_sent,
        started_at_bj=_text(
            attempt.get("started_at_bj") or attempt.get("attempted_at_bj")
        ),
        completed_at_bj=_text(attempt.get("completed_at_bj")),
        body_chars=_integer(attempt.get("body_chars")),
        prose_chars=_integer(
            attempt.get("prose_chars") or attempt.get("body_chars")
        ),
        credits_used=_number(attempt.get("credits_used")),
        latency_ms=_integer(
            attempt.get("latency_ms")
            or attempt.get("duration_ms")
            or attempt.get("elapsed_ms")
        ),
        reason_code=outcome,
        error_type=_text(attempt.get("error_type")),
        evidence=(
            _evidence(
                item_id,
                StageName.ACQUISITION,
                f"attempt[{ordinal}]",
                outcome,
            ),
        ),
    )


def _page_surface(article: ExtractedArticle) -> PageSurface:
    if _text(article.page_role).lower() == "discovery_lead" or _text(
        article.source_action
    ).lower() in {"find_original_article", "find_primary_document"}:
        return PageSurface.EXTERNAL_LINK_STUB
    return _PAGE_SURFACES.get(
        _text(article.page_type).lower(),
        PageSurface.UNKNOWN,
    )


def _medium(article: ExtractedArticle) -> ContentMedium:
    content_type = _text(article.content_type).lower()
    if content_type in _CONTENT_MEDIA:
        return _CONTENT_MEDIA[content_type]
    return (
        ContentMedium.WRITTEN_ARTICLE
        if _text(article.page_type).lower() == "article"
        else ContentMedium.UNKNOWN
    )


def _asset_class(
    medium: ContentMedium,
    genre: EditorialGenre,
) -> AssetClass:
    if medium is ContentMedium.PRIMARY_DOCUMENT:
        return AssetClass.PRIMARY_DOCUMENT
    if medium is ContentMedium.ACADEMIC_PAPER:
        return AssetClass.ACADEMIC_PAPER
    if medium in {
        ContentMedium.TELEVISION_TRANSCRIPT,
        ContentMedium.PODCAST_TRANSCRIPT,
    }:
        return AssetClass.TRANSCRIPT
    if medium is ContentMedium.DATA_CARD:
        return AssetClass.DATA_PRODUCT
    if genre is EditorialGenre.INSTITUTIONAL_REPORT:
        return AssetClass.INSTITUTIONAL_REPORT
    if medium in {
        ContentMedium.WRITTEN_ARTICLE,
        ContentMedium.VIDEO_PAGE,
        ContentMedium.PHOTO_ESSAY,
    }:
        return AssetClass.MEDIA_ARTICLE
    return AssetClass.UNKNOWN


def _legacy_policy(
    disposition: str,
    content_type: str,
) -> tuple[EditorialVerdict, PolicyAction, SelectionTrack, bool]:
    if disposition == "formal_candidate":
        return (
            EditorialVerdict.RECOMMEND,
            PolicyAction.SELECT_STANDARD,
            SelectionTrack.STANDARD_LONGREAD,
            True,
        )
    if disposition == "special_candidate":
        track = (
            SelectionTrack.ACADEMIC
            if "academic" in content_type.lower()
            else SelectionTrack.SPECIAL_DOCUMENT
        )
        return (
            EditorialVerdict.CONSIDER,
            PolicyAction.SELECT_SPECIAL,
            track,
            True,
        )
    if disposition == "original_source_required":
        return (
            EditorialVerdict.INSUFFICIENT_EVIDENCE,
            PolicyAction.SOURCE_CHASE,
            SelectionTrack.SOURCE_CHASE,
            False,
        )
    return (
        EditorialVerdict.REJECT,
        PolicyAction.REJECT,
        SelectionTrack.NONE,
        False,
    )


def _policy_flow(action: PolicyAction) -> FlowStatus:
    if action in {PolicyAction.SELECT_STANDARD, PolicyAction.SELECT_SPECIAL}:
        return FlowStatus.PASS
    if action is PolicyAction.SOURCE_CHASE:
        return FlowStatus.ACTION_REQUIRED
    if action is PolicyAction.DEFER:
        return FlowStatus.DEFER
    return FlowStatus.REJECT


class LegacyV056mAdapter:
    """Project frozen legacy objects into v0.6 contracts without mutation."""

    def adapt_item(
        self,
        *,
        context: RunContext,
        discovered: DiscoveredURL,
        article: ExtractedArticle,
        created_at_bj: str = "",
    ) -> LegacyAdaptedItem:
        item_id = _text(article.article_id) or stable_id(
            canonicalize_url(discovered.url)
        )
        created = created_at_bj or context.started_at_bj
        selection_meta = discovered.metadata.get("selection", {})
        selection_meta = (
            selection_meta if isinstance(selection_meta, Mapping) else {}
        )
        score_components = selection_meta.get("score_components", {})
        score_components = (
            score_components if isinstance(score_components, Mapping) else {}
        )
        priority_features = {
            str(key): _number(value)
            for key, value in score_components.items()
            if isinstance(value, (str, int, float))
        }
        if discovered.rank_score:
            priority_features["discovery_rank_score"] = float(
                discovered.rank_score
            )

        discovery = DiscoveryRecord(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.DISCOVERY],
            run_id=context.run_id,
            item_id=item_id,
            discovery_id=f"legacy-discovery-{item_id}",
            url=discovered.url,
            canonical_url_hint=canonicalize_url(discovered.url),
            title_hint=discovered.title,
            description_hint=discovered.description,
            published_at_hints=_unique(discovered.published_at),
            source_id=(
                _text(discovered.metadata.get("source_id"))
                or discovered.query_or_source
            ),
            discovery_method=discovered.discovery_method,
            query_or_section=discovered.query_or_source,
            rank=discovered.rank,
            route_status=TechnicalStatus.SUCCESS,
            external_link_hint=_text(
                discovered.metadata.get("external_link")
            ),
            raw_metadata=discovered.metadata,
            evidence=(
                _evidence(
                    item_id,
                    StageName.DISCOVERY,
                    "discovery_method",
                    discovered.discovery_method,
                ),
            ),
        )
        gate_reason = (
            _text(selection_meta.get("selection_phase"))
            or _text(selection_meta.get("selection_status"))
            or "legacy_selected_for_extraction"
        )
        gate = GateDecision(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.ACQUISITION_GATE],
            run_id=context.run_id,
            item_id=item_id,
            action=GateAction.ACQUIRE,
            reason_code=gate_reason,
            confidence=1.0,
            priority_features=priority_features,
            evidence=(
                _evidence(
                    item_id,
                    StageName.ACQUISITION_GATE,
                    "selection",
                    dict(selection_meta),
                ),
            ),
        )

        attempts = tuple(
            _adapt_attempt(
                item_id,
                raw if isinstance(raw, Mapping) else {},
                ordinal,
            )
            for ordinal, raw in enumerate(
                article.extraction_attempts,
                start=1,
            )
        )
        best_attempt_id = next(
            (
                attempt.attempt_id
                for attempt in attempts
                if attempt.extractor.lower()
                == _text(article.extractor_used).lower()
                and attempt.status is TechnicalStatus.SUCCESS
            ),
            next(
                (
                    attempt.attempt_id
                    for attempt in attempts
                    if attempt.status is TechnicalStatus.SUCCESS
                ),
                "",
            ),
        )
        content_metrics = article.metadata.get("content_metrics", {})
        content_metrics = (
            content_metrics if isinstance(content_metrics, Mapping) else {}
        )
        extraction_status = _text(article.extraction_status).lower()
        technical_status = (
            TechnicalStatus.SUCCESS
            if extraction_status == "success"
            else TechnicalStatus.FAILED
            if extraction_status == "failed"
            else TechnicalStatus.PARTIAL
        )
        valid_body = article.metadata.get("valid_article_body")
        if valid_body is None:
            valid_body = extraction_status == "success" and bool(
                article.content_markdown
            )
        acquisition = AcquisitionBundle(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.ACQUISITION],
            run_id=context.run_id,
            item_id=item_id,
            status=technical_status,
            attempts=attempts,
            best_attempt_id=best_attempt_id,
            body_text=article.content_markdown,
            body_markdown=article.content_markdown,
            raw_title=article.title,
            raw_author=article.author,
            raw_dates=_unique(article.published_at, discovered.published_at),
            raw_canonical_links=_unique(
                article.url_canonical,
                article.original_url,
            ),
            outbound_links=_unique(article.original_url),
            content_length=len(article.content_markdown),
            prose_length=_integer(
                content_metrics.get("body_prose_chars")
                or article.metadata.get("prose_chars")
                or article.content_chars
                or len(article.content_markdown)
            ),
            template_length=_integer(
                content_metrics.get("template_chars")
            ),
            image_count=_integer(content_metrics.get("image_count")),
            video_count=_integer(content_metrics.get("video_count")),
            sufficient_for_canonicalization=bool(
                article.title or article.content_markdown
            ),
            sufficient_for_editorial_judgment=(
                extraction_status == "success" and bool(valid_body)
            ),
            sufficient_for_source_chase=(
                article.candidate_disposition == "original_source_required"
                or _text(article.source_action).lower()
                in {"find_original_article", "find_primary_document"}
            ),
            total_cost=sum(attempt.credits_used for attempt in attempts),
            total_latency_ms=(
                _integer(article.metadata.get("total_latency_ms"))
                or sum(attempt.latency_ms for attempt in attempts)
            ),
            evidence=(
                _evidence(
                    item_id,
                    StageName.ACQUISITION,
                    "extraction_status",
                    extraction_status,
                ),
            ),
        )

        freshness = article.metadata.get("freshness", {})
        freshness = freshness if isinstance(freshness, Mapping) else {}
        medium = _medium(article)
        genre = _EDITORIAL_GENRES.get(
            _text(article.content_type).lower(),
            EditorialGenre.UNKNOWN,
        )
        relationship = _SOURCE_RELATIONSHIPS.get(
            _text(article.source_relationship).lower(),
            SourceRelationship.UNCERTAIN,
        )
        source_action = _SOURCE_ACTIONS.get(
            _text(article.source_action).lower(),
            SourceAction.NONE,
        )
        publication_confidence = _confidence(
            freshness.get("published_at_confidence")
        )
        canonical = CanonicalArticle(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.CANONICAL],
            run_id=context.run_id,
            item_id=item_id,
            content_id=article.content_sha256 or item_id,
            display_url=article.url or discovered.url,
            canonical_content_url=(
                article.original_url or article.url_canonical
            ),
            resolved_title=article.title or discovered.title,
            resolved_author=article.author,
            published_at=article.published_at or discovered.published_at,
            published_at_confidence=publication_confidence,
            publisher=(
                article.original_publisher
                or article.canonical_source
                or article.hosting_source
            ),
            hosting_source=article.hosting_source or article.domain,
            canonical_source=article.canonical_source,
            original_publisher=article.original_publisher,
            source_relationship=relationship,
            source_action=source_action,
            page_surface=_page_surface(article),
            main_content_medium=medium,
            editorial_genre=genre,
            asset_class=_asset_class(medium, genre),
            duplicate_cluster_id=article.content_cluster_id,
            freshness_facts=freshness,
            confidence_by_field={
                "classification": _confidence(
                    article.classification_confidence
                ),
                "publication": publication_confidence,
                "source_relationship": (
                    0.9
                    if relationship is not SourceRelationship.UNCERTAIN
                    else 0.2
                ),
            },
            evidence=(
                _evidence(
                    item_id,
                    StageName.CANONICAL,
                    "legacy_identity",
                    {
                        "page_type": article.page_type,
                        "content_type": article.content_type,
                        "source_relationship": article.source_relationship,
                        "source_action": article.source_action,
                    },
                ),
            ),
        )

        disposition = _text(article.candidate_disposition) or "reject"
        verdict, policy_action, track, selected = _legacy_policy(
            disposition,
            article.content_type,
        )
        editorial = EditorialAssessment(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.EDITORIAL],
            run_id=context.run_id,
            item_id=item_id,
            substance_score=0.0,
            original_reporting_score=0.0,
            analysis_score=0.0,
            argument_score=0.0,
            evidence_density_score=0.0,
            reader_value_score=0.0,
            timeliness_relevance_score=0.0,
            promotional_risk=0.0,
            event_risk=0.0,
            transcript_risk=0.0,
            template_risk=0.0,
            editorial_value="legacy_unscored",
            verdict=verdict,
            confidence=_confidence(article.classification_confidence),
            evidence=(
                _evidence(
                    item_id,
                    StageName.EDITORIAL,
                    "candidate_disposition",
                    disposition,
                ),
            ),
        )
        selected_order = (
            _integer(
                selection_meta.get("selected_order")
                or selection_meta.get("actual_extraction_order")
            )
            or None
        )
        selection = SelectionDecision(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=_STAGE_VERSIONS[StageName.SELECTION],
            run_id=context.run_id,
            item_id=item_id,
            policy_action=policy_action,
            selection_track=track,
            selected=selected,
            selection_rank=selected_order if selected else None,
            reason_code=(
                article.reject_reason
                or article.classification_reason
                or disposition
            ),
            evidence=(
                _evidence(
                    item_id,
                    StageName.SELECTION,
                    "legacy_selection",
                    disposition,
                ),
            ),
        )
        projection = FinalProjection(
            schema_version=CONTRACT_SCHEMA_VERSION,
            projector_version=_STAGE_VERSIONS[StageName.PROJECTION],
            run_id=context.run_id,
            item_id=item_id,
            candidate_disposition=disposition,
            eligible_for_editor=bool(article.eligible_for_editor),
            reject_reason=article.reject_reason,
            canonical_source=article.canonical_source,
            source_action=article.source_action,
            selection_track=track.value,
            evidence=(
                _evidence(
                    item_id,
                    StageName.PROJECTION,
                    "terminal_state",
                    {
                        "candidate_disposition": disposition,
                        "eligible_for_editor": bool(
                            article.eligible_for_editor
                        ),
                        "reject_reason": article.reject_reason,
                    },
                ),
            ),
        )

        events: list[StageEvent] = []
        parent_id = ""

        def emit(
            stage: StageName,
            event_type: StageEventType,
            technical: TechnicalStatus,
            flow: FlowStatus,
            reason: str,
            attributes: Mapping[str, Any],
            evidence: tuple[Evidence, ...],
            *,
            ordinal: int = 0,
            cost: float = 0.0,
            event_created_at: str = "",
        ) -> StageEvent:
            nonlocal parent_id
            event = make_stage_event(
                run_id=context.run_id,
                item_id=item_id,
                stage=stage,
                event_type=event_type,
                stage_version=_STAGE_VERSIONS[stage],
                technical_status=technical,
                flow_status=flow,
                reason_code=reason,
                created_at_bj=event_created_at or created,
                parent_event_id=parent_id,
                ordinal=ordinal,
                cost=cost,
                attributes=attributes,
                evidence=evidence,
            )
            events.append(event)
            parent_id = event.event_id
            return event

        emit(
            StageName.DISCOVERY,
            StageEventType.DISCOVERY_RESULT,
            discovery.route_status,
            FlowStatus.PASS,
            "legacy_discovery_projected",
            {
                "url": discovery.url,
                "discovery_method": discovery.discovery_method,
                "rank": discovery.rank,
            },
            discovery.evidence,
        )
        emit(
            StageName.ACQUISITION_GATE,
            StageEventType.GATE_RESULT,
            TechnicalStatus.SUCCESS,
            FlowStatus.PASS,
            gate.reason_code,
            {
                "action": gate.action.value,
                "selected_order": selected_order,
            },
            gate.evidence,
        )
        for ordinal, attempt in enumerate(attempts, start=1):
            outcome = attempt.reason_code
            emit(
                StageName.ACQUISITION,
                StageEventType.EXTRACTOR_ATTEMPT,
                attempt.status,
                (
                    FlowStatus.PASS
                    if attempt.status is TechnicalStatus.SUCCESS
                    else FlowStatus.DEFER
                    if attempt.status is TechnicalStatus.SKIPPED
                    else FlowStatus.ERROR
                ),
                outcome,
                {
                    "attempt_id": attempt.attempt_id,
                    "extractor": attempt.extractor.lower(),
                    "request_sent": attempt.request_sent,
                    "request_outcome": outcome,
                    "body_chars": attempt.body_chars,
                    "prose_chars": attempt.prose_chars,
                    "credits_used": attempt.credits_used,
                    "latency_ms": attempt.latency_ms,
                    "error_type": attempt.error_type,
                },
                attempt.evidence,
                ordinal=ordinal,
                cost=attempt.credits_used,
                event_created_at=attempt.started_at_bj,
            )
        emit(
            StageName.ACQUISITION,
            StageEventType.ACQUISITION_RESULT,
            acquisition.status,
            (
                FlowStatus.PASS
                if acquisition.status is TechnicalStatus.SUCCESS
                else FlowStatus.ERROR
                if acquisition.status is TechnicalStatus.FAILED
                else FlowStatus.REJECT
            ),
            extraction_status or "legacy_acquisition_projected",
            {
                "extraction_status": extraction_status,
                "best_extractor": article.extractor_used,
                "best_attempt_id": acquisition.best_attempt_id,
                "sufficient_for_canonicalization": (
                    acquisition.sufficient_for_canonicalization
                ),
                "sufficient_for_editorial_judgment": (
                    acquisition.sufficient_for_editorial_judgment
                ),
                "sufficient_for_source_chase": (
                    acquisition.sufficient_for_source_chase
                ),
            },
            acquisition.evidence,
        )
        emit(
            StageName.CANONICAL,
            StageEventType.CANONICAL_RESULT,
            TechnicalStatus.SUCCESS,
            (
                FlowStatus.ACTION_REQUIRED
                if policy_action is PolicyAction.SOURCE_CHASE
                else FlowStatus.PASS
            ),
            "legacy_canonical_projected",
            {
                "page_surface": canonical.page_surface.value,
                "main_content_medium": canonical.main_content_medium.value,
                "editorial_genre": canonical.editorial_genre.value,
                "source_relationship": canonical.source_relationship.value,
                "source_action": canonical.source_action.value,
                "legacy_page_type": article.page_type,
                "legacy_content_type": article.content_type,
            },
            canonical.evidence,
        )
        emit(
            StageName.EDITORIAL,
            StageEventType.EDITORIAL_RESULT,
            TechnicalStatus.SUCCESS,
            (
                FlowStatus.REJECT
                if verdict is EditorialVerdict.REJECT
                else FlowStatus.ACTION_REQUIRED
                if verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE
                else FlowStatus.PASS
            ),
            "legacy_unscored_compatibility_projection",
            {
                "editorial_value": editorial.editorial_value,
                "verdict": editorial.verdict.value,
                "legacy_disposition": disposition,
            },
            editorial.evidence,
        )
        emit(
            StageName.SELECTION,
            StageEventType.SELECTION_RESULT,
            TechnicalStatus.SUCCESS,
            _policy_flow(policy_action),
            selection.reason_code,
            {
                "policy_action": selection.policy_action.value,
                "selection_track": selection.selection_track.value,
                "selected": selection.selected,
                "selection_rank": selection.selection_rank,
            },
            selection.evidence,
        )
        emit(
            StageName.PROJECTION,
            StageEventType.PROJECTION_RESULT,
            TechnicalStatus.SUCCESS,
            _policy_flow(policy_action),
            "legacy_terminal_projection",
            {
                "candidate_disposition": projection.candidate_disposition,
                "eligible_for_editor": projection.eligible_for_editor,
                "reject_reason": projection.reject_reason,
                "canonical_source": projection.canonical_source,
                "source_action": projection.source_action,
                "selection_track": projection.selection_track,
            },
            projection.evidence,
        )

        return LegacyAdaptedItem(
            discovery=discovery,
            gate=gate,
            acquisition=acquisition,
            canonical=canonical,
            editorial=editorial,
            selection=selection,
            projection=projection,
            events=tuple(events),
        )

    def adapt_run(
        self,
        *,
        context: RunContext,
        pairs: Iterable[tuple[DiscoveredURL, ExtractedArticle]],
        legacy_summary: Mapping[str, Any] | None = None,
        created_at_bj: str = "",
    ) -> LegacyAdaptedRun:
        items = tuple(
            self.adapt_item(
                context=context,
                discovered=discovered,
                article=article,
                created_at_bj=created_at_bj,
            )
            for discovered, article in pairs
        )
        events = tuple(event for item in items for event in item.events)
        metrics = summarize_stage_events(events)
        comparison = (
            compare_legacy_summary(legacy_summary, metrics)
            if legacy_summary is not None
            else None
        )
        return LegacyAdaptedRun(
            context=context,
            items=items,
            events=events,
            metrics=metrics,
            legacy_summary_comparison=comparison,
        )


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "LEGACY_ADAPTER_VERSION",
    "LegacyAdaptedItem",
    "LegacyAdaptedRun",
    "LegacyV056mAdapter",
]
