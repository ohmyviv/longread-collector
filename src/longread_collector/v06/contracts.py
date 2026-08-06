"""Immutable stage contracts for the v0.6 collector architecture."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _deep_freeze(value: Any) -> Any:
    """Recursively freeze JSON-like values held by immutable contracts."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _deep_freeze(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("expected a mapping")
    return frozen


class StageName(StrEnum):
    DISCOVERY = "discovery"
    ACQUISITION_GATE = "acquisition_gate"
    ACQUISITION = "acquisition"
    CANONICAL = "canonical"
    EDITORIAL = "editorial"
    SELECTION = "selection"
    PROJECTION = "projection"


class StageEventType(StrEnum):
    DISCOVERY_RESULT = "discovery_result"
    GATE_RESULT = "gate_result"
    EXTRACTOR_ATTEMPT = "extractor_attempt"
    ACQUISITION_RESULT = "acquisition_result"
    CANONICAL_RESULT = "canonical_result"
    EDITORIAL_RESULT = "editorial_result"
    SELECTION_RESULT = "selection_result"
    PROJECTION_RESULT = "projection_result"


class TechnicalStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class FlowStatus(StrEnum):
    PASS = "pass"
    REJECT = "reject"
    DEFER = "defer"
    ACTION_REQUIRED = "action_required"
    ERROR = "error"


class GateAction(StrEnum):
    ACQUIRE = "acquire"
    DEFER = "defer"
    HARD_REJECT = "hard_reject"


class EditorialVerdict(StrEnum):
    RECOMMEND = "recommend"
    CONSIDER = "consider"
    LOW_VALUE = "low_value"
    REJECT = "reject"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PolicyAction(StrEnum):
    SELECT_STANDARD = "select_standard"
    SELECT_SPECIAL = "select_special"
    SOURCE_CHASE = "source_chase"
    DEFER = "defer"
    REJECT = "reject"


class SelectionTrack(StrEnum):
    STANDARD_LONGREAD = "standard_longread"
    SPECIAL_DOCUMENT = "special_document"
    ACADEMIC = "academic"
    SOURCE_CHASE = "source_chase"
    EXPLORATION = "exploration"
    NONE = "none"


class PageSurface(StrEnum):
    ARTICLE_PAGE = "article_page"
    DOCUMENT_PAGE = "document_page"
    EXTERNAL_LINK_STUB = "external_link_stub"
    LISTING = "listing"
    HOMEPAGE = "homepage"
    PAYWALL = "paywall"
    LOGIN = "login"
    CAPTCHA = "captcha"
    SOCIAL_POST = "social_post"
    UNKNOWN = "unknown"


class ContentMedium(StrEnum):
    WRITTEN_ARTICLE = "written_article"
    PRIMARY_DOCUMENT = "primary_document"
    ACADEMIC_PAPER = "academic_paper"
    TELEVISION_TRANSCRIPT = "television_transcript"
    PODCAST_TRANSCRIPT = "podcast_transcript"
    VIDEO_PAGE = "video_page"
    PHOTO_ESSAY = "photo_essay"
    DATA_CARD = "data_card"
    EVENT_LISTING = "event_listing"
    MIXED_MEDIA = "mixed_media"
    UNKNOWN = "unknown"


class EditorialGenre(StrEnum):
    INVESTIGATION = "investigation"
    REPORTED_FEATURE = "reported_feature"
    ANALYSIS = "analysis"
    COMMENTARY = "commentary"
    INTERVIEW = "interview"
    BOOK_REVIEW = "book_review"
    POLICY_DOCUMENT = "policy_document"
    INSTITUTIONAL_REPORT = "institutional_report"
    EVENT_PREVIEW = "event_preview"
    EVENT_RECAP = "event_recap"
    PROMOTION = "promotion"
    STRAIGHT_NEWS = "straight_news"
    MARKET_DATA = "market_data"
    UNKNOWN = "unknown"


class AssetClass(StrEnum):
    MEDIA_ARTICLE = "media_article"
    PRIMARY_DOCUMENT = "primary_document"
    INSTITUTIONAL_REPORT = "institutional_report"
    ACADEMIC_PAPER = "academic_paper"
    TRANSCRIPT = "transcript"
    DATA_PRODUCT = "data_product"
    UNKNOWN = "unknown"


class SourceRelationship(StrEnum):
    ORIGINAL = "original"
    TRANSLATED_REPUBLISH = "translated_republish"
    WIRE_REPUBLISH = "wire_republish"
    SECONDARY_REPUBLISH = "secondary_republish"
    UNCERTAIN = "uncertain"


class SourceAction(StrEnum):
    NONE = "none"
    RETAIN_CURRENT_DISPLAY_URL = "retain_current_display_url"
    FIND_ORIGINAL_ARTICLE = "find_original_article"
    FIND_PRIMARY_DOCUMENT = "find_primary_document"
    REPLACE_WITH_ORIGINAL = "replace_with_original"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    evidence_type: str
    source_stage: StageName
    field: str
    value: Any = None
    confidence: float = 0.0
    excerpt: str = ""
    extractor: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _deep_freeze(self.value))


@dataclass(frozen=True, slots=True)
class RunContext:
    schema_version: str
    run_id: str
    group_id: str
    scheduled_at_bj: str
    started_at_bj: str
    collector_version: str
    max_acquisition_attempts: int = 32
    firecrawl_daily_limit: int = 3


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    discovery_id: str
    url: str
    canonical_url_hint: str = ""
    title_hint: str = ""
    description_hint: str = ""
    published_at_hints: tuple[str, ...] = ()
    source_id: str = ""
    discovery_method: str = ""
    query_or_section: str = ""
    rank: int = 0
    route_status: TechnicalStatus = TechnicalStatus.SUCCESS
    external_link_hint: str = ""
    raw_metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_metadata", _freeze_mapping(self.raw_metadata))


@dataclass(frozen=True, slots=True)
class GateDecision:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    action: GateAction
    reason_code: str
    confidence: float
    estimated_acquisition_cost: float = 0.0
    priority_features: Mapping[str, float] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "priority_features",
            _freeze_mapping(self.priority_features),
        )


@dataclass(frozen=True, slots=True)
class AcquisitionAttempt:
    attempt_id: str
    extractor: str
    status: TechnicalStatus
    request_sent: bool
    started_at_bj: str = ""
    completed_at_bj: str = ""
    body_chars: int = 0
    prose_chars: int = 0
    credits_used: float = 0.0
    latency_ms: int = 0
    reason_code: str = ""
    error_type: str = ""
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class AcquisitionBundle:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    status: TechnicalStatus
    attempts: tuple[AcquisitionAttempt, ...] = ()
    best_attempt_id: str = ""
    body_text: str = ""
    body_markdown: str = ""
    raw_title: str = ""
    raw_author: str = ""
    raw_dates: tuple[str, ...] = ()
    raw_canonical_links: tuple[str, ...] = ()
    outbound_links: tuple[str, ...] = ()
    content_length: int = 0
    prose_length: int = 0
    template_length: int = 0
    image_count: int = 0
    video_count: int = 0
    sufficient_for_canonicalization: bool = False
    sufficient_for_editorial_judgment: bool = False
    sufficient_for_source_chase: bool = False
    total_cost: float = 0.0
    total_latency_ms: int = 0
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalArticle:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    content_id: str
    display_url: str
    canonical_content_url: str = ""
    resolved_title: str = ""
    resolved_author: str = ""
    published_at: str = ""
    published_at_confidence: float = 0.0
    publisher: str = ""
    hosting_source: str = ""
    canonical_source: str = ""
    original_publisher: str = ""
    source_relationship: SourceRelationship = SourceRelationship.UNCERTAIN
    source_action: SourceAction = SourceAction.NONE
    page_surface: PageSurface = PageSurface.UNKNOWN
    main_content_medium: ContentMedium = ContentMedium.UNKNOWN
    editorial_genre: EditorialGenre = EditorialGenre.UNKNOWN
    asset_class: AssetClass = AssetClass.UNKNOWN
    duplicate_cluster_id: str = ""
    freshness_facts: Mapping[str, Any] = field(default_factory=dict)
    confidence_by_field: Mapping[str, float] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "freshness_facts",
            _freeze_mapping(self.freshness_facts),
        )
        object.__setattr__(
            self,
            "confidence_by_field",
            _freeze_mapping(self.confidence_by_field),
        )


@dataclass(frozen=True, slots=True)
class EditorialAssessment:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    substance_score: float
    original_reporting_score: float
    analysis_score: float
    argument_score: float
    evidence_density_score: float
    reader_value_score: float
    timeliness_relevance_score: float
    promotional_risk: float
    event_risk: float
    transcript_risk: float
    template_risk: float
    editorial_value: str
    verdict: EditorialVerdict
    confidence: float
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    policy_action: PolicyAction
    selection_track: SelectionTrack
    selected: bool
    selection_rank: int | None = None
    marginal_utility: float = 0.0
    risk_penalty: float = 0.0
    diversity_penalty: float = 0.0
    freshness_penalty: float = 0.0
    cost_penalty: float = 0.0
    reason_code: str = ""
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class StageEvent:
    schema_version: str
    event_id: str
    run_id: str
    item_id: str
    stage: StageName
    event_type: StageEventType
    stage_version: str
    technical_status: TechnicalStatus
    flow_status: FlowStatus
    reason_code: str
    created_at_bj: str
    parent_event_id: str = ""
    cost: float = 0.0
    attributes: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", _freeze_mapping(self.attributes))


@dataclass(frozen=True, slots=True)
class FinalProjection:
    schema_version: str
    projector_version: str
    run_id: str
    item_id: str
    candidate_disposition: str
    eligible_for_editor: bool
    reject_reason: str
    canonical_source: str
    source_action: str
    selection_track: str
    evidence: tuple[Evidence, ...] = ()


__all__ = [
    "AcquisitionAttempt",
    "AcquisitionBundle",
    "AssetClass",
    "CanonicalArticle",
    "ContentMedium",
    "DiscoveryRecord",
    "EditorialAssessment",
    "EditorialGenre",
    "EditorialVerdict",
    "Evidence",
    "FinalProjection",
    "FlowStatus",
    "GateAction",
    "GateDecision",
    "PageSurface",
    "PolicyAction",
    "RunContext",
    "SelectionDecision",
    "SelectionTrack",
    "SourceAction",
    "SourceRelationship",
    "StageEvent",
    "StageEventType",
    "StageName",
    "TechnicalStatus",
]
