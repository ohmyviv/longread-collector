"""PR-7.2 Editorial Judge calibration.

PR-7.1 remains the baseline for publication-independent editorial risk
calibration. This wrapper addresses residual natural-run failures from moderate
template contamination and English roundup/news-update formats.

The rules require combinations of structural and semantic evidence. No single
keyword is a hard reject.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import re

from ..contracts import (
    AcquisitionBundle,
    CanonicalArticle,
    ContentMedium,
    EditorialAssessment,
    EditorialGenre,
    EditorialVerdict,
    Evidence,
    PageSurface,
    RunContext,
    StageName,
)
from .service_v071 import (
    EditorialJudge as _PR71EditorialJudge,
    _clamp,
    _editorial_value_for,
    _main_content_text,
    _reader_value,
    _utility,
    _verdict_for,
)

EDITORIAL_JUDGE_VERSION = "editorial-judge-v0.6-pr7.2"

_ROUNDUP_IDENTITY_RE = re.compile(
    r"\b(?:newsletter|news\s+roundup|roundup|news\s+digest|daily\s+digest|"
    r"weekly\s+digest|briefing)\b",
    re.IGNORECASE,
)
_ROUNDUP_SELF_RE = re.compile(
    r"\b(?:welcome\s+to\s+(?:our|the)\s+(?:newsletter|roundup|briefing)|"
    r"this\s+(?:newsletter|roundup|briefing|digest)|"
    r"(?:today['’]s|this\s+week['’]s)\s+(?:newsletter|roundup|briefing)|"
    r"special\s+edition|the\s+abstract)\b",
    re.IGNORECASE,
)
_MULTI_STORY_RE = re.compile(
    r"\b(?:in\s+this\s+(?:edition|issue)|here\s+are\s+(?:the\s+)?"
    r"(?:stories|studies|papers|reports)|in\s+other\s+news|also\s+in\s+this|"
    r"another\s+(?:story|study|paper|report)|more\s+(?:stories|studies|news)|"
    r"next\s+up|elsewhere\s+this\s+week)\b",
    re.IGNORECASE,
)
_NEWS_UPDATE_RE = re.compile(
    r"\b(?:announced|announcement|city\s+council|council\s+meeting|town\s+hall|"
    r"public\s+meeting|statement|confirmed|following|after|moved?\s+to|"
    r"arrested|threats?|officials?\s+said|according\s+to|will\s+(?:now|be|hold))\b",
    re.IGNORECASE,
)
_ENGLISH_REPORTING_RE = re.compile(
    r"\b(?:told\s+me|told\s+us|said|according\s+to|spoke\s+with|interviewed|"
    r"researchers?|experts?|study|studies|survey|data|records?|documents?)\b",
    re.IGNORECASE,
)
_ENGLISH_ANALYSIS_RE = re.compile(
    r"\b(?:because|however|although|yet|therefore|suggests?|evidence|means?|"
    r"why|history|policy|structure|trend|risk|mechanism|consequence|"
    r"implication|compared\s+with|in\s+contrast)\b",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"(?m)^\s*#{1,4}\s+\S")


class EditorialJudge:
    """Run PR-7.1, then apply narrow format and template calibration."""

    stage_version = EDITORIAL_JUDGE_VERSION

    def __init__(self) -> None:
        self._base = _PR71EditorialJudge()

    def assess(
        self,
        context: RunContext,
        article: CanonicalArticle,
        bundle: AcquisitionBundle,
    ) -> EditorialAssessment:
        base = self._base.assess(context, article, bundle)
        if base.verdict is EditorialVerdict.INSUFFICIENT_EVIDENCE:
            return replace(base, stage_version=EDITORIAL_JUDGE_VERSION)

        main_text = _main_content_text(article, bundle)
        compact_chars = len(re.sub(r"\s+", "", main_text))

        roundup_reason = _roundup_reason(main_text, compact_chars)
        if roundup_reason:
            return _format_reject(article, base, reason=roundup_reason, compact_chars=compact_chars)

        news_reason = _short_news_update_reason(article, base, main_text, compact_chars)
        if news_reason:
            return _format_reject(article, base, reason=news_reason, compact_chars=compact_chars)

        if not _eligible_for_template_recovery(article, base, main_text, compact_chars):
            return replace(base, stage_version=EDITORIAL_JUDGE_VERSION)

        template = min(base.template_risk, 0.22)
        if base.template_risk - template < 0.08:
            return replace(base, stage_version=EDITORIAL_JUDGE_VERSION)

        risks = (base.promotional_risk, base.event_risk, base.transcript_risk, template)
        reader_value = _reader_value(base, risks)
        utility = _utility(base, reader_value, risks)
        verdict = _verdict_for(utility)
        editorial_value = _editorial_value_for(verdict)

        superseded_fields = {"reader_value_score", "template_risk", "verdict", "editorial_verdict"}
        evidence = tuple(item for item in base.evidence if item.field not in superseded_fields)
        evidence += (
            _make_evidence(
                article.item_id,
                "reader_value_score",
                round(reader_value, 6),
                evidence_type="editorial_template_recovery",
                excerpt=f"pr7.2 moderate-template recovery; main_chars={compact_chars}; utility={utility:.3f}",
            ),
            _make_evidence(
                article.item_id,
                "template_risk",
                round(template, 6),
                evidence_type="editorial_template_recovery",
                excerpt=f"pr7.2 recovered from template_risk={base.template_risk:.3f}; main_chars={compact_chars}",
            ),
            _make_evidence(
                article.item_id,
                "verdict",
                verdict.value,
                evidence_type="editorial_template_recovery",
                excerpt=f"pr7.2 moderate-template recovery; utility={utility:.3f}; main_chars={compact_chars}",
            ),
        )
        return replace(
            base,
            stage_version=EDITORIAL_JUDGE_VERSION,
            reader_value_score=reader_value,
            template_risk=template,
            editorial_value=editorial_value,
            verdict=verdict,
            evidence=evidence,
        )


def _roundup_reason(main_text: str, compact_chars: int) -> str:
    if compact_chars < 900:
        return ""
    front = main_text[:3500]
    identity_hits = len(_ROUNDUP_IDENTITY_RE.findall(front))
    self_hits = len(_ROUNDUP_SELF_RE.findall(front))
    multi_story_hits = len(_MULTI_STORY_RE.findall(main_text))
    heading_count = len(_HEADING_RE.findall(main_text))
    lower_front = front.lower()
    explicit_abstract_special = "the abstract" in lower_front and "special edition" in lower_front
    if explicit_abstract_special and (multi_story_hits >= 1 or heading_count >= 2):
        return "english_roundup_self_identified_multi_story"
    if self_hits >= 1 and (multi_story_hits >= 2 or heading_count >= 3):
        return "english_roundup_self_identified_multi_story"
    if identity_hits >= 2 and multi_story_hits >= 2:
        return "english_roundup_self_identified_multi_story"
    return ""


def _short_news_update_reason(
    article: CanonicalArticle,
    assessment: EditorialAssessment,
    main_text: str,
    compact_chars: int,
) -> str:
    if article.main_content_medium is not ContentMedium.WRITTEN_ARTICLE:
        return ""
    if article.page_surface is not PageSurface.ARTICLE_PAGE:
        return ""
    if article.editorial_genre is not EditorialGenre.REPORTED_FEATURE:
        return ""
    if compact_chars < 700 or compact_chars > 4200:
        return ""
    update_hits = len(_NEWS_UPDATE_RE.findall(main_text))
    weak_depth = (
        assessment.analysis_score < 0.48
        and assessment.argument_score < 0.45
        and assessment.evidence_density_score < 0.68
        and assessment.original_reporting_score < 0.65
    )
    if update_hits >= 2 and weak_depth:
        return "short_low_depth_news_update"
    return ""


def _eligible_for_template_recovery(
    article: CanonicalArticle,
    assessment: EditorialAssessment,
    main_text: str,
    compact_chars: int,
) -> bool:
    if article.main_content_medium is not ContentMedium.WRITTEN_ARTICLE:
        return False
    if article.page_surface is not PageSurface.ARTICLE_PAGE:
        return False
    if not 0.25 <= assessment.template_risk <= 0.55:
        return False
    if compact_chars < 4500 or assessment.substance_score < 0.70:
        return False
    if max(assessment.promotional_risk, assessment.event_risk, assessment.transcript_risk) >= 0.55:
        return False
    reporting_hits = len(_ENGLISH_REPORTING_RE.findall(main_text))
    analysis_hits = len(_ENGLISH_ANALYSIS_RE.findall(main_text))
    long_paragraphs = sum(1 for line in main_text.splitlines() if len(line.strip()) >= 120)
    depth_evidence = reporting_hits >= 4 or analysis_hits >= 8 or assessment.evidence_density_score >= 0.62
    return long_paragraphs >= 4 and depth_evidence


def _format_reject(
    article: CanonicalArticle,
    base: EditorialAssessment,
    *,
    reason: str,
    compact_chars: int,
) -> EditorialAssessment:
    evidence = tuple(item for item in base.evidence if item.field not in {"verdict", "editorial_verdict"})
    evidence += (
        _make_evidence(
            article.item_id,
            "format_guard_reason",
            reason,
            evidence_type="editorial_format_guard",
            excerpt=f"pr7.2 format guard; main_chars={compact_chars}",
            confidence=0.96,
        ),
        _make_evidence(
            article.item_id,
            "verdict",
            EditorialVerdict.REJECT.value,
            evidence_type="editorial_format_guard",
            excerpt=f"pr7.2 format guard={reason}; main_chars={compact_chars}; combined structural evidence required",
            confidence=0.96,
        ),
    )
    return replace(
        base,
        stage_version=EDITORIAL_JUDGE_VERSION,
        editorial_value="none",
        verdict=EditorialVerdict.REJECT,
        evidence=evidence,
    )


def _make_evidence(
    item_id: str,
    field: str,
    value: object,
    *,
    evidence_type: str,
    excerpt: str,
    confidence: float = 0.92,
) -> Evidence:
    seed = f"{item_id}|{EDITORIAL_JUDGE_VERSION}|{evidence_type}|{field}|{value}"
    return Evidence(
        evidence_id=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20],
        evidence_type=evidence_type,
        source_stage=StageName.EDITORIAL,
        field=field,
        value=value,
        confidence=_clamp(confidence),
        excerpt=excerpt[:500],
        extractor=EDITORIAL_JUDGE_VERSION,
    )


__all__ = ["EDITORIAL_JUDGE_VERSION", "EditorialJudge"]
