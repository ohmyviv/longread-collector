"""v0.5.6m terminal-gate wrapper with Chinese labelled-date evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import DiscoveredURL, ExtractedArticle
from .post_extraction_gates_v056l import apply_post_extraction_gates_v056l
from .publication_date_v056m import extract_body_publication_date_v056m

POST_EXTRACTION_GATE_VERSION = "post-extraction-gates-v0.5.6m"


def apply_post_extraction_gates_v056m(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    now: datetime | None = None,
    body_date_extractor: Any = None,
) -> dict[str, Any]:
    result = apply_post_extraction_gates_v056l(
        discovered,
        article,
        now=now,
        body_date_extractor=body_date_extractor or extract_body_publication_date_v056m,
    )
    article.metadata.setdefault("post_extraction_gate", {})["version"] = (
        POST_EXTRACTION_GATE_VERSION
    )
    return result


__all__ = [
    "POST_EXTRACTION_GATE_VERSION",
    "apply_post_extraction_gates_v056m",
]
