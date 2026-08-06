"""v0.5.6 PR-D pipeline with v0.5.6l natural-holdout calibration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import classification as _classification
from . import pipeline_v05 as _pipeline_v05
from . import pipeline_v056b as _pipeline_v056b
from . import quality as _quality
from .classification import ClassificationResult
from .classification_v056l import (
    CLASSIFICATION_VERSION,
    classify_candidate_v056l,
    sanitize_author_v056l,
)
from .content_identity_v056j import CONTENT_IDENTITY_VERSION, evaluate_content_identity
from .extraction import FallbackBudget
from .historical_dedupe_v056l import (
    HISTORICAL_DEDUPE_VERSION,
    apply_historical_primary_document_dedupe_from_store,
)
from .models import DiscoveredURL, ExtractedArticle
from .pipeline_v056c import NativeCollectorPipeline as _BasePipeline
from .post_extraction_gates_v056l import (
    POST_EXTRACTION_GATE_VERSION,
    apply_post_extraction_gates_v056l,
)
from .publication_date_v056l import extract_body_publication_date_v056l
from .source_chase_identity_v056j import SOURCE_CHASE_IDENTITY_VERSION
from .source_chase_v056 import SOURCE_CHASE_VERSION, build_source_chase_queries_v056
from .source_relationship_v056 import (
    SOURCE_RELATIONSHIP_VERSION,
    detect_wire_evidence,
    evidence_dict,
)

FINAL_CALIBRATION_VERSION = "shadow-quality-final-v0.5.6l"

# v0.5.5 installs its classifier during module import. PR-D replaces the
# callable after PR-C is fully loaded, so extraction and quality use the same
# fully calibrated policy in one pass.
_classification.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_classification.classify_candidate = classify_candidate_v056l
_quality.classify_candidate = classify_candidate_v056l
_pipeline_v05.build_source_chase_queries = build_source_chase_queries_v056

_PR_D_MARKER = (
    f"classification_version={CLASSIFICATION_VERSION}; "
    f"final_calibration_version={FINAL_CALIBRATION_VERSION}; "
    f"source_relationship_version={SOURCE_RELATIONSHIP_VERSION}; "
    f"source_chase_version={SOURCE_CHASE_VERSION}; "
    f"content_identity_version={CONTENT_IDENTITY_VERSION}; "
    f"source_chase_identity_version={SOURCE_CHASE_IDENTITY_VERSION}; "
    f"historical_dedupe_version={HISTORICAL_DEDUPE_VERSION}; "
    f"post_extraction_gate_version={POST_EXTRACTION_GATE_VERSION}"
)
if _PR_D_MARKER not in _pipeline_v056b._SELECTION_MARKER:
    _pipeline_v056b._SELECTION_MARKER = f"{_pipeline_v056b._SELECTION_MARKER}; {_PR_D_MARKER}"


def _apply_classification(
    article: ExtractedArticle,
    result: ClassificationResult,
) -> None:
    article.page_role = result.page_role
    article.page_type = result.page_type
    article.content_type = result.content_type
    article.candidate_disposition = result.candidate_disposition
    article.special_candidate_type = result.special_candidate_type
    article.source_relationship = result.source_relationship
    article.original_publisher = result.original_publisher
    article.original_url = result.original_url
    article.wire_service = result.wire_service
    article.source_action = result.source_action
    article.duplicate_type = result.duplicate_type
    article.content_cluster_id = result.content_cluster_id
    article.classification_confidence = result.confidence
    article.classification_version = CLASSIFICATION_VERSION
    article.classification_reason = result.reason
    article.eligible_for_editor = result.eligible_for_editor
    if result.original_publisher:
        article.canonical_source = result.original_publisher
    article.reject_reason = "" if result.eligible_for_editor else result.reason

    article.metadata.setdefault("classification", {})
    article.metadata["classification"].update(
        {
            "version": CLASSIFICATION_VERSION,
            "final_calibration_version": FINAL_CALIBRATION_VERSION,
            "page_role": article.page_role,
            "page_type": article.page_type,
            "content_type": article.content_type,
            "candidate_disposition": article.candidate_disposition,
            "source_relationship": article.source_relationship,
            "source_action": article.source_action,
            "duplicate_type": article.duplicate_type,
            "content_cluster_id": article.content_cluster_id,
            "confidence": article.classification_confidence,
            "reason": article.classification_reason,
        }
    )


def _write_terminal_state(article: ExtractedArticle) -> None:
    article.metadata["terminal_state"] = {
        "version": POST_EXTRACTION_GATE_VERSION,
        "final_calibration_version": FINAL_CALIBRATION_VERSION,
        "page_role": article.page_role,
        "page_type": article.page_type,
        "content_type": article.content_type,
        "candidate_disposition": article.candidate_disposition,
        "eligible_for_editor": article.eligible_for_editor,
        "reject_reason": article.reject_reason,
        "classification_reason": article.classification_reason,
        "source_relationship": article.source_relationship,
        "duplicate_type": article.duplicate_type,
        "content_cluster_id": article.content_cluster_id,
    }


class NativeCollectorPipeline(_BasePipeline):
    """Run PR-A/B/C with one final v0.5.6l classification and terminal gate."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._historical_dedupe_count = 0

    async def _extract_batch(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        articles = await super()._extract_batch(discovered, fallback_budget)
        for discovered_item, article in zip(discovered, articles, strict=True):
            identity = evaluate_content_identity(
                title=article.title,
                markdown=article.content_markdown,
                discovered_title=discovered_item.title,
                external_link=str(discovered_item.metadata.get("external_link", "")),
            )
            article.metadata["content_identity"] = identity.as_dict()
            article.metadata["content_metrics"] = {
                "version": CONTENT_IDENTITY_VERSION,
                "raw_markdown_chars": identity.raw_markdown_chars,
                "body_prose_chars": identity.body_prose_chars,
                "template_chars": identity.template_chars,
                "image_count": identity.image_count,
                "video_count": identity.video_count,
                "heading_count": identity.heading_count,
            }
            if identity.resolved_title and identity.resolved_title != article.title:
                article.title = identity.resolved_title

            raw_author = str(getattr(article, "author", "") or "")
            clean_author = sanitize_author_v056l(raw_author)
            if clean_author != raw_author.strip():
                article.metadata["author_sanitization"] = {
                    "version": CLASSIFICATION_VERSION,
                    "raw_author": raw_author[:500],
                    "clean_author": clean_author,
                    "reason": "metadata_boilerplate",
                }
                article.author = clean_author

            result = classify_candidate_v056l(
                url=article.url,
                title=article.title,
                description=article.description,
                author=article.author,
                markdown=article.content_markdown,
                published_at=article.published_at,
                verification_level=article.verification_level,
                content_chars=identity.body_prose_chars,
            )
            _apply_classification(article, result)

            evidence = detect_wire_evidence(
                url=article.url,
                author=str(getattr(article, "author", "") or ""),
                markdown=str(article.content_markdown or ""),
                description=str(article.description or ""),
            )
            article.metadata["source_relationship_evidence"] = evidence_dict(evidence)
            article.metadata["classification_policy"] = {
                "version": CLASSIFICATION_VERSION,
                "final_calibration_version": FINAL_CALIBRATION_VERSION,
                "page_role": article.page_role,
                "page_type": article.page_type,
                "content_type": article.content_type,
                "candidate_disposition": article.candidate_disposition,
                "special_candidate_type": article.special_candidate_type,
                "source_relationship": article.source_relationship,
                "source_action": article.source_action,
                "reason": article.classification_reason,
            }

            apply_post_extraction_gates_v056l(
                discovered_item,
                article,
                body_date_extractor=extract_body_publication_date_v056l,
            )

        pairs = list(zip(discovered, articles, strict=True))
        self._historical_dedupe_count += apply_historical_primary_document_dedupe_from_store(
            self.store,
            pairs,
        )
        for article in articles:
            _write_terminal_state(article)
        return articles

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        self._historical_dedupe_count = 0
        result = await super().collect(group_id=group_id, query_file=query_file)
        result.update(
            {
                "classification_version": CLASSIFICATION_VERSION,
                "final_calibration_version": FINAL_CALIBRATION_VERSION,
                "source_relationship_version": SOURCE_RELATIONSHIP_VERSION,
                "source_chase_version": SOURCE_CHASE_VERSION,
                "content_identity_version": CONTENT_IDENTITY_VERSION,
                "source_chase_identity_version": SOURCE_CHASE_IDENTITY_VERSION,
                "historical_dedupe_version": HISTORICAL_DEDUPE_VERSION,
                "historical_duplicates_rejected": self._historical_dedupe_count,
                "post_extraction_gate_version": POST_EXTRACTION_GATE_VERSION,
            }
        )
        return result


__all__ = ["FINAL_CALIBRATION_VERSION", "NativeCollectorPipeline"]
