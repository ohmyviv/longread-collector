"""Per-item policy evaluation for v0.6 PR-4.

This module translates Canonical Article facts and Editorial Judge assessments
into a provisional policy action. Portfolio capacity and diversity are applied
later by ``portfolio.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import (
    AssetClass,
    CanonicalArticle,
    EditorialAssessment,
    EditorialVerdict,
    PageSurface,
    PolicyAction,
    SelectionTrack,
    SourceAction,
)

POLICY_VERSION = "policy-v0.6-pr4"

_SOURCE_CHASE_ACTIONS = {
    SourceAction.FIND_ORIGINAL_ARTICLE,
    SourceAction.FIND_PRIMARY_DOCUMENT,
    SourceAction.REPLACE_WITH_ORIGINAL,
}


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    provisional_action: PolicyAction
    track: SelectionTrack
    base_utility: float
    risk_penalty: float
    freshness_penalty: float
    cost_penalty: float
    confidence_adjustment: float
    reason_code: str

    @property
    def pre_diversity_utility(self) -> float:
        return _clamp_signed(
            self.base_utility
            + self.confidence_adjustment
            - self.risk_penalty
            - self.freshness_penalty
            - self.cost_penalty
        )


def evaluate_policy(
    article: CanonicalArticle,
    assessment: EditorialAssessment,
    *,
    estimated_cost: float = 0.0,
) -> PolicyEvaluation:
    """Return a provisional policy action without consuming portfolio capacity."""
    chase = _needs_source_chase(article)

    if assessment.verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE:
        action = PolicyAction.SOURCE_CHASE if chase else PolicyAction.DEFER
        track = SelectionTrack.SOURCE_CHASE if chase else SelectionTrack.NONE
        return PolicyEvaluation(
            provisional_action=action,
            track=track,
            base_utility=0.0,
            risk_penalty=0.0,
            freshness_penalty=0.0,
            cost_penalty=_cost_penalty(estimated_cost),
            confidence_adjustment=0.0,
            reason_code=(
                "canonical_source_chase_required"
                if chase
                else "insufficient_editorial_evidence"
            ),
        )

    if assessment.verdict is EditorialVerdict.REJECT or _dominant_risk(assessment) >= 0.85:
        return PolicyEvaluation(
            provisional_action=PolicyAction.REJECT,
            track=SelectionTrack.NONE,
            base_utility=_positive_utility(article, assessment, SelectionTrack.NONE),
            risk_penalty=_risk_penalty(assessment),
            freshness_penalty=0.0,
            cost_penalty=_cost_penalty(estimated_cost),
            confidence_adjustment=_confidence_adjustment(assessment.confidence),
            reason_code="editorial_reject_or_dominant_risk",
        )

    if assessment.verdict is EditorialVerdict.LOW_VALUE:
        action = PolicyAction.REJECT if assessment.confidence >= 0.70 else PolicyAction.DEFER
        return PolicyEvaluation(
            provisional_action=action,
            track=SelectionTrack.NONE,
            base_utility=_positive_utility(article, assessment, SelectionTrack.NONE),
            risk_penalty=_risk_penalty(assessment),
            freshness_penalty=0.0,
            cost_penalty=_cost_penalty(estimated_cost),
            confidence_adjustment=_confidence_adjustment(assessment.confidence),
            reason_code=(
                "low_editorial_value_policy_reject"
                if action is PolicyAction.REJECT
                else "low_editorial_value_low_confidence_defer"
            ),
        )

    if chase:
        return PolicyEvaluation(
            provisional_action=PolicyAction.SOURCE_CHASE,
            track=SelectionTrack.SOURCE_CHASE,
            base_utility=_positive_utility(article, assessment, SelectionTrack.SOURCE_CHASE),
            risk_penalty=_risk_penalty(assessment),
            freshness_penalty=0.0,
            cost_penalty=_cost_penalty(estimated_cost),
            confidence_adjustment=_confidence_adjustment(assessment.confidence),
            reason_code="canonical_source_chase_required",
        )

    track, action = _selection_track(article)
    base = _positive_utility(article, assessment, track)
    risk = _risk_penalty(assessment)
    freshness = _freshness_penalty(assessment.timeliness_relevance_score, track)
    cost = _cost_penalty(estimated_cost)
    confidence = _confidence_adjustment(assessment.confidence)

    if assessment.confidence < 0.50:
        return PolicyEvaluation(
            provisional_action=PolicyAction.DEFER,
            track=track,
            base_utility=base,
            risk_penalty=risk,
            freshness_penalty=freshness,
            cost_penalty=cost,
            confidence_adjustment=confidence,
            reason_code="editorial_confidence_too_low",
        )

    return PolicyEvaluation(
        provisional_action=action,
        track=track,
        base_utility=base,
        risk_penalty=risk,
        freshness_penalty=freshness,
        cost_penalty=cost,
        confidence_adjustment=confidence,
        reason_code="eligible_for_portfolio",
    )


def _needs_source_chase(article: CanonicalArticle) -> bool:
    if article.source_action in _SOURCE_CHASE_ACTIONS:
        return True
    return article.page_surface is PageSurface.EXTERNAL_LINK_STUB


def _selection_track(article: CanonicalArticle) -> tuple[SelectionTrack, PolicyAction]:
    if article.asset_class is AssetClass.PRIMARY_DOCUMENT:
        return SelectionTrack.SPECIAL_DOCUMENT, PolicyAction.SELECT_SPECIAL
    if article.asset_class is AssetClass.ACADEMIC_PAPER:
        return SelectionTrack.ACADEMIC, PolicyAction.SELECT_SPECIAL
    return SelectionTrack.STANDARD_LONGREAD, PolicyAction.SELECT_STANDARD


def _positive_utility(
    article: CanonicalArticle,
    assessment: EditorialAssessment,
    track: SelectionTrack,
) -> float:
    if track in {SelectionTrack.SPECIAL_DOCUMENT, SelectionTrack.ACADEMIC} or article.asset_class in {
        AssetClass.PRIMARY_DOCUMENT,
        AssetClass.ACADEMIC_PAPER,
        AssetClass.INSTITUTIONAL_REPORT,
    }:
        weights = (0.22, 0.05, 0.20, 0.12, 0.20, 0.13, 0.08)
    else:
        weights = (0.20, 0.16, 0.14, 0.10, 0.14, 0.18, 0.08)
    values = (
        assessment.substance_score,
        assessment.original_reporting_score,
        assessment.analysis_score,
        assessment.argument_score,
        assessment.evidence_density_score,
        assessment.reader_value_score,
        assessment.timeliness_relevance_score,
    )
    return _clamp(sum(weight * float(value) for weight, value in zip(weights, values)))


def _risk_penalty(assessment: EditorialAssessment) -> float:
    penalty = (
        0.28 * assessment.promotional_risk
        + 0.26 * assessment.event_risk
        + 0.30 * assessment.transcript_risk
        + 0.18 * assessment.template_risk
    )
    return _clamp(min(0.72, penalty))


def _freshness_penalty(timeliness: float, track: SelectionTrack) -> float:
    missing = max(0.0, 1.0 - _clamp(timeliness))
    if track in {SelectionTrack.SPECIAL_DOCUMENT, SelectionTrack.ACADEMIC}:
        return 0.04 * (missing ** 1.2)
    return 0.12 * (missing ** 1.4)


def _cost_penalty(estimated_cost: float) -> float:
    return min(0.20, max(0.0, float(estimated_cost)) * 0.08)


def _confidence_adjustment(confidence: float) -> float:
    return max(-0.04, min(0.04, (float(confidence) - 0.70) * 0.12))


def _dominant_risk(assessment: EditorialAssessment) -> float:
    return max(
        assessment.promotional_risk,
        assessment.event_risk,
        assessment.transcript_risk,
        assessment.template_risk,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clamp_signed(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


__all__ = ["POLICY_VERSION", "PolicyEvaluation", "evaluate_policy"]