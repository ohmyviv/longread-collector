"""v0.5.6l terminal-gate wrapper with versioned date and body evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import DiscoveredURL, ExtractedArticle
from .post_extraction_gates_v056k import apply_post_extraction_gates_v056k

POST_EXTRACTION_GATE_VERSION = "post-extraction-gates-v0.5.6l"


def _body_prose_chars(article: ExtractedArticle) -> int:
    metrics = article.metadata.get("content_metrics", {})
    try:
        value = int(metrics.get("body_prose_chars") or 0)
    except (TypeError, ValueError):
        value = 0
    return value or int(article.content_chars or 0)


def apply_post_extraction_gates_v056l(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    now: datetime | None = None,
    body_date_extractor: Any = None,
) -> dict[str, Any]:
    previous = {
        "candidate_disposition": article.candidate_disposition,
        "eligible_for_editor": article.eligible_for_editor,
        "reject_reason": article.reject_reason,
        "classification_reason": article.classification_reason,
        "page_type": article.page_type,
        "content_type": article.content_type,
        "source_relationship": article.source_relationship,
    }
    result = apply_post_extraction_gates_v056k(
        discovered,
        article,
        now=now,
        body_date_extractor=body_date_extractor,
    )
    gate = article.metadata.setdefault("post_extraction_gate", {})
    gate["version"] = POST_EXTRACTION_GATE_VERSION
    freshness = article.metadata.setdefault("freshness", {})
    evidence = freshness.get("body_publication_evidence", {})
    if isinstance(evidence, dict) and evidence.get("version"):
        freshness["body_date_version"] = evidence["version"]

    try:
        age_days = int(freshness.get("freshness_age_days"))
    except (TypeError, ValueError):
        age_days = -999
    body_verified = (
        previous["candidate_disposition"] == "formal_candidate"
        and previous["eligible_for_editor"] is True
        and article.extraction_status == "success"
        and _body_prose_chars(article) >= 1800
        and isinstance(evidence, dict)
        and evidence.get("confidence") == "high"
    )
    if (
        result.get("freshness_rejected") is True
        and article.reject_reason == "stale_8_14d_without_depth"
        and 8 <= age_days <= 14
        and body_verified
    ):
        article.candidate_disposition = str(previous["candidate_disposition"])
        article.eligible_for_editor = bool(previous["eligible_for_editor"])
        article.reject_reason = str(previous["reject_reason"])
        article.classification_reason = str(previous["classification_reason"])
        article.page_type = str(previous["page_type"])
        article.content_type = str(previous["content_type"])
        article.source_relationship = str(previous["source_relationship"])
        freshness.update(
            {
                "decision_allowed": True,
                "freshness_reject_reason": "",
                "freshness_track": "deep_read_8_14d_body_verified",
                "freshness_exception_reason": "complete_formal_body_after_extraction",
                "freshness_score_penalty": -2,
                "body_depth_override": True,
            }
        )
        gate.update(
            {
                "freshness_allowed": True,
                "freshness_reject_reason": "",
                "body_depth_override": True,
                "body_depth_override_age_days": age_days,
            }
        )
        result = {**result, "freshness_rejected": False, "body_depth_override": True}

    # Once freshness is the terminal rejection reason, there is no remaining
    # source-chase or retention action to perform for an otherwise original
    # article. Clear stale actions so top-level fields describe one executable
    # terminal state rather than the pre-freshness classification intent.
    if result.get("freshness_rejected") is True and article.candidate_disposition == "reject":
        if str(previous["source_relationship"]) == "original":
            article.source_relationship = "original"
        article.source_action = "none"
        article.duplicate_type = "none"
        gate["terminal_source_action_cleared"] = True
    return result


__all__ = ["POST_EXTRACTION_GATE_VERSION", "apply_post_extraction_gates_v056l"]
