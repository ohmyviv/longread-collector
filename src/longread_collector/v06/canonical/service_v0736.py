"""PR-7.3.6 Canonical Article wrapper for source identity corrections.

PR-7.3.6 remains L4-only. It preserves PR-7.3.3 publication semantics and the
PR-7.3.4 page-surface recovery while re-resolving only source identity and
source relationship from already-acquired evidence. L5/L6 remain unchanged.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib

from ..contracts import AcquisitionBundle, AssetClass, CanonicalArticle, ContentMedium, DiscoveryRecord, RunContext
from .service_v0734 import CanonicalArticleResolver as _PR734CanonicalArticleResolver
from .source_resolution_v0736 import SOURCE_VERSION, resolve_source

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr7.3.6"


class CanonicalArticleResolver(_PR734CanonicalArticleResolver):
    """Resolve PR-7.3.6 source facts over the PR-7.3.4 L4 base."""

    stage_version = CANONICAL_SERVICE_VERSION

    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle:
        base = super().canonicalize(context, record, bundle)

        source = resolve_source(
            record,
            bundle,
            resolved_title=base.resolved_title,
            primary_document_hint=(
                base.asset_class is AssetClass.PRIMARY_DOCUMENT
                or base.main_content_medium is ContentMedium.PRIMARY_DOCUMENT
            ),
            transcript_hint=(
                base.asset_class is AssetClass.TRANSCRIPT
                or base.main_content_medium
                in {
                    ContentMedium.TELEVISION_TRANSCRIPT,
                    ContentMedium.PODCAST_TRANSCRIPT,
                }
            ),
        )

        confidence = dict(base.confidence_by_field)
        confidence["source"] = source.confidence

        evidence = tuple(
            item
            for item in base.evidence
            if not item.extractor.startswith("canonical-source-")
        )
        evidence += source.evidence

        canonical_url = source.canonical_content_url or base.canonical_content_url or record.url
        content_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]

        return replace(
            base,
            stage_version=CANONICAL_SERVICE_VERSION,
            content_id=content_id,
            canonical_content_url=canonical_url,
            publisher=source.canonical_source,
            hosting_source=source.hosting_source,
            canonical_source=source.canonical_source,
            original_publisher=source.original_publisher,
            source_relationship=source.relationship,
            source_action=source.action,
            confidence_by_field=confidence,
            evidence=evidence,
        )


__all__ = ["CANONICAL_SERVICE_VERSION", "CanonicalArticleResolver", "SOURCE_VERSION"]
