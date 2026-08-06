"""Natural zh-midday holdout fixes for collector v0.5.6m."""

from __future__ import annotations

import re

from .classification import ClassificationResult, normalize_title
from .classification_v056l import (
    classify_candidate_v056l as _base_classify,
    sanitize_author_v056l,
)
from .content_identity_v056j import evaluate_content_identity

CLASSIFICATION_VERSION = "collector-v0.5.6m"

_TRAINING_EVENT_TITLE_RE = re.compile(
    r"(?:专题|能力建设|干部|书记|业务)?培训班.{0,16}(?:开班|开课|结业)|"
    r"(?:开班|结业).{0,16}(?:培训班|研修班)",
    re.I,
)
_TRAINING_EVENT_BODY_MARKERS = (
    re.compile(r"(?:开班仪式|开班式|结业仪式)", re.I),
    re.compile(r"(?:出席.{0,30}讲话|作开班动员|领导讲话)", re.I),
    re.compile(r"(?:参训学员|全体学员|学员代表|培训学员)", re.I),
    re.compile(r"(?:培训期间|专题授课|课程安排|现场教学)", re.I),
    re.compile(r"(?:主办单位|承办单位|由.{0,30}主办|由.{0,30}承办)", re.I),
)
_REGULATORY_TITLE_RE = re.compile(
    r"(?:办法|规定|意见|通知|条例|细则|指南|指引|规范|决定|政策解读)$",
    re.I,
)
_SOURCE_LINE_RE = re.compile(
    r"(?:来源|原载|转载自|本文原载|稿源)\s*[:：]\s*"
    r"(?P<publisher>[^|\n]{2,80})",
    re.I,
)
_ORIGINAL_LINK_RE = re.compile(
    r"(?:原文|原文链接|英文原文|original(?:\s+(?:article|link))?)"
    r"[^\n]{0,180}(?:https?://|\]\(https?://)",
    re.I,
)
_TRANSLATION_RE = re.compile(
    r"(?:译者|翻译\s*[:：]|中文译文|本文译自|translated\s+by|translation\s+by)",
    re.I,
)
_REPOST_DISCLOSURE_RE = re.compile(
    r"(?:来源|原载|转载自|本文原载|稿源)\s*[:：]|"
    r"(?:原文|原文链接)[^\n]{0,160}(?:https?://|\]\(https?://)",
    re.I,
)
_EDITORIAL_RE = re.compile(
    r"(?:记者|采访|专访|调查|暗访|数据显示|研究显示|分析|指出|表示|回应|"
    r"according to|told |said |reported|analysis|research|data show)",
    re.I,
)
_LOW_VALUE_RE = re.compile(
    r"(?:开班仪式|结业仪式|圆满举行|成功举办|会议指出|活动现场|"
    r"新闻8点见|每日简报|一周回顾|欢迎报名|点击报名)",
    re.I,
)
_PROMOTIONAL_RE = re.compile(
    r"(?:品牌发布|新品发布|重磅发布|成果发布会|招商推介|签约仪式|"
    r"下载报告|填写表单|立即报名|request a demo)",
    re.I,
)


def _count(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _reject(reason: str, page_type: str, content_type: str) -> ClassificationResult:
    return ClassificationResult(
        page_role="non_content",
        page_type=page_type,
        content_type=content_type,
        candidate_disposition="reject",
        source_relationship="original",
        source_action="none",
        duplicate_type="none",
        confidence="high",
        reason=reason,
    )


def _republish_formal(
    *,
    reason: str,
    publisher: str,
    content_type: str,
    translated: bool,
) -> ClassificationResult:
    return ClassificationResult(
        page_role="standalone_content",
        page_type="article",
        content_type=content_type,
        candidate_disposition="formal_candidate",
        source_relationship="translated_republish" if translated else "secondary_republish",
        original_publisher=publisher,
        source_action="retain_with_source_label",
        duplicate_type="translated_version" if translated else "syndicated_republish",
        confidence="high",
        reason=reason,
    )


def _publisher(text: str) -> str:
    match = _SOURCE_LINE_RE.search(text[:7000])
    if not match:
        return ""
    value = " ".join(match.group("publisher").split()).strip(" -*_[]（）()")
    # Avoid accidentally swallowing a byline/date sequence.
    value = re.split(r"(?:作者|记者|日期|发布时间)\s*[:：]", value, maxsplit=1)[0].strip()
    return value[:80]


def classify_candidate_v056m(
    *,
    url: str,
    title: str,
    description: str = "",
    author: str = "",
    markdown: str = "",
    published_at: str = "",
    verification_level: str = "",
    content_chars: int = 0,
) -> ClassificationResult:
    text = str(markdown or "")
    identity = evaluate_content_identity(title=title, markdown=text)
    resolved_title = identity.resolved_title or str(title or "").strip()

    if (
        _TRAINING_EVENT_TITLE_RE.search(resolved_title)
        and not _REGULATORY_TITLE_RE.search(resolved_title)
        and _count(_TRAINING_EVENT_BODY_MARKERS, text[:20000]) >= 2
    ):
        return _reject(
            "training_event_recap_v056m",
            "event_news",
            "training_event_recap",
        )

    result = _base_classify(
        url=url,
        title=resolved_title,
        description=description,
        author=author,
        markdown=text,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=(identity.body_prose_chars or content_chars),
    )

    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n", text)
        if len(part.strip()) >= 80
    ]
    normalized_title = normalize_title(resolved_title)
    title_evidence = (
        identity.title_similarity >= 0.45
        or (len(normalized_title) >= 8 and normalized_title in normalize_title(text[:14000]))
    )
    disclosure = bool(_REPOST_DISCLOSURE_RE.search(text[:10000]))
    translated = bool(_TRANSLATION_RE.search(text[:12000]) and _ORIGINAL_LINK_RE.search(text[:16000]))
    publisher = _publisher(text)
    strong_body = (
        identity.body_prose_chars >= 3400
        and len(paragraphs) >= 5
        and title_evidence
        and len(_EDITORIAL_RE.findall(text[:18000])) >= 2
    )
    unsafe = bool(
        _LOW_VALUE_RE.search("\n".join((resolved_title, text[:7000])))
        or _PROMOTIONAL_RE.search("\n".join((resolved_title, text[:7000])))
    )

    # Transparent complete republications are valid formal candidates. This
    # recovery requires both disclosure and strong article-body evidence, and
    # it cannot override deterministic low-value/event/promotion signals.
    if (
        disclosure
        and strong_body
        and not unsafe
        and (
            (
                result.candidate_disposition == "reject"
                and result.reason.startswith("insufficient_editorial_evidence")
            )
            or (
                result.candidate_disposition == "formal_candidate"
                and result.source_relationship == "original"
            )
        )
    ):
        return _republish_formal(
            reason="complete_transparent_republication_v056m",
            publisher=publisher,
            content_type="reported_feature",
            translated=translated,
        )

    # Some complete translations were previously misrouted into the special
    # document lane. An explicit original link plus translation disclosure and
    # a complete article body is enough to restore the normal formal lane.
    if (
        result.candidate_disposition == "special_candidate"
        and translated
        and strong_body
        and not unsafe
        and result.content_type not in {
            "government_primary_document",
            "regulatory_guidance",
            "academic_paper",
        }
    ):
        return _republish_formal(
            reason="complete_translated_article_v056m",
            publisher=publisher,
            content_type="translated_feature",
            translated=True,
        )

    return result


__all__ = [
    "CLASSIFICATION_VERSION",
    "classify_candidate_v056m",
    "sanitize_author_v056l",
]
