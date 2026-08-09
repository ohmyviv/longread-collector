"""PR-7.3 Canonical Article wrapper for L4 evidence resolution.

PR-7.1 publication safety remains the compatibility baseline. PR-7.3 enriches
publication evidence and source relationships without changing L5 Editorial
Judge semantics.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from email.utils import parsedate_to_datetime
import hashlib

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    DiscoveryRecord,
    RunContext,
)
from .header_evidence_v073 import (
    demoted_url_publication_value,
    enrich_header_publication_evidence,
)
from .publication_v073 import (
    PUBLICATION_VERSION,
    normalize_publication_date,
    resolve_publication,
)
from .service_v071 import CanonicalArticleResolver as _PR71CanonicalArticleResolver
from .source_resolution_v073 import SOURCE_VERSION, resolve_source

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr7.3"


class CanonicalArticleResolver(_PR71CanonicalArticleResolver):
    """Resolve L4 date evidence and source relationships over PR-7.1."""

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

        # PR-7.3 is evidence-authoritative. If the richer resolver cannot
        # establish an initial publication fact, keep it unknown. Do not revive
        # PR-7.1's aggregate result after PR-7.3 has deliberately demoted the
        # underlying evidence (for example a URL-path date or republication
        # timestamp) to contextual-only.
        published_at = publication.value
        published_confidence = publication.confidence
        published_source = publication.source

        facts = dict(base.freshness_facts)
        facts.update(
            {
                "published_at_source": published_source,
                "publication_conflict": publication.conflict,
                "publication_conflict_values": publication.conflict_values,
                "resolved_freshness_age_days": _age_days(context, published_at),
                "publication_calibration_version": PUBLICATION_VERSION,
                "publication_evidence_status": publication.status,
                "publication_evidence_profile": publication.evidence_profile,
                "policy_applied": False,
            }
        )

        confidence = dict(base.confidence_by_field)
        confidence["publication"] = published_confidence
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
            published_at=published_at,
            published_at_confidence=published_confidence,
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


def _strip_demoted_url_date_projections(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> tuple[DiscoveryRecord, AcquisitionBundle]:
    """Remove adapter copies of a known URL-derived legacy publication fact.

    Legacy/full-parallel adapters flatten resolved publication dates into both
    discovery hints and acquisition raw dates. Once PR-7.3 has identified that
    aggregate as URL-derived, those generic copies must not silently regain
    selectable acquisition/discovery provenance. Independent dates with a
    different normalized value remain untouched; article-local/page evidence is
    collected through its own explicit paths.
    """

    demoted = demoted_url_publication_value(record)
    target = _publication_projection_key(demoted)
    if not target:
        return record, bundle

    published_at_hints = tuple(
        value
        for value in record.published_at_hints
        if _publication_projection_key(value) != target
    )
    raw_dates = tuple(
        value
        for value in bundle.raw_dates
        if _publication_projection_key(value) != target
    )

    if published_at_hints != record.published_at_hints:
        record = replace(record, published_at_hints=published_at_hints)
    if raw_dates != bundle.raw_dates:
        bundle = replace(bundle, raw_dates=raw_dates)
    return record, bundle


def _publication_projection_key(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    return normalize_publication_date(raw) or raw


def _age_days(context: RunContext, published_at: str) -> int | None:
    published = _parse_date(published_at)
    run_time = _parse_date(context.started_at_bj or context.scheduled_at_bj)
    if published is None or run_time is None:
        return None
    return max(0, (run_time.date() - published.date()).days)


def _parse_date(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    normalized_date = normalize_publication_date(raw)
    if normalized_date:
        try:
            return datetime.fromisoformat(normalized_date)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None


__all__ = ["CANONICAL_SERVICE_VERSION", "CanonicalArticleResolver", "SOURCE_VERSION"]
