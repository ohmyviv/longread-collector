"""Final calibration over the v0.5.6k shadow-quality classifier.

The base v0.5.6k layer handles broad page intent and recall recovery. This
module performs the narrow, evidence-heavy corrections discovered by replaying
the complete Aug 5 reviewed cache:

* identify the article's real H1 before reading its source line;
* distinguish same-publisher source labels from transparent republication;
* keep primary government documents in the special lane;
* reject official consultative-meeting recaps deterministically.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .classification import ClassificationResult
from .classification_v056k import (
    CLASSIFICATION_VERSION,
    classify_candidate_v056k as _base_classify,
)
from .content_identity_v056j import evaluate_content_identity

_SOURCE_RE = re.compile(
    r"(?:来源|Source)\s*[:：]\s*"
    r"(?:\[(?P<linked>[^\]\n]{2,80})\]\([^)]+\)|(?P<plain>[^\s\n]{2,80}))",
    re.I,
)
_PRIMARY_DOCUMENT_RE = re.compile(
    r"(?:通知|规划|条例|办法|意见|公告|决定|通告|批复|令)$|"
    r"(?:关于.{0,100}(?:通知|意见|公告|决定|批复))",
    re.I,
)
_CPPCC_MEETING_RE = re.compile(
    r"(?:CPPCC members discuss|biweekly consultative meeting|"
    r"consultative meeting|held its .{0,30} meeting)",
    re.I,
)
_CPPCC_BODY_RE = re.compile(
    r"(?:presid(?:e|es|ed) over the meeting|members spoke at the meeting|"
    r"officials .{0,120} gave briefings|participants called for|attended the meeting)",
    re.I | re.S,
)
_HOST_SOURCE_TOKENS: dict[str, tuple[str, ...]] = {
    "chinanews.com.cn": ("中新网", "中国新闻网", "中新社"),
    "cnr.cn": ("央广网", "中央广播电视总台"),
    "ce.cn": ("中国经济网", "经济日报", "经济日报社"),
    "studytimes.cn": ("学习时报", "学习时报网", "中央党校报刊社"),
    "fudan.edu.cn": ("复旦大学", "上海医学院"),
    "cass.cn": ("中国社会科学院", "社科院专刊"),
    "cssn.cn": ("中国社会科学网", "中国社会科学院"),
    "naes.org.cn": ("中国社会科学网", "中国社会科学院", "财经战略研究院"),
    "mee.gov.cn": ("生态环境部",),
    "cq.gov.cn": ("重庆市人民政府", "重庆市政府网"),
    "china.com": ("中华网",),
    "news.cn": ("新华社", "新华网"),
    "xinhuanet.com": ("新华社", "新华网"),
    "eeo.com.cn": ("经济观察网", "经济观察报"),
    "yicai.com": ("第一财经",),
    "cppcc.gov.cn": ("全国政协", "CPPCC", "CPPCC Daily"),
}


def _domain(url: str) -> str:
    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


def _same_publisher(source: str, url: str) -> bool:
    domain = _domain(url)
    normalized = re.sub(r"[\s_*《》\[\]（）()]", "", source)
    for suffix, tokens in _HOST_SOURCE_TOKENS.items():
        if domain == suffix or domain.endswith(f".{suffix}"):
            return any(
                re.sub(r"[\s_*《》\[\]（）()]", "", token) in normalized
                for token in tokens
            )
    return False


def _article_window(markdown: str, title: str) -> str:
    text = str(markdown or "")
    identity = evaluate_content_identity(title=title, markdown=text)
    heading = str(identity.body_heading or "").strip()
    if heading:
        match = re.search(
            rf"(?m)^#{{1,2}}\s+.*{re.escape(heading[:50])}.*$",
            text,
            re.I,
        )
        if match:
            return text[match.start() : match.start() + 8000]
    for match in re.finditer(r"(?m)^#\s+(.+)$", text):
        candidate = match.group(1).strip()
        if candidate.startswith("[![") or len(re.sub(r"\W", "", candidate)) < 6:
            continue
        return text[match.start() : match.start() + 8000]
    return text[:8000]


def _header_source(markdown: str, title: str) -> str:
    window = _article_window(markdown, title)
    match = _SOURCE_RE.search(window)
    if not match:
        return ""
    source = (match.group("linked") or match.group("plain") or "").strip(" _*[]")
    return source.rstrip("，。；;、")


def _reject_official_meeting() -> ClassificationResult:
    return ClassificationResult(
        page_role="non_content",
        page_type="event_or_release_announcement",
        content_type="official_consultative_meeting_recap",
        candidate_disposition="reject",
        source_relationship="original",
        source_action="none",
        confidence="high",
        reason="official_consultative_meeting_recap_v056k",
    )


def _apply_source_calibration(
    result: ClassificationResult,
    *,
    source: str,
    url: str,
    title: str,
    body_chars: int,
) -> ClassificationResult:
    if result.source_relationship == "translated_republish":
        return result

    if not source:
        # The base layer may have found a source token in navigation or a legal
        # disclaimer. Without a source in the article-header window, do not
        # change authorship.
        if "transparent_source_line_v056k" in result.reason:
            result.source_relationship = "original"
            result.original_publisher = ""
            result.original_url = ""
            if result.candidate_disposition != "reject":
                result.source_action = "retain_with_source_label"
            result.reason = result.reason.replace(
                "; transparent_source_line_v056k", ""
            ).replace("transparent_source_line_v056k; ", "")
        return result

    if _same_publisher(source, url):
        result.source_relationship = "original"
        result.original_publisher = ""
        result.original_url = ""
        if result.candidate_disposition != "reject":
            result.source_action = "retain_with_source_label"
        result.reason = result.reason.replace(
            "; transparent_source_line_v056k", ""
        ).replace("transparent_source_line_v056k; ", "")
        return result

    result.source_relationship = "secondary_republish"
    result.original_publisher = source
    result.original_url = ""
    if result.candidate_disposition != "reject":
        result.source_action = "retain_with_source_label"
    if "transparent_source_line_v056k" not in result.reason:
        result.reason = (
            f"{result.reason}; transparent_source_line_v056k"
            if result.reason
            else "transparent_source_line_v056k"
        )

    if (
        result.candidate_disposition == "special_candidate"
        and not _PRIMARY_DOCUMENT_RE.search(title)
        and body_chars >= 1800
    ):
        result.page_role = "standalone_content"
        result.page_type = "article"
        result.content_type = "reported_republish"
        result.candidate_disposition = "formal_candidate"
        result.special_candidate_type = ""
        result.source_action = "retain_with_source_label"
        result.confidence = "high"
        result.reason = "transparent_reported_republish_v056k"
    return result


def classify_candidate_v056k_final(
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
    identity = evaluate_content_identity(title=title, markdown=markdown)
    resolved_title = identity.resolved_title or str(title or "").strip()
    window = _article_window(markdown, resolved_title)
    domain = _domain(url)

    if (
        (domain == "cppcc.gov.cn" or domain.endswith(".cppcc.gov.cn"))
        and _CPPCC_MEETING_RE.search("\n".join((resolved_title, window[:3000])))
        and len(_CPPCC_BODY_RE.findall(window)) >= 2
    ):
        return _reject_official_meeting()

    result = _base_classify(
        url=url,
        title=resolved_title,
        description=description,
        author=author,
        markdown=markdown,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=(identity.body_prose_chars or content_chars),
    )
    source = _header_source(markdown, resolved_title)
    return _apply_source_calibration(
        result,
        source=source,
        url=url,
        title=resolved_title,
        body_chars=identity.body_prose_chars,
    )


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056k_final"]
