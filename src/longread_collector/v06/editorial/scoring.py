"""Deterministic continuous scoring for the v0.6 PR-3 Editorial Judge."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import (
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    EditorialGenre,
    EditorialVerdict,
)
from .features import EditorialFeatures


SCORING_VERSION = "editorial-scoring-v0.6-pr3"


@dataclass(frozen=True, slots=True)
class EditorialScoreVector:
    substance: float
    original_reporting: float
    analysis: float
    argument: float
    evidence_density: float
    reader_value: float
    timeliness_relevance: float
    promotional_risk: float
    event_risk: float
    transcript_risk: float
    template_risk: float
    utility: float


def score_editorial(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> EditorialScoreVector:
    substance = _score_substance(article, features)
    original_reporting = _score_original_reporting(article, features)
    analysis = _score_analysis(article, features)
    argument = _score_argument(article, features)
    evidence_density = _score_evidence_density(article, features)

    promotional_risk = _score_promotional_risk(article, features)
    event_risk = _score_event_risk(article, features)
    transcript_risk = _score_transcript_risk(article, features)
    template_risk = _score_template_risk(article, features)

    reader_value = _score_reader_value(
        features,
        substance=substance,
        original_reporting=original_reporting,
        analysis=analysis,
        argument=argument,
        evidence_density=evidence_density,
        risks=(
            promotional_risk,
            event_risk,
            transcript_risk,
            template_risk,
        ),
    )
    timeliness_relevance = _score_timeliness(features.freshness_age_days)

    positive = (
        0.18 * substance
        + 0.17 * original_reporting
        + 0.17 * analysis
        + 0.12 * argument
        + 0.14 * evidence_density
        + 0.14 * reader_value
        + 0.08 * timeliness_relevance
    )
    risks = (
        promotional_risk,
        event_risk,
        transcript_risk,
        template_risk,
    )
    risk_penalty = 0.34 * max(risks) + 0.08 * (sum(risks) / len(risks))
    utility = _clamp(positive - risk_penalty)

    return EditorialScoreVector(
        substance=substance,
        original_reporting=original_reporting,
        analysis=analysis,
        argument=argument,
        evidence_density=evidence_density,
        reader_value=reader_value,
        timeliness_relevance=timeliness_relevance,
        promotional_risk=promotional_risk,
        event_risk=event_risk,
        transcript_risk=transcript_risk,
        template_risk=template_risk,
        utility=utility,
    )


def verdict_for(scores: EditorialScoreVector) -> EditorialVerdict:
    if scores.utility >= 0.68:
        return EditorialVerdict.RECOMMEND
    if scores.utility >= 0.48:
        return EditorialVerdict.CONSIDER
    if scores.utility >= 0.30:
        return EditorialVerdict.LOW_VALUE
    return EditorialVerdict.REJECT


def editorial_value_for(verdict: EditorialVerdict) -> str:
    if verdict is EditorialVerdict.RECOMMEND:
        return "high"
    if verdict is EditorialVerdict.CONSIDER:
        return "medium"
    if verdict is EditorialVerdict.LOW_VALUE:
        return "low"
    if verdict is EditorialVerdict.REJECT:
        return "none"
    return "insufficient_evidence"


def _score_substance(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    length = _length_score(features.prose_chars)
    structure = 0.65 * _sat(features.paragraph_count, 12) + 0.35 * _sat(
        features.heading_count, 4
    )
    genre_bonus = {
        EditorialGenre.INVESTIGATION: 0.98,
        EditorialGenre.REPORTED_FEATURE: 0.90,
        EditorialGenre.ANALYSIS: 0.96,
        EditorialGenre.COMMENTARY: 0.82,
        EditorialGenre.INTERVIEW: 0.94,
        EditorialGenre.BOOK_REVIEW: 0.90,
        EditorialGenre.POLICY_DOCUMENT: 0.84,
        EditorialGenre.INSTITUTIONAL_REPORT: 0.88,
        EditorialGenre.STRAIGHT_NEWS: 0.38,
        EditorialGenre.EVENT_PREVIEW: 0.45,
        EditorialGenre.EVENT_RECAP: 0.45,
        EditorialGenre.PROMOTION: 0.38,
        EditorialGenre.MARKET_DATA: 0.28,
        EditorialGenre.UNKNOWN: 0.55,
    }.get(article.editorial_genre, 0.55)

    score = _clamp(0.62 * length + 0.20 * structure + 0.18 * genre_bonus)
    if article.asset_class is AssetClass.PRIMARY_DOCUMENT:
        score = max(score, 0.78)
    if article.asset_class is AssetClass.ACADEMIC_PAPER:
        score = max(score, 0.88)
    return score


def _score_original_reporting(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    signals = _sat(features.reporting_signal_count, 5)
    attribution = _sat(features.attribution_count, 6)

    if article.editorial_genre is EditorialGenre.INVESTIGATION:
        base = 0.96
    elif article.editorial_genre is EditorialGenre.INTERVIEW:
        base = 0.92
    elif article.editorial_genre is EditorialGenre.REPORTED_FEATURE:
        # PR-2 deliberately uses REPORTED_FEATURE as a broad narrative fallback.
        # Require observed reporting signals before granting a high reporting score.
        base = 0.28 + 0.52 * signals
    elif article.editorial_genre is EditorialGenre.STRAIGHT_NEWS:
        base = 0.42
    elif article.editorial_genre in {
        EditorialGenre.ANALYSIS,
        EditorialGenre.COMMENTARY,
        EditorialGenre.BOOK_REVIEW,
    }:
        base = 0.12
    else:
        base = 0.08

    if article.asset_class in {
        AssetClass.PRIMARY_DOCUMENT,
        AssetClass.ACADEMIC_PAPER,
        AssetClass.INSTITUTIONAL_REPORT,
    }:
        base = min(base, 0.18)

    return _clamp(0.68 * base + 0.22 * signals + 0.10 * attribution)


def _score_analysis(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    cue_score = _sat(features.analysis_signal_count, 7)
    base = {
        EditorialGenre.INVESTIGATION: 0.72,
        EditorialGenre.REPORTED_FEATURE: 0.42,
        EditorialGenre.ANALYSIS: 0.92,
        EditorialGenre.COMMENTARY: 0.86,
        EditorialGenre.INTERVIEW: 0.52,
        EditorialGenre.BOOK_REVIEW: 0.80,
        EditorialGenre.POLICY_DOCUMENT: 0.55,
        EditorialGenre.INSTITUTIONAL_REPORT: 0.68,
        EditorialGenre.STRAIGHT_NEWS: 0.22,
        EditorialGenre.EVENT_PREVIEW: 0.18,
        EditorialGenre.EVENT_RECAP: 0.22,
        EditorialGenre.PROMOTION: 0.10,
        EditorialGenre.MARKET_DATA: 0.14,
        EditorialGenre.UNKNOWN: 0.35,
    }.get(article.editorial_genre, 0.35)
    score = _clamp(0.72 * base + 0.28 * cue_score)

    if features.book_review_signal_count >= 2:
        score = max(score, 0.80)
    if article.asset_class is AssetClass.ACADEMIC_PAPER:
        score = max(score, 0.72)
    return score


def _score_argument(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    cue_score = _sat(features.argument_signal_count, 6)
    base = {
        EditorialGenre.INVESTIGATION: 0.58,
        EditorialGenre.REPORTED_FEATURE: 0.36,
        EditorialGenre.ANALYSIS: 0.82,
        EditorialGenre.COMMENTARY: 0.90,
        EditorialGenre.INTERVIEW: 0.42,
        EditorialGenre.BOOK_REVIEW: 0.88,
        EditorialGenre.POLICY_DOCUMENT: 0.42,
        EditorialGenre.INSTITUTIONAL_REPORT: 0.58,
        EditorialGenre.STRAIGHT_NEWS: 0.12,
        EditorialGenre.EVENT_PREVIEW: 0.10,
        EditorialGenre.EVENT_RECAP: 0.14,
        EditorialGenre.PROMOTION: 0.08,
        EditorialGenre.MARKET_DATA: 0.08,
        EditorialGenre.UNKNOWN: 0.25,
    }.get(article.editorial_genre, 0.25)
    score = _clamp(0.72 * base + 0.28 * cue_score)

    if features.book_review_signal_count >= 2:
        score = max(score, 0.84)
    if article.asset_class is AssetClass.ACADEMIC_PAPER:
        score = max(score, 0.62)
    return score


def _score_evidence_density(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    score = _clamp(
        0.34 * _sat(features.numeric_fact_count, 10)
        + 0.28 * _sat(features.attribution_count, 7)
        + 0.18 * _sat(features.quote_count, 4)
        + 0.20 * _sat(features.link_count, 5)
    )
    if article.asset_class is AssetClass.PRIMARY_DOCUMENT:
        score = max(score, 0.78)
    if article.asset_class is AssetClass.ACADEMIC_PAPER:
        score = max(score, 0.90)
    return score


def _score_reader_value(
    features: EditorialFeatures,
    *,
    substance: float,
    original_reporting: float,
    analysis: float,
    argument: float,
    evidence_density: float,
    risks: tuple[float, float, float, float],
) -> float:
    rhetoric_penalty = _sat(features.generic_rhetoric_count, 5)
    score = _clamp(
        0.26 * substance
        + 0.20 * original_reporting
        + 0.20 * analysis
        + 0.12 * argument
        + 0.14 * evidence_density
        + 0.08 * (1.0 - rhetoric_penalty)
    )
    return _clamp(score * (1.0 - 0.45 * max(risks)))


def _score_promotional_risk(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    if article.editorial_genre is EditorialGenre.PROMOTION:
        return 0.97

    count = features.promotion_signal_count
    if count >= 7:
        cue_risk = 0.94
    elif count >= 5:
        cue_risk = 0.82
    elif count >= 3:
        cue_risk = 0.58
    elif count >= 1:
        cue_risk = 0.24
    else:
        cue_risk = 0.05

    if features.title_has_promotion_signal and count >= 3:
        cue_risk = max(cue_risk, 0.78)
    return cue_risk


def _score_event_risk(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    if article.main_content_medium is ContentMedium.EVENT_LISTING:
        return 0.98
    if article.editorial_genre is EditorialGenre.EVENT_PREVIEW:
        return 0.96
    if article.editorial_genre is EditorialGenre.EVENT_RECAP:
        return 0.90

    count = features.event_signal_count
    if count >= 7:
        cue_risk = 0.94
    elif count >= 5:
        cue_risk = 0.82
    elif count >= 3:
        cue_risk = 0.58
    elif count >= 1:
        cue_risk = 0.22
    else:
        cue_risk = 0.04

    if features.title_has_event_signal and count >= 3:
        cue_risk = max(cue_risk, 0.84)
    return cue_risk


def _score_transcript_risk(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    if article.main_content_medium in {
        ContentMedium.TELEVISION_TRANSCRIPT,
        ContentMedium.PODCAST_TRANSCRIPT,
    }:
        return 0.98
    if article.asset_class is AssetClass.TRANSCRIPT:
        return 0.95

    count = features.transcript_signal_count
    if count >= 6:
        return 0.76
    if count >= 3:
        return 0.48
    if count >= 1:
        return 0.18
    return 0.03


def _score_template_risk(
    article: CanonicalArticle,
    features: EditorialFeatures,
) -> float:
    if article.main_content_medium is ContentMedium.DATA_CARD:
        return 0.98
    if features.market_template_signal_count >= 4:
        return 0.95
    if features.market_template_signal_count >= 2:
        return 0.75

    ratio_risk = _clamp((features.template_ratio - 0.58) / 0.35)
    return ratio_risk


def _score_timeliness(age_days: int | None) -> float:
    if age_days is None:
        return 0.50
    if age_days <= 3:
        return 1.00
    if age_days <= 7:
        return 0.86
    if age_days <= 14:
        return 0.66
    if age_days <= 30:
        return 0.38
    if age_days <= 90:
        return 0.16
    return 0.06


def _length_score(chars: int) -> float:
    value = max(0, int(chars))
    points = (
        (0, 0.05),
        (400, 0.12),
        (800, 0.22),
        (1200, 0.32),
        (2400, 0.52),
        (4000, 0.70),
        (7000, 0.86),
        (10000, 0.94),
    )
    if value >= 10000:
        return 0.97

    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= value < right_x:
            progress = (value - left_x) / (right_x - left_x)
            return left_y + progress * (right_y - left_y)
    return 0.05


def _sat(value: int | float, target: int | float) -> float:
    if target <= 0:
        return 0.0
    return _clamp(float(value) / float(target))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "EditorialScoreVector",
    "SCORING_VERSION",
    "editorial_value_for",
    "score_editorial",
    "verdict_for",
]
