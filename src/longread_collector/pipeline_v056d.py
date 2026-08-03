"""v0.5.6 PR-D: separated candidate types and strong source relationships."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import classification as _classification
from . import pipeline_v05 as _pipeline_v05
from . import pipeline_v056b as _pipeline_v056b
from . import quality as _quality
from .classification_v056h import CLASSIFICATION_VERSION, classify_candidate_v056h
from .extraction import FallbackBudget
from .models import DiscoveredURL, ExtractedArticle
from .pipeline_v056c import NativeCollectorPipeline as _BasePipeline
from .source_chase_v056 import SOURCE_CHASE_VERSION, build_source_chase_queries_v056
from .source_relationship_v056 import (
    SOURCE_RELATIONSHIP_VERSION,
    detect_wire_evidence,
    evidence_dict,
)

# v0.5.5 installs its classifier during module import. PR-D replaces the
# callable after PR-C is fully loaded, so extraction and quality use one policy.
_classification.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_classification.classify_candidate = classify_candidate_v056h
_quality.classify_candidate = classify_candidate_v056h
_pipeline_v05.build_source_chase_queries = build_source_chase_queries_v056

_PR_D_MARKER = (
    f"classification_version={CLASSIFICATION_VERSION}; "
    f"source_relationship_version={SOURCE_RELATIONSHIP_VERSION}; "
    f"source_chase_version={SOURCE_CHASE_VERSION}"
)
if _PR_D_MARKER not in _pipeline_v056b._SELECTION_MARKER:
    _pipeline_v056b._SELECTION_MARKER = f"{_pipeline_v056b._SELECTION_MARKER}; {_PR_D_MARKER}"


class NativeCollectorPipeline(_BasePipeline):
    """Run PR-A/B/C with PR-D classification and relationship evidence."""

    async def _extract_batch(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        articles = await super()._extract_batch(discovered, fallback_budget)
        for article in articles:
            evidence = detect_wire_evidence(
                url=article.url,
                author=str(getattr(article, "author", "") or ""),
                markdown=str(article.content_markdown or ""),
                description=str(article.description or ""),
            )
            article.metadata["source_relationship_evidence"] = evidence_dict(evidence)
            article.metadata["classification_policy"] = {
                "version": CLASSIFICATION_VERSION,
                "page_role": article.page_role,
                "page_type": article.page_type,
                "content_type": article.content_type,
                "candidate_disposition": article.candidate_disposition,
                "special_candidate_type": article.special_candidate_type,
                "source_relationship": article.source_relationship,
                "source_action": article.source_action,
                "reason": article.classification_reason,
            }
            article.classification_version = CLASSIFICATION_VERSION
        return articles

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        result = await super().collect(group_id=group_id, query_file=query_file)
        result.update(
            {
                "classification_version": CLASSIFICATION_VERSION,
                "source_relationship_version": SOURCE_RELATIONSHIP_VERSION,
                "source_chase_version": SOURCE_CHASE_VERSION,
            }
        )
        return result


__all__ = ["NativeCollectorPipeline"]
