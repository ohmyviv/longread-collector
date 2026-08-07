"""Canonical Article resolver for v0.6 PR-2."""

from __future__ import annotations

import hashlib
import re

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    DiscoveryRecord,
    Evidence,
    RunContext,
)
from .evidence import body_heading, make_evidence, nested, normalize_space, text
from .genre import resolve_genre
from .medium import resolve_medium
from .publication import resolve_publication
from .source_resolution import resolve_source

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr2"


class CanonicalArticleResolver:
    """Resolve factual identity without making daily editorial policy decisions."""

    stage_version = CANONICAL_SERVICE_VERSION

    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle:
        metadata = record.raw_metadata
        resolved_title, title_confidence, title_evidence = _resolve_title(record, bundle)

        medium = resolve_medium(
            record,
            bundle,
            resolved_title=resolved_title,
            asset_hint=None,
        )
        source = resolve_source(
            record,
            bundle,
            resolved_title=resolved_title,
            primary_document_hint=medium.primary_document_hint,
            transcript_hint=medium.transcript_hint,
        )

        if source.asset_class is AssetClass.PRIMARY_DOCUMENT and not medium.primary_document_hint:
            medium = resolve_medium(
                record,
                bundle,
                resolved_title=resolved_title,
                asset_hint=source.asset_class,
            )

        publication = resolve_publication(record, bundle)
        genre, genre_confidence, genre_evidence = resolve_genre(
            record,
            bundle,
            title=resolved_title,
            medium=medium.medium,
            asset_class=source.asset_class,
        )

        author = normalize_space(bundle.raw_author)
        if not author:
            author = _author_from_body(bundle.body_markdown or bundle.body_text)

        evidence: list[Evidence] = []
        evidence.extend(title_evidence)
        evidence.extend(publication.evidence)
        evidence.extend(medium.evidence)
        evidence.extend(source.evidence)
        evidence.extend(genre_evidence)
        if author:
            evidence.append(
                make_evidence(
                    record.item_id,
                    "author",
                    "resolved_author",
                    author,
                    confidence=0.82,
                    extractor=CANONICAL_SERVICE_VERSION,
                )
            )

        content_id = hashlib.sha256(
            source.canonical_content_url.encode("utf-8")
        ).hexdigest()[:20]
        confidence_by_field = {
            "title": title_confidence,
            "publication": publication.confidence,
            "source": source.confidence,
            "page_surface": medium.confidence,
            "main_content_medium": medium.confidence,
            "editorial_genre": genre_confidence,
        }
        freshness_facts = {
            "published_at_source": publication.source,
            "legacy_freshness_track": text(
                nested(metadata, "freshness", "freshness_track")
            ),
            "legacy_freshness_age_days": nested(
                metadata, "freshness", "freshness_age_days"
            ),
            "policy_applied": False,
        }

        return CanonicalArticle(
            schema_version="v06-contracts-v1",
            stage_version=CANONICAL_SERVICE_VERSION,
            run_id=context.run_id,
            item_id=record.item_id,
            content_id=content_id,
            display_url=record.url,
            canonical_content_url=source.canonical_content_url,
            resolved_title=resolved_title,
            resolved_author=author,
            published_at=publication.value,
            published_at_confidence=publication.confidence,
            publisher=source.canonical_source,
            hosting_source=source.hosting_source,
            canonical_source=source.canonical_source,
            original_publisher=source.original_publisher,
            source_relationship=source.relationship,
            source_action=source.action,
            page_surface=medium.page_surface,
            main_content_medium=medium.medium,
            editorial_genre=genre,
            asset_class=source.asset_class,
            duplicate_cluster_id=text(
                nested(metadata, "terminal_state", "content_cluster_id")
            ),
            freshness_facts=freshness_facts,
            confidence_by_field=confidence_by_field,
            evidence=tuple(evidence),
        )


def _resolve_title(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> tuple[str, float, tuple[Evidence, ...]]:
    raw = normalize_space(bundle.raw_title or record.title_hint)
    heading = normalize_space(body_heading(record.raw_metadata))
    similarity = nested(record.raw_metadata, "content_identity", "title_similarity")
    try:
        similarity_value = float(similarity)
    except (TypeError, ValueError):
        similarity_value = 1.0 if raw and heading and raw == heading else 0.0

    use_heading = bool(
        heading
        and (
            not raw
            or similarity_value < 0.45
            or _looks_like_site_title(raw)
        )
    )
    if use_heading:
        title, confidence, reason = heading, 0.96, "body_heading_overrides_host_title"
    elif raw:
        title, confidence, reason = raw, 0.90, "acquisition_or_discovery_title"
    elif heading:
        title, confidence, reason = heading, 0.90, "body_heading_only"
    else:
        title, confidence, reason = "", 0.0, "missing_title"

    evidence = (
        make_evidence(
            record.item_id,
            "title_resolution",
            "resolved_title",
            title,
            confidence=confidence,
            excerpt=reason,
            extractor=CANONICAL_SERVICE_VERSION,
        ),
    )
    return title, confidence, evidence


def _looks_like_site_title(value: str) -> bool:
    if len(value) > 45:
        return False
    return bool(
        re.search(
            r"(?:委员会办公室|委員會辦公室|人民政府|人民银行|人民銀行|官方网站|官方網站)$",
            value,
        )
    )


def _author_from_body(body: str) -> str:
    sample = body[:10000]
    patterns = (
        r"(?:文|採訪|采访|現場採訪|现场采访)(?:、攝影|、摄影)?\s*[／/：:]\s*([^\n]{2,30})",
        r"^\s*(?:作者|記者|记者)\s*[：:]\s*([^\n]{2,30})",
    )
    for pattern in patterns:
        match = re.search(pattern, sample, flags=re.MULTILINE)
        if match:
            return normalize_space(match.group(1))
    return ""


__all__ = ["CANONICAL_SERVICE_VERSION", "CanonicalArticleResolver"]
