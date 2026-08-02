from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DiscoveredURL:
    url: str
    title: str = ""
    description: str = ""
    published_at: str = ""
    discovery_method: str = "firecrawl_search"
    query_or_source: str = ""
    language: str = ""
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    # Compatibility aliases used by historical snapshot/audit payloads.
    query_id: str = ""
    rank_score: float = 0.0

    def __post_init__(self) -> None:
        if self.query_id and not self.query_or_source:
            self.query_or_source = self.query_id
        elif self.query_or_source and not self.query_id:
            self.query_id = self.query_or_source

        if self.rank_score and not self.rank:
            self.rank = int(round(self.rank_score))
        elif self.rank and not self.rank_score:
            self.rank_score = float(self.rank)


@dataclass(slots=True)
class ExtractedArticle:
    article_id: str
    url: str
    url_canonical: str
    domain: str
    title: str = ""
    author: str = ""
    published_at: str = ""
    language: str = ""
    canonical_source: str = ""
    hosting_source: str = ""
    original_publisher: str = ""
    original_url: str = ""
    wire_service: str = ""
    source_relationship: str = "original"
    page_role: str = "standalone_content"
    page_type: str = "article"
    content_type: str = "unknown"
    candidate_disposition: str = "reject"
    special_candidate_type: str = ""
    source_action: str = "none"
    duplicate_type: str = "none"
    content_cluster_id: str = ""
    classification_confidence: str = "medium"
    classification_version: str = ""
    classification_reason: str = ""
    description: str = ""
    extractor_used: str = ""
    extraction_status: str = "failed"
    verification_level: str = "D"
    content_markdown: str = ""
    content_chars: int = 0
    content_sha256: str = ""
    content_truncated: bool = False
    eligible_for_editor: bool = False
    reject_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_attempts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Apply the v0.4 semantic contract after technical extraction."""
        if self.classification_version:
            return

        from .classification import CLASSIFICATION_VERSION, classify_candidate

        technical_eligible_before = self.eligible_for_editor
        result = classify_candidate(
            url=self.url,
            title=self.title,
            description=self.description,
            author=self.author,
            markdown=self.content_markdown,
            published_at=self.published_at,
            verification_level=self.verification_level,
            content_chars=self.content_chars,
        )
        self.page_role = result.page_role
        self.page_type = result.page_type
        self.content_type = result.content_type
        self.candidate_disposition = result.candidate_disposition
        self.special_candidate_type = result.special_candidate_type
        self.source_relationship = result.source_relationship
        self.original_publisher = result.original_publisher
        self.original_url = result.original_url
        self.wire_service = result.wire_service
        self.source_action = result.source_action
        self.duplicate_type = result.duplicate_type
        self.content_cluster_id = result.content_cluster_id
        self.classification_confidence = result.confidence
        self.classification_version = CLASSIFICATION_VERSION
        self.classification_reason = result.reason
        self.eligible_for_editor = result.eligible_for_editor

        if result.original_publisher:
            self.canonical_source = result.original_publisher
        if self.candidate_disposition == "formal_candidate":
            self.reject_reason = ""
        else:
            self.reject_reason = result.reason

        self.metadata.setdefault("classification", {})
        self.metadata["classification"].update(
            {
                "version": CLASSIFICATION_VERSION,
                "technical_eligible_before": technical_eligible_before,
                "page_role": self.page_role,
                "page_type": self.page_type,
                "content_type": self.content_type,
                "candidate_disposition": self.candidate_disposition,
                "source_relationship": self.source_relationship,
                "source_action": self.source_action,
                "duplicate_type": self.duplicate_type,
                "content_cluster_id": self.content_cluster_id,
                "confidence": self.classification_confidence,
                "reason": self.classification_reason,
            }
        )
