"""Natural-holdout classification fixes for collector v0.5.6l.

The Aug 6 pre-report run exposed two general failure modes:

* corrupted metadata (especially cookie text in the author field) could erase
  strong article evidence and reject complete editorial bodies;
* several deterministic non-article intents still fell through to the generic
  long-form path.

This layer keeps deterministic negative intent ahead of positive rescue and
uses article-body structure rather than fixture titles or article IDs.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .classification import ClassificationResult
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
_COURSE_TITLE_RE = re.compile(
    r"(?:\bcourse\b|training program|certificate program|课程|培训班|研修班)",
    re.I,
)
_COURSE_BODY_MARKERS = (
    re.compile(r"(?:enrol|enroll|register|apply now|报名|招生)", re.I),
    re.compile(r"(?:curriculum|syllabus|module|lesson|课程安排|教学计划)", re.I),
    re.compile(r"(?:certificate|continuing education|ceu|结业证书|学分)", re.I),
    re.compile(r"(?:participants will learn|you will learn|学习目标|培训对象)", re.I),
)
_REPORT_TITLE_RE = re.compile(r"(?:benchmark|industry|research|market|r&d).{0,40}report|报告", re.I)
_GATED_REPORT_MARKERS = (
    re.compile(r"(?:download|get|access|request).{0,24}(?:full )?report", re.I),
    re.compile(r"(?:first name|last name|business email|company name|work email)", re.I),
    re.compile(r"(?:complete the form|submit the form|填写表单|免费下载|获取报告)", re.I),
    re.compile(r"(?:lead generation|contact sales|talk to an expert)", re.I),
)
_VENDOR_CASE_TITLE_RE = re.compile(
    r"(?:customer story|user story|case study|root cause.{0,40}(?:simulation|software)|"
    r"using .{0,40}(?:apps?|platform|software) to)",
    re.I,
)
_VENDOR_CASE_BODY_MARKERS = (
    re.compile(r"(?:customer story|user story|case study|客户案例|用户案例)", re.I),
    re.compile(r"(?:software platform|simulation app|multiphysics|product suite|解决方案)", re.I),
    re.compile(r"(?:learn more|request a demo|contact sales|try the software|了解更多)", re.I),
    re.compile(r"(?:originally appeared|sponsored by|partner content|品牌内容)", re.I),
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
    r"Dec(?:ember)?)\s+\d{1,2},\s+20\d{2}",
    re.I,
)
_EDITORIAL_PROSE_RE = re.compile(
    r"(?:according to|told |said |reported|analysis|research|data show|"
    r"采访|记者|数据显示|研究显示|分析|指出|表示)",
    re.I,
)


def sanitize_author_v056l(author: str) -> str:
    """Return a plausible byline or an empty value when metadata is chrome."""

    value = " ".join(str(author or "").split()).strip()
    if not value:
        return ""
    if len(value) > 180 or _AUTHOR_BOILERPLATE_RE.search(value):
        return ""
    return value


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


def _domain(url: str) -> str:
    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


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
    domain = _domain(url)
    sample = "\n".join((resolved_title, str(description or ""), text[:12000]))

    if (
        _LIVE_RESULTS_RE.search("\n".join((resolved_title, url)))
        and (_LIVE_RESULTS_BODY_RE.search(sample) or "results" in url.lower())
    ):
        return _reject(
            "live_results_interactive_v056l",
            "interactive_data",
            "live_election_results",
        )

    if (
        _COURSE_TITLE_RE.search(resolved_title)
        and _count(_COURSE_BODY_MARKERS, text[:10000]) >= 2
    ):
        return _reject(
            "course_promotion_v056l",
            "course_or_training",
            "course_promotion",
        )

    if (
        _REPORT_TITLE_RE.search(resolved_title)
        and _count(_GATED_REPORT_MARKERS, text[:10000]) >= 2
        and identity.body_prose_chars < 6000
    ):
        return _reject(
            "gated_report_landing_v056l",
            "report_landing",
            "gated_marketing_report",
        )

    if (
        _VENDOR_CASE_TITLE_RE.search(resolved_title)
        and _count(_VENDOR_CASE_BODY_MARKERS, sample) >= 2
        and not _BYLINE_RE.search(text[:3000])
    ):
        return _reject(
            "vendor_case_study_v056l",
            "advertorial",
            "vendor_case_study",
        )

    clean_author = sanitize_author_v056l(author)
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

    # A corrupted metadata field must not erase a complete article body. This
    # rescue is deliberately structural and remains behind all deterministic
    # non-content gates above.
    if (
        result.candidate_disposition == "reject"
        and result.reason.startswith("insufficient_editorial_evidence")
        and identity.body_prose_chars >= 5000
        and identity.heading_count >= 1
        and identity.title_similarity >= 0.60
        and len([p for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 80]) >= 8
        and (_BYLINE_RE.search(text[:5000]) or _DATE_LINE_RE.search(text[:5000]))
        and len(_EDITORIAL_PROSE_RE.findall(text[:12000])) >= 2
        and not (_PAYWALL_RE.search(text[:5000]) and identity.body_prose_chars < 5000)
    ):
        result = _formal("complete_editorial_body_metadata_recovery_v056l")

    if clean_author != str(author or "").strip() and result.candidate_disposition != "reject":
        result.reason = f"{result.reason}; author_boilerplate_removed_v056l"

    return result


__all__ = [
    "CLASSIFICATION_VERSION",
    "classify_candidate_v056l",
    "sanitize_author_v056l",
]
