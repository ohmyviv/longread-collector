"""Post-extraction page-role and freshness verification for PR-C."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from .freshness_policy_v056f import evaluate_freshness_policy
from .models import DiscoveredURL, ExtractedArticle
from .page_gate_policy_v056 import evaluate_page_gate_policy

POST_EXTRACTION_GATE_VERSION = "post-extraction-gates-v0.5.6f"


def _evaluation_item(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
) -> DiscoveredURL:
    metadata = deepcopy(discovered.metadata)
    for key, value in article.metadata.items():
        if isinstance(value, dict) and isinstance(metadata.get(key), dict):
            metadata[key] = {**metadata[key], **deepcopy(value)}
        else:
            metadata[key] = deepcopy(value)
    return DiscoveredURL(
        url=article.url_canonical or article.url or discovered.url,
        title=article.title or discovered.title,
        description=article.description or discovered.description,
        published_at=article.published_at or discovered.published_at,
        discovery_method=discovered.discovery_method,
        query_or_source=discovered.query_or_source,
        language=article.language or discovered.language,
        rank=discovered.rank,
        metadata=metadata,
    )


def _reject_article(
    article: ExtractedArticle,
    *,
    reason: str,
    gate: str,
    page_type: str = "",
) -> None:
    audit = article.metadata.setdefault("post_extraction_gate", {})
    audit.setdefault("previous_disposition", article.candidate_disposition)
    audit.setdefault("previous_reject_reason", article.reject_reason)
    audit.update(
        {
            "version": POST_EXTRACTION_GATE_VERSION,
            "gate": gate,
            "reason": reason,
        }
    )
    article.candidate_disposition = "reject"
    article.eligible_for_editor = False
    article.reject_reason = reason
    if page_type:
        article.page_type = page_type
    previous_reason = str(article.classification_reason or "").strip()
    marker = f"post_{gate}_gate={reason}"
    article.classification_reason = (
        f"{previous_reason}; {marker}" if previous_reason else marker
    )


def apply_post_extraction_gates(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    item = _evaluation_item(discovered, article)
    page = evaluate_page_gate_policy(item)
    freshness = evaluate_freshness_policy(item, phase="post_extraction", now=now)

    article.metadata["page_gate"] = deepcopy(item.metadata.get("page_gate", {}))
    article.metadata["freshness"] = deepcopy(item.metadata.get("freshness", {}))
    article.metadata.setdefault("post_extraction_gate", {}).update(
        {
            "version": POST_EXTRACTION_GATE_VERSION,
            "page_gate_rejected": page.rejected,
            "page_gate_reason": page.reject_reason,
            "freshness_allowed": freshness.allowed,
            "freshness_reject_reason": freshness.reject_reason,
        }
    )

    resolved_date = str(
        article.metadata.get("freshness", {}).get("published_at_resolved", "")
    )
    if resolved_date and not article.published_at:
        article.published_at = resolved_date

    if article.extraction_status != "success":
        return {
            "page_rejected": False,
            "freshness_rejected": False,
            "skipped_for_failed_extraction": True,
        }
    if page.rejected:
        _reject_article(
            article,
            reason=page.reject_reason,
            gate="page",
            page_type=page.page_type,
        )
        return {
            "page_rejected": True,
            "freshness_rejected": False,
            "skipped_for_failed_extraction": False,
        }
    if not freshness.allowed:
        _reject_article(
            article,
            reason=freshness.reject_reason,
            gate="freshness",
        )
        return {
            "page_rejected": False,
            "freshness_rejected": True,
            "skipped_for_failed_extraction": False,
        }
    return {
        "page_rejected": False,
        "freshness_rejected": False,
        "skipped_for_failed_extraction": False,
    }


__all__ = ["POST_EXTRACTION_GATE_VERSION", "apply_post_extraction_gates"]
