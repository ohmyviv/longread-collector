"""PR-7.1 compatibility wrapper for Canonical Article resolution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..contracts import AcquisitionBundle, CanonicalArticle, DiscoveryRecord, RunContext
from .publication_v071 import PUBLICATION_VERSION, normalize_publication_date, resolve_publication
from .service import CanonicalArticleResolver as _BaseCanonicalArticleResolver

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr7.1"


class CanonicalArticleResolver(_BaseCanonicalArticleResolver):
    """Preserve PR-2 canonical facts and calibrate publication evidence only."""

    stage_version = CANONICAL_SERVICE_VERSION

    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle:
        base = super().canonicalize(context, record, bundle)
        publication = resolve_publication(record, bundle)

        facts = dict(base.freshness_facts)
        facts.update(
            {
                "published_at_source": publication.source,
                "publication_conflict": publication.conflict,
                "publication_conflict_values": publication.conflict_values,
                "resolved_freshness_age_days": _age_days(
                    context, publication.value
                ),
                "publication_calibration_version": PUBLICATION_VERSION,
                "policy_applied": False,
            }
        )

        evidence = tuple(
            item
            for item in base.evidence
            if item.evidence_type != "publication_date"
        ) + publication.evidence

        confidence = dict(base.confidence_by_field)
        confidence["publication"] = publication.confidence

        return replace(
            base,
            stage_version=CANONICAL_SERVICE_VERSION,
            published_at=publication.value,
            published_at_confidence=publication.confidence,
            freshness_facts=facts,
            confidence_by_field=confidence,
            evidence=evidence,
        )


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


__all__ = ["CANONICAL_SERVICE_VERSION", "CanonicalArticleResolver"]
