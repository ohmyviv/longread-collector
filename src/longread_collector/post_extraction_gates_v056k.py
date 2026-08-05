"""Final post-classification page and freshness gates for v0.5.6k."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Any

from .models import DiscoveredURL, ExtractedArticle
from .page_gate_policy_v056 import evaluate_page_gate_policy
from .post_freshness_v056h import (
    POST_FRESHNESS_VERSION,
    evaluate_post_extraction_freshness,
)
from .publication_date_v056k import (
    BODY_DATE_VERSION,
    BodyDateEvidence,
    extract_body_publication_date,
)

POST_EXTRACTION_GATE_VERSION = "post-extraction-gates-v0.5.6k"
BodyDateExtractor = Callable[[str], BodyDateEvidence | None]


def _evaluation_item(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    body_date_extractor: BodyDateExtractor,
) -> tuple[DiscoveredURL, BodyDateEvidence | None]:
    metadata = deepcopy(discovered.metadata)
    for key, value in article.metadata.items():
        if isinstance(value, dict) and isinstance(metadata.get(key), dict):
            metadata[key] = {**metadata[key], **deepcopy(value)}
        else:
            metadata[key] = deepcopy(value)

    body_date = body_date_extractor(article.content_markdown)
    published_at = (
        body_date.value.isoformat()
        if body_date is not None
        else article.published_at or discovered.published_at
    )
    item = DiscoveredURL(
        url=article.url_canonical or article.url or discovered.url,
        title=article.title or discovered.title,
        description=article.description or discovered.description,
        published_at=published_at,
        discovery_method=discovered.discovery_method,
        query_or_source=discovered.query_or_source,
        language=article.language or discovered.language,
        rank=discovered.rank,
        metadata=metadata,
    )
    return item, body_date


def _reject_article(
    article: ExtractedArticle,
    *,
    reason: str,
    gate: str,
    page_type: str = "",
) -> None:
    audit = article.metadata.setdefault("post_extraction_gate", {})
    audit.update(
        {
            "version": POST_EXTRACTION_GATE_VERSION,
            "post_freshness_version": POST_FRESHNESS_VERSION,
            "previous_disposition": article.candidate_disposition,
            "previous_reject_reason": article.reject_reason,
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
    if marker not in previous_reason:
        article.classification_reason = (
            f"{previous_reason}; {marker}" if previous_reason else marker
        )


def apply_post_extraction_gates_v056k(
    discovered: DiscoveredURL,
    article: ExtractedArticle,
    *,
    now: datetime | None = None,
    body_date_extractor: BodyDateExtractor | None = None,
) -> dict[str, Any]:
    """Apply the only authoritative terminal page/freshness state.

    PR-C gates run during extraction, while later classification layers can
    legitimately refine page intent and source relationships. This function is
    therefore called after v0.5.6k classification and projects the final gate
    result back to the top-level article fields.

    ``body_date_extractor`` is injectable so the release pipeline can use the
    final article-header parser without mutating module-global functions. Tests
    that monkeypatch ``extract_body_publication_date`` remain supported when no
    explicit extractor is supplied.
    """

    extractor = body_date_extractor or extract_body_publication_date
    item, body_date = _evaluation_item(
        discovered,
        article,
        body_date_extractor=extractor,
    )
    page = evaluate_page_gate_policy(item)
    freshness = evaluate_post_extraction_freshness(item, now=now)

    if body_date is not None:
        freshness_payload = item.metadata.setdefault("freshness", {})
        freshness_payload["published_at_resolved"] = body_date.value.isoformat()
        freshness_payload["published_at_source"] = body_date.source
        freshness_payload["published_at_confidence"] = body_date.confidence
        freshness_payload["body_date_version"] = BODY_DATE_VERSION
        freshness_payload["body_publication_evidence"] = body_date.as_dict()
        freshness_payload.setdefault("evidence", []).insert(
            0,
            {
                **body_date.as_dict(),
                "role": "published",
                "priority": 110 if body_date.confidence == "high" else 88,
            },
        )
        if article.published_at != body_date.value.isoformat():
            article.metadata["body_publication_date_override"] = {
                "version": BODY_DATE_VERSION,
                "previous_published_at": article.published_at,
                "resolved_published_at": body_date.value.isoformat(),
                "source": body_date.source,
                "confidence": body_date.confidence,
            }
            article.published_at = body_date.value.isoformat()

    # A complete translated republication is allowed to use the original
    # article date for the deep-read window. This is intentionally limited to
    # 14 days and requires the classification layer to have verified a full
    # translated body and an explicit original link.
    if (
        not freshness.allowed
        and article.source_relationship == "translated_republish"
        and freshness.age_days is not None
        and 0 <= freshness.age_days <= 14
        and freshness.reject_reason in {
            "stale_4_7d_without_quality_signal",
            "stale_8_14d_without_depth",
        }
    ):
        freshness = replace(
            freshness,
            allowed=True,
            reject_reason="",
            track="translated_republish_14d",
            exception_reason="complete_translation_with_original_link",
            score_penalty=-2,
        )
        item.metadata.setdefault("freshness", {}).update(
            {
                "decision_allowed": True,
                "freshness_reject_reason": "",
                "freshness_track": freshness.track,
                "freshness_exception_reason": freshness.exception_reason,
                "freshness_score_penalty": freshness.score_penalty,
                "translated_republish_exception": True,
            }
        )

    article.metadata["page_gate"] = deepcopy(item.metadata.get("page_gate", {}))
    article.metadata["freshness"] = deepcopy(item.metadata.get("freshness", {}))
    article.metadata.setdefault("post_extraction_gate", {}).update(
        {
            "version": POST_EXTRACTION_GATE_VERSION,
            "post_freshness_version": POST_FRESHNESS_VERSION,
            "page_gate_rejected": page.rejected,
            "page_gate_reason": page.reject_reason,
            "freshness_allowed": freshness.allowed,
            "freshness_reject_reason": freshness.reject_reason,
            "terminal_projection": True,
        }
    )

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

    # A previous extraction-stage gate may have rejected the article before the
    # body-date/source refinements were available. The post-classification
    # result is authoritative when both final gates allow it.
    if article.candidate_disposition != "reject":
        article.eligible_for_editor = True
        article.reject_reason = ""
    return {
        "page_rejected": False,
        "freshness_rejected": False,
        "skipped_for_failed_extraction": False,
    }


__all__ = [
    "POST_EXTRACTION_GATE_VERSION",
    "apply_post_extraction_gates_v056k",
]
