"""Offline E1 factual identity resolver for Standard Longread Eligibility.

E1 deliberately sits above L4 facts and below editorial scoring.  It only
applies narrow, high-confidence product-identity cues that can be replayed
without network or Sheets access.  It is not wired into the Collector runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from longread_collector.v06.contracts import CanonicalArticle
from longread_collector.v06.eligibility import (
    EligibilityEvidence,
    EligibilityReason,
    StandardLongreadDisposition,
    StandardLongreadEligibility,
    evaluate_standard_longread_eligibility,
)

E1_ELIGIBILITY_VERSION = "standard-longread-eligibility-v0.6-e1"


class E1IdentityKind(StrEnum):
    ACADEMIC_PAPER = "academic_paper"
    RECURRING_BRIEFING = "recurring_briefing"
    VIDEO_PAGE = "video_page"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class E1IdentityEvidence:
    """Minimal replayable facts used by E1.

    ``explicit_video_page`` must come from an upstream page/medium observation.
    E1 never infers video identity from publisher, title, or the mere presence of
    an embedded player.
    """

    url: str
    title: str
    source: str = ""
    author: str = ""
    explicit_video_page: bool | None = None


@dataclass(frozen=True, slots=True)
class E1IdentityResolution:
    kind: E1IdentityKind
    confidence: float
    reason_code: str

    @property
    def resolved(self) -> bool:
        return self.kind is not E1IdentityKind.UNRESOLVED


_GUARDIAN_DAY_BRIEFING_RE = re.compile(
    r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+briefing\s*:",
    re.IGNORECASE,
)


def _normalized_host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def resolve_e1_identity(evidence: E1IdentityEvidence) -> E1IdentityResolution:
    """Resolve only high-confidence non-standard product identities.

    The ordering is intentional: explicit page evidence is strongest; exact
    academic URL identity is next; recurring briefing identity requires both a
    Guardian identity and a day-specific briefing title.  Everything else
    abstains.
    """

    if evidence.explicit_video_page is True:
        return E1IdentityResolution(
            kind=E1IdentityKind.VIDEO_PAGE,
            confidence=0.99,
            reason_code="explicit_video_page_evidence",
        )

    parts = urlsplit(evidence.url)
    host = _normalized_host(evidence.url)
    path = parts.path.lower()
    if host == "arxiv.org" and (
        path.startswith("/abs/")
        or path.startswith("/pdf/")
        or path.startswith("/html/")
    ):
        return E1IdentityResolution(
            kind=E1IdentityKind.ACADEMIC_PAPER,
            confidence=0.995,
            reason_code="arxiv_academic_document_url",
        )

    guardian_identity = (
        host == "theguardian.com"
        or evidence.source.strip().lower() == "the guardian"
    )
    if guardian_identity and _GUARDIAN_DAY_BRIEFING_RE.search(evidence.title.strip()):
        return E1IdentityResolution(
            kind=E1IdentityKind.RECURRING_BRIEFING,
            confidence=0.99,
            reason_code="guardian_day_briefing_identity",
        )

    return E1IdentityResolution(
        kind=E1IdentityKind.UNRESOLVED,
        confidence=0.0,
        reason_code="no_high_confidence_e1_identity",
    )


def _override_result(
    article: CanonicalArticle,
    evidence: EligibilityEvidence,
    disposition: StandardLongreadDisposition,
    reason: EligibilityReason,
) -> StandardLongreadEligibility:
    reasons = [reason]
    if evidence.substantive_length_chars is not None:
        reasons.append(EligibilityReason.LENGTH_MEASUREMENT_ONLY)
    return StandardLongreadEligibility(
        schema_version=article.schema_version,
        stage_version=E1_ELIGIBILITY_VERSION,
        run_id=article.run_id,
        item_id=article.item_id,
        disposition=disposition,
        reasons=tuple(reasons),
        length_measurement_observed=evidence.substantive_length_chars is not None,
        substantive_length_chars=evidence.substantive_length_chars,
        substantive_length_source=evidence.substantive_length_source,
    )


def evaluate_standard_longread_eligibility_e1(
    article: CanonicalArticle,
    identity_evidence: E1IdentityEvidence,
    eligibility_evidence: EligibilityEvidence | None = None,
) -> StandardLongreadEligibility:
    """Apply E1 identity resolution, falling back losslessly to E0.

    An unresolved E1 identity returns the ordinary E0 evaluation unchanged,
    including its E0 stage version.  This makes abstention auditable and avoids
    pretending that E1 supplied evidence where it did not.
    """

    eligibility_evidence = eligibility_evidence or EligibilityEvidence()
    resolved = resolve_e1_identity(identity_evidence)

    if resolved.kind is E1IdentityKind.ACADEMIC_PAPER:
        return _override_result(
            article,
            eligibility_evidence,
            StandardLongreadDisposition.ROUTE_SPECIAL,
            EligibilityReason.ACADEMIC_ASSET,
        )
    if resolved.kind is E1IdentityKind.RECURRING_BRIEFING:
        return _override_result(
            article,
            eligibility_evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.ROUNDUP_IDENTITY,
        )
    if resolved.kind is E1IdentityKind.VIDEO_PAGE:
        return _override_result(
            article,
            eligibility_evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.VIDEO_MEDIUM,
        )

    return evaluate_standard_longread_eligibility(article, eligibility_evidence)


__all__ = [
    "E1_ELIGIBILITY_VERSION",
    "E1IdentityEvidence",
    "E1IdentityKind",
    "E1IdentityResolution",
    "evaluate_standard_longread_eligibility_e1",
    "resolve_e1_identity",
]
