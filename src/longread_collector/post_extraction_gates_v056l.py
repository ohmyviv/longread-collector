"""v0.5.6l terminal-gate wrapper with versioned date evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import DiscoveredURL, ExtractedArticle
from .post_extraction_gates_v056k import apply_post_extraction_gates_v056k
from .publication_date_v056k import BodyDateEvidence

POST_EXTRACTION_GATE_VERSION = "post-extraction-gates-v0.5.6l"


def apply_post_extraction_gates_v056l(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    now: datetime | None = None,
    body_date_extractor: Any = None,
) -> dict[str, Any]:
    result = apply_post_extraction_gates_v056k(
        discovered,
        article,
        now=now,
        body_date_extractor=body_date_extractor,
    )
    gate = article.metadata.setdefault("post_extraction_gate", {})
    gate["version"] = POST_EXTRACTION_GATE_VERSION
    evidence = article.metadata.get("freshness", {}).get("body_publication_evidence", {})
    if isinstance(evidence, dict) and evidence.get("version"):
        article.metadata.setdefault("freshness", {})["body_date_version"] = evidence["version"]
    return result


__all__ = ["POST_EXTRACTION_GATE_VERSION", "apply_post_extraction_gates_v056l"]
