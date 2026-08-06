"""Natural-holdout classification fixes for collector v0.5.6l."""

from __future__ import annotations

import re

from .classification import ClassificationResult, normalize_title
from .classification_v056k_final import classify_candidate_v056k_final as _base_classify
from .content_identity_v056j import evaluate_content_identity

CLASSIFICATION_VERSION = "collector-v0.5.6l"

_AUTHOR_BOILERPLATE_RE = re.compile(
    r"(?:use of cookies|cookie policy|privacy policy|personalization of content|"
    r"traffic analysis|enable javascript|unsupported browser|sign in to continue|"
    r"all rights reserved)",
    re.I,
)
_LIVE_RESULTS_RE = re.compile(
    r"(?:live results?|election results?|primary[- ]election map|results map|"
    r"实时(?:结果|选情)|开票结果)",
    re.I,
)
_LIVE_RESULTS_BODY_RE = re.compile(
    r"(?:precincts reporting|estimated votes|race called|interactive map|"
    r"live vote|reporting results|开票进度|实时更新)",
    re.I,
)
_POETRY_RE = re.compile(r"(?:/poems?(?:/|$)|[-_]poem(?:[/?#]|$)|\[Poems\])", re.I)
_IN_CONTENT_PAYWALL_RE = re.compile(
    r"(?:your window is closing|PAYWALL_IN_CONTENT_BARRIER|unlock this story|"
    r"don[’']t lose these views|get full access for|already a subscriber\?\s*\[?Sign In)",
    re.I,
)
_COURSE_TITLE_RE = re.compile(
    r"(?:\bcourse\b|training program|certificate program|课程|培训班|研修班)",
    re.I,
)
_COURSE_BODY_MARKERS = (
    re.compile(r"(?:online\s+.+?course program|launched the online|course program)", re.I),
    re.compile(r"(?:curriculum|syllabus|learning modules?|five modules?|课程安排|教学计划)", re.I),
    re.compile(r"(?:learners? are taught|this module teaches|participants will learn|学习目标)", re.I),
    re.compile(r"(?:individual access|volume pricing|contact a content specialist|enrol|enroll|报名)", re.I),
    re.compile(r"(?:certificate|continuing education|ceu|结业证书|学分)", re.I),
)
_REPORT_TITLE_RE = re.compile(
    r"(?:(?:benchmark|industry|research|market|r&d).{0,50}report|white paper|白皮书|报告)",
    re.I,
)
_GATED_REPORT_MARKERS = (
    re.compile(r"(?:download now|download the .{0,30}report|complimentary .{0,20}report|look inside)", re.I),
    re.compile(r"(?:first register|register your details|login to access|hub registration)", re.I),
    re.compile(r"(?:first name|last name|business email|company/?organization|job title)", re.I),
    re.compile(r"(?:complete the form|submit the form|fill out the form|填写表单)", re.I),
    re.compile(r"(?:sponsored by|presented by|partnered with|sponsor)", re.I),
    re.compile(r"(?:consent to receive marketing|marketing messaging)", re.I),
)
_SPONSORED_CASE_RE = re.compile(
    r"(?:sponsored article|this article is brought to you by|partner content|"
    r"paid content|advertorial|品牌内容|赞助内容)",
    re.I,
)
_VENDOR_CASE_CONTEXT_RE = re.compile(
    r"(?:customer story|user story|case study|this article originally appeared|客户案例|用户案例)",
    re.I,
)
_VENDOR_PRODUCT_RE = re.compile(
    r"(?:comsol multiphysics|simulation apps?|product suite|software platform|"
    r"request a demo|learn more about the product)",
    re.I,
)
_PAYWALL_RE = re.compile(
    r"(?:subscribe to continue|subscription required|already a subscriber|"
    r"to read the full (?:story|article)|付费阅读|订阅后继续)",
    re.I,
)
_BYLINE_RE = re.compile(
    r"(?m)^(?:by|author|作者|记者)\s*[:：]?\s*[A-Z\u4e00-\u9fff][^\n]{1,120}$",
    re.I,
)
_DATE_LINE_RE = re.compile(
    r"(?m)^(?:published|updated)?\s*(?:on\s*)?"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},\s*20\d{2}\s*$",
    re.I,
)
_INTERVIEW_LABEL_RE = re.compile(r"(?m)^#{2,4}\s*INTERVIEW\s*$", re.I)
_QA_RE = re.compile(r"(?m)^\*\*(?:e360|[^*:\n]{2,60})\s*:\*\*", re.I)
_FIRST_PARTY_PUBLICATION_RE = re.compile(r"(?m)^##\s+Published at the \[.+?\]", re.I)
_EDITORIAL_PROSE_RE = re.compile(
    r"(?:according to|told |said |reported|analysis|research|data show|"
    r"采访|记者|数据显示|研究显示|分析|指出|表示)",
    re.I,
)


def sanitize_author_v056l(author: str) -> str:
    value = " ".join(str(author or "").split()).strip()
    if not value:
        return ""
    if len(value) > 180 or _AUTHOR_BOILERPLATE_RE.search(value):
        return ""
    return value


def _count(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _reject(
    reason: str,
    page_type: str,
    content_type: str,
    *,
    source_relationship: str = "original",
    duplicate_type: str = "none",
) -> ClassificationResult:
    return ClassificationResult(
        page_role="non_content",
        page_type=page_type,
        content_type=content_type,
        candidate_disposition="reject",
        source_relationship=source_relationship,
        source_action="none",
        duplicate_type=duplicate_type,
        confidence="high",
        reason=reason,
    )


def _formal(reason: str, content_type: str = "analysis_or_commentary") -> ClassificationResult:
    return ClassificationResult(
        page_role="standalone_content",
        page_type="article",
        content_type=content_type,
        candidate_disposition="formal_candidate",
        source_relationship="original",
        source_action="retain_with_source_label",
        confidence="high",
        reason=reason,
    )


def _title_present(title: str, text: str) -> bool:
    normalized = normalize_title(title)
    if len(normalized) < 8:
        return False
    return normalized in normalize_title(text[:12000])


def classify_candidate_v056l(
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
    sample = "\n".join((resolved_title, str(description or ""), text[:16000]))

    if (
        _LIVE_RESULTS_RE.search("\n".join((resolved_title, url)))
        and (_LIVE_RESULTS_BODY_RE.search(sample) or "results" in url.lower())
    ):
        return _reject("live_results_interactive_v056l", "interactive_data", "live_election_results")

    if _POETRY_RE.search("\n".join((url, text[:8000]))):
        return _reject("poetry_not_editorial_longread_v056l", "poetry", "poem")

    if _IN_CONTENT_PAYWALL_RE.search(text):
        return _reject("paywalled_excerpt_v056l", "article", "paywalled_excerpt")

    if _COURSE_TITLE_RE.search(resolved_title) and _count(_COURSE_BODY_MARKERS, text[:30000]) >= 2:
        return _reject("course_promotion_v056l", "course", "course_promotion")

    if _REPORT_TITLE_RE.search(resolved_title) and _count(_GATED_REPORT_MARKERS, text[:30000]) >= 3:
        return _reject(
            "gated_report_landing_v056l",
            "report_landing",
            "gated_marketing_report",
            source_relationship="secondary_republish",
        )

    if (
        (_SPONSORED_CASE_RE.search(text[:18000]) or _VENDOR_CASE_CONTEXT_RE.search(text[:18000]))
        and _VENDOR_PRODUCT_RE.search(text[:24000])
    ):
        return _reject(
            "sponsored_vendor_case_v056l",
            "advertorial",
            "vendor_case_study",
            source_relationship="secondary_republish",
            duplicate_type="syndicated_republish",
        )

    clean_author = sanitize_author_v056l(author)

    if (
        _INTERVIEW_LABEL_RE.search(text[:8000])
        and len(_QA_RE.findall(text[:20000])) >= 3
        and identity.body_prose_chars >= 3000
        and _title_present(resolved_title, text)
    ):
        result = _formal("structured_editorial_interview_v056l", "interview")
    elif (
        _FIRST_PARTY_PUBLICATION_RE.search(text[:16000])
        and identity.body_prose_chars >= 3000
        and _title_present(resolved_title, text)
    ):
        result = _formal("first_party_published_feature_v056l", "reported_feature")
    else:
        result = _base_classify(
            url=url,
            title=resolved_title,
            description=description,
            author=clean_author,
            markdown=text,
            published_at=published_at,
            verification_level=verification_level,
            content_chars=(identity.body_prose_chars or content_chars),
        )

    paragraph_count = len([p for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 80])
    title_evidence = identity.title_similarity >= 0.50 or _title_present(resolved_title, text)
    publication_evidence = bool(published_at or clean_author or _DATE_LINE_RE.search(text[:12000]))

    if (
        result.candidate_disposition == "reject"
        and result.reason.startswith("insufficient_editorial_evidence")
        and identity.body_prose_chars >= 5000
        and identity.heading_count >= 1
        and title_evidence
        and paragraph_count >= 6
        and (publication_evidence or len(_EDITORIAL_PROSE_RE.findall(text[:16000])) >= 2)
        and not _IN_CONTENT_PAYWALL_RE.search(text)
        and not (_PAYWALL_RE.search(text[:6000]) and identity.body_prose_chars < 5000)
    ):
        result = _formal("complete_editorial_body_metadata_recovery_v056l")

    if clean_author != str(author or "").strip() and result.candidate_disposition != "reject":
        result.reason = f"{result.reason}; author_boilerplate_removed_v056l"
    return result


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056l", "sanitize_author_v056l"]
