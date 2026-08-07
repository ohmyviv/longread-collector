"""Editorial value and risk judgment for v0.6 PR-3.

The judge consumes CanonicalArticle facts plus an AcquisitionBundle and emits a
continuous EditorialAssessment.  It does not write legacy candidate states or
selection policy.
"""

from __future__ import annotations

import hashlib
from statistics import mean

from ..contracts import (
    AcquisitionBundle,
    CanonicalArticle,
    EditorialAssessment,
    EditorialGenre,
    EditorialVerdict,
    Evidence,
    PageSurface,
    RunContext,
    StageName,
)
from .features import EditorialFeatures, extract_editorial_features
from .scoring import (
    EditorialScoreVector,
    editorial_value_for,
    score_editorial,
    verdict_for,
)


EDITORIAL_JUDGE_VERSION = "editorial-judge-v0.6-pr3"


class EditorialJudge:
    """Assess editorial value without making portfolio or compatibility decisions."""

    stage_version = EDITORIAL_JUDGE_VERSION

    def assess(
        self,
        context: RunContext,
        article: CanonicalArticle,
        bundle: AcquisitionBundle,
    ) -> EditorialAssessment:
        if _insufficient_for_judgment(article, bundle):
            return _insufficient_assessment(context, article, bundle)

        features = extract_editorial_features(context, article, bundle)
        scores = score_editorial(article, features)
        verdict = verdict_for(scores)
        confidence = _assessment_confidence(article, bundle, features)

        evidence = _score_evidence(article.item_id, scores, features)
        evidence += (
            _make_evidence(
                article.item_id,
                "editorial_verdict",
                "verdict",
                verdict.value,
                confidence=confidence,
                excerpt=(
                    f"utility={scores.utility:.3f}; "
                    f"max_risk={max(scores.promotional_risk, scores.event_risk, scores.transcript_risk, scores.template_risk):.3f}"
                ),
            ),
        )

        return EditorialAssessment(
            schema_version=article.schema_version,
            stage_version=EDITORIAL_JUDGE_VERSION,
            run_id=context.run_id,
            item_id=article.item_id,
            substance_score=scores.substance,
            original_reporting_score=scores.original_reporting,
            analysis_score=scores.analysis,
            argument_score=scores.argument,
            evidence_density_score=scores.evidence_density,
            reader_value_score=scores.reader_value,
            timeliness_relevance_score=scores.timeliness_relevance,
            promotional_risk=scores.promotional_risk,
            event_risk=scores.event_risk,
            transcript_risk=scores.transcript_risk,
            template_risk=scores.template_risk,
            editorial_value=editorial_value_for(verdict),
            verdict=verdict,
            confidence=confidence,
            evidence=evidence,
        )


def _insufficient_for_judgment(
    article: CanonicalArticle,
    bundle: AcquisitionBundle,
) -> bool:
    if not bundle.sufficient_for_editorial_judgment:
        return True
    if article.page_surface in {
        PageSurface.EXTERNAL_LINK_STUB,
        PageSurface.PAYWALL,
        PageSurface.LOGIN,
        PageSurface.CAPTCHA,
        PageSurface.LISTING,
        PageSurface.HOMEPAGE,
    }:
        return True
    body = bundle.body_markdown or bundle.body_text or ""
    prose_chars = max(0, int(bundle.prose_length or 0))
    if not prose_chars:
        prose_chars = len("".join(body.split()))
    return prose_chars < 250 and article.editorial_genre is EditorialGenre.UNKNOWN


def _insufficient_assessment(
    context: RunContext,
    article: CanonicalArticle,
    bundle: AcquisitionBundle,
) -> EditorialAssessment:
    evidence = (
        _make_evidence(
            article.item_id,
            "editorial_sufficiency",
            "verdict",
            EditorialVerdict.INSUFFICIENT_EVIDENCE.value,
            confidence=0.98,
            excerpt=(
                f"page_surface={article.page_surface.value}; "
                f"sufficient_for_editorial_judgment={bundle.sufficient_for_editorial_judgment}"
            ),
        ),
    )
    return EditorialAssessment(
        schema_version=article.schema_version,
        stage_version=EDITORIAL_JUDGE_VERSION,
        run_id=context.run_id,
        item_id=article.item_id,
        substance_score=0.0,
        original_reporting_score=0.0,
        analysis_score=0.0,
        argument_score=0.0,
        evidence_density_score=0.0,
        reader_value_score=0.0,
        timeliness_relevance_score=0.0,
        promotional_risk=0.0,
        event_risk=0.0,
        transcript_risk=0.0,
        template_risk=0.0,
        editorial_value="insufficient_evidence",
        verdict=EditorialVerdict.INSUFFICIENT_EVIDENCE,
        confidence=0.98,
        evidence=evidence,
    )


def _assessment_confidence(
    article: CanonicalArticle,
    bundle: AcquisitionBundle,
    features: EditorialFeatures,
) -> float:
    canonical_confidences = [
        float(value)
        for value in article.confidence_by_field.values()
        if isinstance(value, (int, float))
    ]
    canonical = mean(canonical_confidences) if canonical_confidences else 0.72
    body = 0.96 if bundle.sufficient_for_editorial_judgment else 0.35
    length = min(1.0, features.prose_chars / 2400) if features.prose_chars else 0.0

    ambiguity_penalty = 0.0
    if article.editorial_genre is EditorialGenre.UNKNOWN:
        ambiguity_penalty += 0.08
    if article.page_surface is PageSurface.UNKNOWN:
        ambiguity_penalty += 0.06

    return _clamp(0.45 * canonical + 0.35 * body + 0.20 * length - ambiguity_penalty)


def _score_evidence(
    item_id: str,
    scores: EditorialScoreVector,
    features: EditorialFeatures,
) -> tuple[Evidence, ...]:
    score_fields = (
        ("substance_score", scores.substance, f"prose_chars={features.prose_chars}; paragraphs={features.paragraph_count}; headings={features.heading_count}"),
        ("original_reporting_score", scores.original_reporting, f"reporting_signals={features.reporting_signal_count}; attributions={features.attribution_count}"),
        ("analysis_score", scores.analysis, f"analysis_signals={features.analysis_signal_count}"),
        ("argument_score", scores.argument, f"argument_signals={features.argument_signal_count}; book_review_signals={features.book_review_signal_count}"),
        ("evidence_density_score", scores.evidence_density, f"numeric_facts={features.numeric_fact_count}; attributions={features.attribution_count}; quotes={features.quote_count}; links={features.link_count}"),
        ("reader_value_score", scores.reader_value, f"generic_rhetoric={features.generic_rhetoric_count}"),
        ("timeliness_relevance_score", scores.timeliness_relevance, f"age_days={features.freshness_age_days}"),
        ("promotional_risk", scores.promotional_risk, f"promotion_signals={features.promotion_signal_count}; title_signal={features.title_has_promotion_signal}"),
        ("event_risk", scores.event_risk, f"event_signals={features.event_signal_count}; title_signal={features.title_has_event_signal}"),
        ("transcript_risk", scores.transcript_risk, f"transcript_signals={features.transcript_signal_count}"),
        ("template_risk", scores.template_risk, f"template_ratio={features.template_ratio:.3f}; market_template_signals={features.market_template_signal_count}"),
    )
    return tuple(
        _make_evidence(
            item_id,
            "editorial_score",
            field,
            round(value, 6),
            confidence=0.90,
            excerpt=excerpt,
        )
        for field, value, excerpt in score_fields
    )


def _make_evidence(
    item_id: str,
    evidence_type: str,
    field: str,
    value: object,
    *,
    confidence: float,
    excerpt: str = "",
) -> Evidence:
    seed = f"{item_id}|{evidence_type}|{field}|{value}"
    evidence_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return Evidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        source_stage=StageName.EDITORIAL,
        field=field,
        value=value,
        confidence=_clamp(confidence),
        excerpt=excerpt[:500],
        extractor=EDITORIAL_JUDGE_VERSION,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = ["EDITORIAL_JUDGE_VERSION", "EditorialJudge"]
