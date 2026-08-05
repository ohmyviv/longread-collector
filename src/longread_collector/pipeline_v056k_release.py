"""Release wrapper for the fully calibrated v0.5.6k shadow pipeline.

PR-D and PR-E remain unchanged. This final layer reapplies the reviewed
classification/source calibration and the authoritative body-date gate after
all extraction and operational instrumentation has completed.
"""

from __future__ import annotations

from . import classification as _classification
from . import post_extraction_gates_v056k as _post_gates
from . import quality as _quality
from .classification_v056k_final import (
    CLASSIFICATION_VERSION,
    classify_candidate_v056k_final,
)
from .content_identity_v056j import CONTENT_IDENTITY_VERSION, evaluate_content_identity
from .extraction import FallbackBudget
from .models import DiscoveredURL, ExtractedArticle
from .pipeline_v056d import _apply_classification
from .pipeline_v056e import NativeCollectorPipeline as _BasePipeline
from .publication_date_v056k_final import extract_body_publication_date_final

# Earlier layers resolve these callables at module scope. Point the shared
# classification and terminal-date hooks at the final reviewed policy without
# modifying the stable PR-D/PR-E implementations.
_classification.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_classification.classify_candidate = classify_candidate_v056k_final
_quality.classify_candidate = classify_candidate_v056k_final
_post_gates.extract_body_publication_date = extract_body_publication_date_final

FINAL_CALIBRATION_VERSION = "shadow-quality-final-v0.5.6k"


class NativeCollectorPipeline(_BasePipeline):
    """Run the existing pipeline, then project one final reviewed state."""

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

            result = classify_candidate_v056k_final(
                url=article.url,
                title=article.title,
                description=article.description,
                author=str(getattr(article, "author", "") or ""),
                markdown=article.content_markdown,
                published_at=article.published_at,
                verification_level=article.verification_level,
                content_chars=identity.body_prose_chars,
            )
            _apply_classification(article, result)
            _post_gates.apply_post_extraction_gates_v056k(discovered_item, article)

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
            article.metadata["terminal_state"] = {
                "version": _post_gates.POST_EXTRACTION_GATE_VERSION,
                "final_calibration_version": FINAL_CALIBRATION_VERSION,
                "page_role": article.page_role,
                "page_type": article.page_type,
                "content_type": article.content_type,
                "candidate_disposition": article.candidate_disposition,
                "eligible_for_editor": article.eligible_for_editor,
                "reject_reason": article.reject_reason,
                "classification_reason": article.classification_reason,
            }
        return articles


__all__ = ["FINAL_CALIBRATION_VERSION", "NativeCollectorPipeline"]
