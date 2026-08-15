"""Offline E2 substantive-length and structural-measurement contract.

E2 is measurement-first.  It records whether a length observation is trustworthy
enough to support future analysis, but it does not define or apply a production
Standard Longread length threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

E2_MEASUREMENT_VERSION = "standard-longread-eligibility-v0.6-e2-measurement"


class LengthEvidenceQuality(StrEnum):
    TRUSTED_SUBSTANTIVE = "trusted_substantive"
    LEGACY_APPROXIMATE = "legacy_approximate"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SubstantiveLengthEvidence:
    """Provenance for a body-length observation.

    ``chars`` is useful only together with provenance.  Historical
    ``body_chars_read`` values should normally be marked ``legacy_approximate``
    because the old field does not prove clean boilerplate removal, complete
    body capture, or absence of truncation.
    """

    chars: int | None
    source: str
    body_complete: bool | None = None
    extraction_truncated: bool | None = None
    boilerplate_removed: bool | None = None
    paragraph_count: int | None = None
    heading_count: int | None = None
    prose_ratio: float | None = None
    legacy_body_chars_read: bool = False

    def __post_init__(self) -> None:
        if self.chars is not None and self.chars < 0:
            raise ValueError("chars must be non-negative")
        for name in ("paragraph_count", "heading_count"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.prose_ratio is not None and not 0.0 <= self.prose_ratio <= 1.0:
            raise ValueError("prose_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class E2MeasurementAssessment:
    version: str
    quality: LengthEvidenceQuality
    chars: int | None
    source: str
    hard_gate_eligible: bool
    structural_measurement_observed: bool
    reason_code: str


def assess_e2_measurement(
    evidence: SubstantiveLengthEvidence,
) -> E2MeasurementAssessment:
    """Assess measurement trustworthiness without classifying article length."""

    structural_observed = any(
        value is not None
        for value in (
            evidence.paragraph_count,
            evidence.heading_count,
            evidence.prose_ratio,
        )
    )

    if evidence.chars is None:
        return E2MeasurementAssessment(
            version=E2_MEASUREMENT_VERSION,
            quality=LengthEvidenceQuality.UNKNOWN,
            chars=None,
            source=evidence.source,
            hard_gate_eligible=False,
            structural_measurement_observed=structural_observed,
            reason_code="length_not_observed",
        )

    if evidence.legacy_body_chars_read:
        return E2MeasurementAssessment(
            version=E2_MEASUREMENT_VERSION,
            quality=LengthEvidenceQuality.LEGACY_APPROXIMATE,
            chars=evidence.chars,
            source=evidence.source,
            hard_gate_eligible=False,
            structural_measurement_observed=structural_observed,
            reason_code="legacy_body_chars_read_provenance_incomplete",
        )

    if evidence.extraction_truncated is True or evidence.body_complete is False:
        return E2MeasurementAssessment(
            version=E2_MEASUREMENT_VERSION,
            quality=LengthEvidenceQuality.INCOMPLETE,
            chars=evidence.chars,
            source=evidence.source,
            hard_gate_eligible=False,
            structural_measurement_observed=structural_observed,
            reason_code="body_incomplete_or_truncated",
        )

    if (
        evidence.body_complete is True
        and evidence.extraction_truncated is False
        and evidence.boilerplate_removed is True
    ):
        return E2MeasurementAssessment(
            version=E2_MEASUREMENT_VERSION,
            quality=LengthEvidenceQuality.TRUSTED_SUBSTANTIVE,
            chars=evidence.chars,
            source=evidence.source,
            hard_gate_eligible=True,
            structural_measurement_observed=structural_observed,
            reason_code="complete_clean_substantive_body",
        )

    return E2MeasurementAssessment(
        version=E2_MEASUREMENT_VERSION,
        quality=LengthEvidenceQuality.UNKNOWN,
        chars=evidence.chars,
        source=evidence.source,
        hard_gate_eligible=False,
        structural_measurement_observed=structural_observed,
        reason_code="length_provenance_not_sufficient_for_hard_gate",
    )


__all__ = [
    "E2_MEASUREMENT_VERSION",
    "E2MeasurementAssessment",
    "LengthEvidenceQuality",
    "SubstantiveLengthEvidence",
    "assess_e2_measurement",
]
