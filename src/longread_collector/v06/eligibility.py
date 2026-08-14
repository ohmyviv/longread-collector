"""Offline Standard Longread Eligibility contract.

This module deliberately has no production wiring.  It separates product-class
eligibility from L4 factual resolution, L5 editorial value, and L6 portfolio
selection so those stages do not compensate for one another.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from longread_collector.v06.contracts import (
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    PageSurface,
)

ELIGIBILITY_VERSION = "standard-longread-eligibility-v0.6-e0"


class StandardLongreadDisposition(StrEnum):
    """Product-class disposition before editorial value is considered."""

    ELIGIBLE_STANDARD = "eligible_standard"
    ROUTE_SPECIAL = "route_special"
    INELIGIBLE_STANDARD = "ineligible_standard"
    UNKNOWN = "unknown"


class EligibilityReason(StrEnum):
    """Stable audit reason codes for the E0 offline contract."""

    STANDARD_WRITTEN_ARTICLE = "standard_written_article"
    NON_ARTICLE_SURFACE = "non_article_surface"
    ROUNDUP_IDENTITY = "roundup_identity"
    ACADEMIC_ASSET = "academic_asset"
    PRIMARY_DOCUMENT_ASSET = "primary_document_asset"
    VIDEO_MEDIUM = "video_medium"
    DATA_OR_EVENT_MEDIUM = "data_or_event_medium"
    PAYWALL_OR_UNKNOWN_SURFACE = "paywall_or_unknown_surface"
    UNRESOLVED_MEDIUM_OR_ASSET = "unresolved_medium_or_asset"
    LENGTH_MEASUREMENT_ONLY = "length_measurement_only"


@dataclass(frozen=True, slots=True)
class EligibilityEvidence:
    """Evidence that is product-specific rather than an editorial score.

    ``roundup_identity`` is intentionally an explicit upstream fact.  E0 does
    not infer it from a source name or title; a later factual resolver can own
    that inference.

    ``substantive_length_chars`` is measurement-only in E0.  Human calibration
    on the 80-item retrospective set showed that the historical
    ``body_chars_read`` field is not safe as a direct hard threshold, so E0
    records length provenance but never rejects on length alone.
    """

    roundup_identity: bool | None = None
    substantive_length_chars: int | None = None
    substantive_length_source: str = ""

    def __post_init__(self) -> None:
        if self.substantive_length_chars is not None and self.substantive_length_chars < 0:
            raise ValueError("substantive_length_chars must be non-negative")


@dataclass(frozen=True, slots=True)
class StandardLongreadEligibility:
    schema_version: str
    stage_version: str
    run_id: str
    item_id: str
    disposition: StandardLongreadDisposition
    reasons: tuple[EligibilityReason, ...]
    length_measurement_observed: bool = False
    substantive_length_chars: int | None = None
    substantive_length_source: str = ""

    @property
    def eligible_for_standard(self) -> bool:
        return self.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD


def _result(
    article: CanonicalArticle,
    evidence: EligibilityEvidence,
    disposition: StandardLongreadDisposition,
    *reasons: EligibilityReason,
) -> StandardLongreadEligibility:
    reason_list = list(reasons)
    if evidence.substantive_length_chars is not None:
        reason_list.append(EligibilityReason.LENGTH_MEASUREMENT_ONLY)
    return StandardLongreadEligibility(
        schema_version=article.schema_version,
        stage_version=ELIGIBILITY_VERSION,
        run_id=article.run_id,
        item_id=article.item_id,
        disposition=disposition,
        reasons=tuple(reason_list),
        length_measurement_observed=evidence.substantive_length_chars is not None,
        substantive_length_chars=evidence.substantive_length_chars,
        substantive_length_source=evidence.substantive_length_source,
    )


def evaluate_standard_longread_eligibility(
    article: CanonicalArticle,
    evidence: EligibilityEvidence | None = None,
) -> StandardLongreadEligibility:
    """Evaluate Standard Longread product eligibility without editorial scoring.

    E0 is intentionally high precision.  It only makes hard product decisions
    from facts whose responsibility is already clear.  In particular, it does
    *not* apply a prose/character hard floor.
    """

    evidence = evidence or EligibilityEvidence()

    non_article_surfaces = {
        PageSurface.EXTERNAL_LINK_STUB,
        PageSurface.LISTING,
        PageSurface.HOMEPAGE,
        PageSurface.LOGIN,
        PageSurface.CAPTCHA,
        PageSurface.SOCIAL_POST,
    }
    if article.page_surface in non_article_surfaces:
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.NON_ARTICLE_SURFACE,
        )

    if evidence.roundup_identity is True:
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.ROUNDUP_IDENTITY,
        )

    if (
        article.asset_class is AssetClass.ACADEMIC_PAPER
        or article.main_content_medium is ContentMedium.ACADEMIC_PAPER
    ):
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.ROUTE_SPECIAL,
            EligibilityReason.ACADEMIC_ASSET,
        )

    if (
        article.asset_class is AssetClass.PRIMARY_DOCUMENT
        or article.main_content_medium is ContentMedium.PRIMARY_DOCUMENT
    ):
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.ROUTE_SPECIAL,
            EligibilityReason.PRIMARY_DOCUMENT_ASSET,
        )

    if article.main_content_medium is ContentMedium.VIDEO_PAGE:
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.VIDEO_MEDIUM,
        )

    if article.main_content_medium in {
        ContentMedium.DATA_CARD,
        ContentMedium.EVENT_LISTING,
    }:
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.INELIGIBLE_STANDARD,
            EligibilityReason.DATA_OR_EVENT_MEDIUM,
        )

    if article.page_surface in {PageSurface.PAYWALL, PageSurface.UNKNOWN}:
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.UNKNOWN,
            EligibilityReason.PAYWALL_OR_UNKNOWN_SURFACE,
        )

    if (
        article.page_surface is PageSurface.ARTICLE_PAGE
        and article.main_content_medium is ContentMedium.WRITTEN_ARTICLE
        and article.asset_class is AssetClass.MEDIA_ARTICLE
    ):
        return _result(
            article,
            evidence,
            StandardLongreadDisposition.ELIGIBLE_STANDARD,
            EligibilityReason.STANDARD_WRITTEN_ARTICLE,
        )

    return _result(
        article,
        evidence,
        StandardLongreadDisposition.UNKNOWN,
        EligibilityReason.UNRESOLVED_MEDIUM_OR_ASSET,
    )
