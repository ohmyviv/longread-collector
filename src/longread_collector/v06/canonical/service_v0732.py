"""PR-7.3.2 Canonical Article wrapper for natural-run L4 follow-ups.

This layer is intentionally narrow: PR-7.3.1 date provenance remains the base,
while PR-7.3.2 adds a tight title-local absolute datetime cue and explicit
original-source body links. L5/L6 semantics remain unchanged.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib

from ..contracts import AcquisitionBundle, AssetClass, CanonicalArticle, ContentMedium, DiscoveryRecord, RunContext
from .header_evidence_v073 import enrich_header_publication_evidence
from .publication_v0732 import PUBLICATION_VERSION, resolve_publication
from .service_v0731 import (
    CanonicalArticleResolver as _PR731CanonicalArticleResolver,
    _age_days,
    _strip_demoted_url_date_projections,
)
from .source_resolution_v0732 import SOURCE_VERSION, resolve_source

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr7.3.2"


class CanonicalArticleResolver(_PR731CanonicalArticleResolver):
    """Resolve PR-7.3.2 L4 date/source evidence over the PR-7.3.1 base."""

    stage_version = CANONICAL_SERVICE_VERSION

    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle:
        base = super().canonicalize(context, record, bundle)

        publication_record = enrich_header_publication_evidence(record, bundle)
        publication_record, publication_bundle = _strip_demoted_url_date_projections(
            publication_record,
            bundle,
        )
        publication = resolve_publication(publication_record, publication_bundle)
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

        facts = dict(base.freshness_facts)
        facts.update(
            {
                "published_at_source": publication.source,
                "publication_conflict": publication.conflict,
                "publication_conflict_values": publication.conflict_values,
                "resolved_freshness_age_days": _age_days(context, publication.value),
                "publication_calibration_version": PUBLICATION_VERSION,
                "publication_evidence_status": publication.status,
                "publication_evidence_profile": publication.evidence_profile,
                "policy_applied": False,
            }
        )

        confidence = dict(base.confidence_by_field)
        confidence["publication"] = publication.confidence
        confidence["source"] = source.confidence

        evidence = tuple(
            item
            for item in base.evidence
            if not item.extractor.startswith("canonical-publication-")
            and not item.extractor.startswith("canonical-source-")
        )
        evidence += publication.evidence
        evidence += source.evidence

        canonical_url = source.canonical_content_url or base.canonical_content_url or record.url
        content_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]

        return replace(
            base,
            stage_version=CANONICAL_SERVICE_VERSION,
            content_id=content_id,
            canonical_content_url=canonical_url,
            published_at=publication.value,
            published_at_confidence=publication.confidence,
            publisher=source.canonical_source,
            hosting_source=source.hosting_source,
            canonical_source=source.canonical_source,
            original_publisher=source.original_publisher,
            source_relationship=source.relationship,
            source_action=source.action,
            freshness_facts=facts,
            confidence_by_field=confidence,
            evidence=evidence,
        )


__all__ = ["CANONICAL_SERVICE_VERSION", "CanonicalArticleResolver", "SOURCE_VERSION"]
