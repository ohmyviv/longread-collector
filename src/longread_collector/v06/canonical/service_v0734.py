"""PR-7.3.4 Canonical Article wrapper for listing-surface recovery.

PR-7.3.4 remains L4-only. It preserves PR-7.3.3 publication/source behavior and
adds a narrow page-surface correction for explicit multi-article newspaper issue
containers. L5/L6 semantics remain unchanged.
"""

from __future__ import annotations

from dataclasses import replace

from ..contracts import AcquisitionBundle, CanonicalArticle, DiscoveryRecord, RunContext
from .service_v0733 import CanonicalArticleResolver as _PR733CanonicalArticleResolver
from .surface_v0734 import SURFACE_VERSION, recover_newspaper_issue_listing

CANONICAL_SERVICE_VERSION = "canonical-article-resolver-v0.6-pr7.3.4"


class CanonicalArticleResolver(_PR733CanonicalArticleResolver):
    """Resolve PR-7.3.4 page surface over the PR-7.3.3 L4 base."""

    stage_version = CANONICAL_SERVICE_VERSION

    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle:
        base = super().canonicalize(context, record, bundle)
        recovery = recover_newspaper_issue_listing(record, bundle, base)
        if recovery is None:
            return replace(base, stage_version=CANONICAL_SERVICE_VERSION)

        confidence = dict(base.confidence_by_field)
        confidence["page_surface"] = recovery.confidence
        confidence["main_content_medium"] = recovery.confidence

        # The PR-2 medium resolver emitted one terminal medium_resolution item
        # for written_article. Preserve its body/video metric evidence but remove
        # the superseded terminal classification before appending the explicit
        # listing override.
        evidence = tuple(
            item for item in base.evidence if item.evidence_type != "medium_resolution"
        )
        evidence += recovery.evidence

        return replace(
            base,
            stage_version=CANONICAL_SERVICE_VERSION,
            page_surface=recovery.page_surface,
            main_content_medium=recovery.main_content_medium,
            confidence_by_field=confidence,
            evidence=evidence,
        )


__all__ = [
    "CANONICAL_SERVICE_VERSION",
    "CanonicalArticleResolver",
    "SURFACE_VERSION",
]
