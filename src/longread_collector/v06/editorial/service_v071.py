"""PR-7.1 Editorial Judge calibration.

The PR-3 judge remains the development baseline.  This wrapper only recalibrates
risk when whole-page/template text inflated semantic risk, while preserving
intrinsic canonical event/promotion/transcript decisions.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import re

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    EditorialAssessment,
    EditorialGenre,
    EditorialVerdict,
    Evidence,
    RunContext,
    StageName,
)
from .service import EditorialJudge as _BaseEditorialJudge

EDITORIAL_JUDGE_VERSION = "editorial-judge-v0.6-pr7.1"

_PROMO_STRONG_RE = re.compile(
    r"报名|報名|诚邀|誠邀|欢迎参加|歡迎參加|优惠|優惠|限时|限時|"
    r"新品首发|新品首發|推介会|推介會|展销|展銷|成果展示|商业合作|商業合作|广告合作|廣告合作"
)
_EVENT_STRONG_RE = re.compile(
    r"培训班|培訓班|发布会|發布會|启动仪式|啟動儀式|开幕式|開幕式|"
    r"闭幕式|閉幕式|结业仪式|結業儀式|书展|書展|展会|展會|论坛|論壇|峰会|峰會|"
    r"活动(?:成功)?(?:举办|举行)|活動(?:成功)?(?:舉辦|舉行)"
)
_TRANSCRIPT_STRONG_RE = re.compile(
    r"焦点访谈|焦點訪談|主持人\s*[：:]|解说\s*[：:]|解說\s*[：:]|"
    r"同期声|同期聲|节目实录|節目實錄|电视节目|電視節目"
)
_END_MARKERS = (
    "\n相关阅读",
    "\n相關閱讀",
    "\n相关新闻",
    "\n相關新聞",
    "\n举报",
    "\n舉報",
    "\n版权声明",
    "\n版權聲明",
    "\n值班总编推荐",
    "\n一财最热",
    "\n网站声明",
    "\n網站聲明",
    "\n版权所有",
    "\n版權所有",
    "\n返回顶部",
    "\n返回頂部",
)


class EditorialJudge:
    """Run PR-3 scoring, then correct demonstrable whole-page risk inflation."""

    stage_version = EDITORIAL_JUDGE_VERSION

    def __init__(self) -> None:
        self._base = _BaseEditorialJudge()

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
        promotional, event, transcript, template = _calibrated_risks(
            article, base, main_text
        )
        old_risks = (
            base.promotional_risk,
            base.event_risk,
            base.transcript_risk,
            base.template_risk,
        )
        new_risks = (promotional, event, transcript, template)

        # Do not perturb already-stable low-risk judgments.  PR-7.1 is a risk
        # false-positive calibration, not a wholesale PR-3 rescoring exercise.
        materially_reduced = any(old - new >= 0.15 for old, new in zip(old_risks, new_risks))
        if max(old_risks) < 0.55 or not materially_reduced:
            return replace(base, stage_version=EDITORIAL_JUDGE_VERSION)

        reader_value = _reader_value(base, new_risks)
        utility = _utility(base, reader_value, new_risks)
        verdict = _verdict_for(utility)
        editorial_value = _editorial_value_for(verdict)

        superseded_fields = {
            "reader_value_score",
            "promotional_risk",
            "event_risk",
            "transcript_risk",
            "template_risk",
            "verdict",
        }
        evidence = tuple(item for item in base.evidence if item.field not in superseded_fields)
        evidence += _calibration_evidence(
            article.item_id,
            reader_value=reader_value,
            promotional=promotional,
            event=event,
            transcript=transcript,
            template=template,
            verdict=verdict,
            utility=utility,
            main_chars=len(main_text),
        )

        return replace(
            base,
            stage_version=EDITORIAL_JUDGE_VERSION,
            reader_value_score=reader_value,
            promotional_risk=promotional,
            event_risk=event,
            transcript_risk=transcript,
            template_risk=template,
            editorial_value=editorial_value,
            verdict=verdict,
            evidence=evidence,
        )


def _main_content_text(article: CanonicalArticle, bundle: AcquisitionBundle) -> str:
    body = bundle.body_markdown or bundle.body_text or ""
    title = (article.resolved_title or bundle.raw_title or "").strip()
    start = 0
    if title:
        position = body.find(title)
        if 0 <= position <= 12000:
            start = position
        elif " - " in title:
            short_title = title.split(" - ", 1)[0].strip()
            position = body.find(short_title)
            if 0 <= position <= 12000:
                start = position

    value = body[start : start + 36000]
    end = len(value)
    for marker in _END_MARKERS:
        position = value.find(marker)
        if position >= 1200:
            end = min(end, position)
    return value[:end]


def _calibrated_risks(
    article: CanonicalArticle,
    base: EditorialAssessment,
    main_text: str,
) -> tuple[float, float, float, float]:
    title = article.resolved_title or ""
    promo_count = len(_PROMO_STRONG_RE.findall(main_text))
    event_count = len(_EVENT_STRONG_RE.findall(main_text))
    transcript_count = len(_TRANSCRIPT_STRONG_RE.findall(main_text))
    title_promo = bool(_PROMO_STRONG_RE.search(title))
    title_event = bool(_EVENT_STRONG_RE.search(title))

    if article.editorial_genre is EditorialGenre.PROMOTION:
        promotional = 0.97
    elif title_promo and promo_count >= 2:
        promotional = max(0.78, min(base.promotional_risk, 0.92))
    elif promo_count >= 5 and base.original_reporting_score < 0.25:
        promotional = min(base.promotional_risk, 0.70)
    elif promo_count >= 3:
        promotional = min(base.promotional_risk, 0.42)
    else:
        promotional = min(base.promotional_risk, 0.24)

    if article.main_content_medium is ContentMedium.EVENT_LISTING:
        event = 0.98
    elif article.editorial_genre is EditorialGenre.EVENT_PREVIEW:
        event = 0.96
    elif article.editorial_genre is EditorialGenre.EVENT_RECAP:
        event = 0.90
    elif title_event and event_count >= 2:
        event = max(0.78, min(base.event_risk, 0.90))
    elif event_count >= 5 and base.original_reporting_score < 0.25:
        event = min(base.event_risk, 0.68)
    elif event_count >= 3:
        event = min(base.event_risk, 0.42)
    else:
        event = min(base.event_risk, 0.24)

    if article.main_content_medium in {
        ContentMedium.TELEVISION_TRANSCRIPT,
        ContentMedium.PODCAST_TRANSCRIPT,
    } or article.asset_class is AssetClass.TRANSCRIPT:
        transcript = 0.98
    elif transcript_count >= 6:
        transcript = min(base.transcript_risk, 0.76)
    elif transcript_count >= 3:
        transcript = min(base.transcript_risk, 0.48)
    else:
        transcript = min(base.transcript_risk, 0.18)

    if article.main_content_medium is ContentMedium.DATA_CARD or article.editorial_genre is EditorialGenre.MARKET_DATA:
        template = max(0.95, base.template_risk)
    elif len("".join(main_text.split())) >= 2500 and article.main_content_medium is ContentMedium.WRITTEN_ARTICLE:
        template = min(base.template_risk, 0.35)
    else:
        template = base.template_risk

    return tuple(_clamp(value) for value in (promotional, event, transcript, template))


def _reader_value(
    base: EditorialAssessment,
    risks: tuple[float, float, float, float],
) -> float:
    value = (
        0.30 * base.substance_score
        + 0.22 * base.original_reporting_score
        + 0.20 * base.analysis_score
        + 0.12 * base.argument_score
        + 0.16 * base.evidence_density_score
    )
    return _clamp(value * (1.0 - 0.35 * max(risks)))


def _utility(
    base: EditorialAssessment,
    reader_value: float,
    risks: tuple[float, float, float, float],
) -> float:
    positive = (
        0.18 * base.substance_score
        + 0.17 * base.original_reporting_score
        + 0.17 * base.analysis_score
        + 0.12 * base.argument_score
        + 0.14 * base.evidence_density_score
        + 0.14 * reader_value
        + 0.08 * base.timeliness_relevance_score
    )
    risk_penalty = 0.34 * max(risks) + 0.08 * (sum(risks) / len(risks))
    return _clamp(positive - risk_penalty)


def _verdict_for(utility: float) -> EditorialVerdict:
    if utility >= 0.68:
        return EditorialVerdict.RECOMMEND
    if utility >= 0.48:
        return EditorialVerdict.CONSIDER
    if utility >= 0.30:
        return EditorialVerdict.LOW_VALUE
    return EditorialVerdict.REJECT


def _editorial_value_for(verdict: EditorialVerdict) -> str:
    return {
        EditorialVerdict.RECOMMEND: "high",
        EditorialVerdict.CONSIDER: "medium",
        EditorialVerdict.LOW_VALUE: "low",
        EditorialVerdict.REJECT: "none",
        EditorialVerdict.INSUFFICIENT_EVIDENCE: "insufficient_evidence",
    }[verdict]


def _calibration_evidence(
    item_id: str,
    *,
    reader_value: float,
    promotional: float,
    event: float,
    transcript: float,
    template: float,
    verdict: EditorialVerdict,
    utility: float,
    main_chars: int,
) -> tuple[Evidence, ...]:
    rows = (
        ("reader_value_score", round(reader_value, 6)),
        ("promotional_risk", round(promotional, 6)),
        ("event_risk", round(event, 6)),
        ("transcript_risk", round(transcript, 6)),
        ("template_risk", round(template, 6)),
        ("verdict", verdict.value),
    )
    return tuple(
        _make_evidence(
            item_id,
            field,
            value,
            excerpt=(
                f"pr7.1 main_content_chars={main_chars}; calibrated_utility={utility:.3f}"
                if field == "verdict"
                else f"pr7.1 main_content_chars={main_chars}"
            ),
        )
        for field, value in rows
    )


def _make_evidence(item_id: str, field: str, value: object, *, excerpt: str) -> Evidence:
    seed = f"{item_id}|{EDITORIAL_JUDGE_VERSION}|{field}|{value}"
    return Evidence(
        evidence_id=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20],
        evidence_type="editorial_calibration",
        source_stage=StageName.EDITORIAL,
        field=field,
        value=value,
        confidence=0.90,
        excerpt=excerpt[:500],
        extractor=EDITORIAL_JUDGE_VERSION,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = ["EDITORIAL_JUDGE_VERSION", "EditorialJudge"]
