"""Shadow-quality classification fixes for collector v0.5.6k.

This layer addresses two opposite failures observed in the Aug 5 natural
shadow runs:

* institutional activities, financing releases and curated digests could fall
  through to the generic long-form candidate path;
* complete reported articles could be rejected because site chrome triggered a
  course rule or because a registered outlet did not expose a reliable date.

The rules remain deliberately evidence based. Deterministic negative page
intent is evaluated before any positive rescue, and the positive rescue is
limited to trusted editorial domains with a substantial, structured body.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .classification import ClassificationResult
from .classification_v056j import classify_candidate_v056j as _base_classify
from .content_identity_v056j import evaluate_content_identity

CLASSIFICATION_VERSION = "collector-v0.5.6k"

_DIGEST_RE = re.compile(
    r"(?:weekly digest|curated selection of articles|members[- ]only content|"
    r"welcome to .{0,80}(?:digest|compass)|本周摘要|每周(?:精选|汇编)|文章汇编)",
    re.I | re.S,
)
_FINANCING_TITLE_RE = re.compile(
    r"(?:完成|获得|宣布).{0,24}(?:pre[- ]?[a-z]|[a-z轮]|战略)?融资|"
    r"(?:pre[- ]?[a-z]|series\s+[a-z]).{0,20}(?:financing|funding)",
    re.I,
)
_FINANCING_BODY_RE = re.compile(
    r"(?:本轮融资|投资方|领投|跟投|融资将用于|资金将用于|融资用途|"
    r"this round was led by|proceeds will be used)",
    re.I,
)
_STUDENT_ACTIVITY_TITLE_RE = re.compile(
    r"(?:社会实践团队|暑期社会实践|实践队|实习计划.{0,20}(?:收官|结业)|"
    r"同学荟.{0,20}(?:成立|启航))",
    re.I,
)
_STUDENT_ACTIVITY_BODY_RE = re.compile(
    r"(?:走访调研|实践团队|带队老师|学生代表|学子们|供稿单位|实习学员|研学)",
    re.I,
)
_EVENT_TITLE_RE = re.compile(
    r"(?:成功举办|圆满举行|研讨活动|研讨会|座谈会|论坛|年会|"
    r"biweekly consultative meeting|members discuss)",
    re.I,
)
_EVENT_BODY_MARKERS = (
    re.compile(r"(?:主办|承办|协办|举办)", re.I),
    re.compile(r"(?:出席|与会|参会|attended)", re.I),
    re.compile(r"(?:致辞|主持|presided over)", re.I),
    re.compile(r"(?:主旨报告|主题报告|分论坛|议程|agenda)", re.I),
    re.compile(r"(?:代表发言|嘉宾发言|members spoke|专家表示)", re.I),
)
_IMAGE_POLICY_RE = re.compile(r"(?:图片解读|一图读懂|政策图解|政策解读)", re.I)
_REPORTED_GUARD_RE = re.compile(
    r"(?:调查|深度|新闻分析|分析|评论|观察|追踪|专访|为何|如何|背后|"
    r"investigation|analysis|commentary|interview|why|how)",
    re.I,
)
_COURSE_TITLE_RE = re.compile(
    r"(?:课程|培训班|研修班|招生简章|培训对象|结业证书|学费|课时|"
    r"training course|training program)",
    re.I,
)
_COURSE_OPERATIONAL_MARKERS = (
    re.compile(r"(?:报名|招生|申请入学|enrol|enroll|apply now)", re.I),
    re.compile(r"(?:学费|费用|tuition|course fee)", re.I),
    re.compile(r"(?:课时|课程安排|教学计划|curriculum|syllabus)", re.I),
    re.compile(r"(?:结业证书|培训证书|certificate)", re.I),
    re.compile(r"(?:培训对象|招生对象|适合人群|target audience)", re.I),
)
_EDITORIAL_TITLE_RE = re.compile(
    r"(?:新闻分析|调查|深度|分析|评论|观察|财报|为何|如何|背后|影响|"
    r"风险|供应链|制度|改革|市场却|investigation|analysis|why|how|impact)",
    re.I,
)
_REPORTING_MARKERS = (
    re.compile(r"(?:记者|采访|author[:：]|作者[:：])", re.I),
    re.compile(r"(?:回应|表示|指出|认为|称|told|said)", re.I),
    re.compile(r"(?:报告称|数据显示|研究显示|according to|the report)", re.I),
    re.compile(r"(?:专家|分析师|研究员|机构|公司方面)", re.I),
)
_TRUSTED_EDITORIAL_DOMAINS = (
    "yicai.com",
    "news.cn",
    "xinhuanet.com",
    "eeo.com.cn",
)
_ORIGINAL_LINK_RE = re.compile(
    r"(?:原文链接|original\s+(?:article|link))\s*[:：]?\s*\n?\s*"
    r"(?P<url>https?://[^\s)]+)",
    re.I,
)
_SOURCE_LINE_RE = re.compile(r"来源[:：]\s*\[?(?P<source>[^\]\n]{2,40})", re.I)


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


def _formal(
    *,
    reason: str,
    content_type: str,
    source_relationship: str = "original",
    original_publisher: str = "",
    original_url: str = "",
) -> ClassificationResult:
    return ClassificationResult(
        page_role="standalone_content",
        page_type="article",
        content_type=content_type,
        candidate_disposition="formal_candidate",
        source_relationship=source_relationship,
        original_publisher=original_publisher,
        original_url=original_url,
        source_action="retain_with_source_label",
        confidence="high",
        reason=reason,
    )


def _body_main(markdown: str) -> str:
    text = str(markdown or "")
    heading = re.search(r"(?m)^#\s+[^#\n].+$", text)
    if heading:
        text = text[heading.start() :]
    boundary = re.search(
        r"(?m)^#{1,4}\s*(?:相关阅读|推荐阅读|热门推荐|新闻排行|视频排行|"
        r"本周热文|更多推荐|评论|相关文章)\s*$",
        text,
        re.I,
    )
    if boundary:
        text = text[: boundary.start()]
    return text[:16000]


def _count_markers(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _domain(url: str) -> str:
    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


def _trusted_editorial_domain(url: str) -> bool:
    domain = _domain(url)
    return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in _TRUSTED_EDITORIAL_DOMAINS)


def classify_candidate_v056k(
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
    markdown_text = str(markdown or "")
    identity = evaluate_content_identity(title=title, markdown=markdown_text)
    title_text = identity.resolved_title or str(title or "").strip()
    main = _body_main(markdown_text)
    sample = "\n".join((str(description or ""), main))

    if _DIGEST_RE.search(sample):
        return _reject(
            "curated_news_digest_v056k",
            "newsletter_or_roundup",
            "curated_news_digest",
        )

    if (
        _IMAGE_POLICY_RE.search(title_text)
        and _IMAGE_POLICY_RE.search(sample)
        and identity.image_count >= 1
        and identity.body_prose_chars < 2200
    ):
        return _reject(
            "visual_policy_card_v056k",
            "visual_data_card",
            "infographic",
        )

    if (
        _FINANCING_TITLE_RE.search(title_text)
        and len(_FINANCING_BODY_RE.findall(sample)) >= 2
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _reject(
            "financing_promotion_v056k",
            "press_release",
            "financing_promotion",
        )

    if (
        _STUDENT_ACTIVITY_TITLE_RE.search(title_text)
        and _STUDENT_ACTIVITY_BODY_RE.search(sample)
    ):
        return _reject(
            "student_or_internship_activity_v056k",
            "institutional_activity",
            "student_social_practice_recap",
        )

    if (
        _EVENT_TITLE_RE.search(title_text)
        and _count_markers(_EVENT_BODY_MARKERS, sample) >= 3
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _reject(
            "institutional_event_recap_v056k",
            "event_or_release_announcement",
            "conference_recap",
        )

    original_link = _ORIGINAL_LINK_RE.search(markdown_text)
    if original_link and identity.body_prose_chars >= 2500:
        original_url = original_link.group("url").rstrip(".,;，。；")
        publisher = urlsplit(original_url).netloc.lower().removeprefix("www.")
        if publisher:
            return _formal(
                reason="complete_translated_republish_v056k",
                content_type="translated_republish",
                source_relationship="translated_republish",
                original_publisher=publisher,
                original_url=original_url,
            )

    result = _base_classify(
        url=url,
        title=title_text,
        description=description,
        author=author,
        markdown=markdown_text,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=(identity.body_prose_chars or content_chars),
    )

    # Site chrome must not be sufficient evidence for a course/training page.
    if (
        result.reason == "course_or_training"
        and not _COURSE_TITLE_RE.search(title_text)
        and _count_markers(_COURSE_OPERATIONAL_MARKERS, main) < 2
    ):
        result = _base_classify(
            url=url,
            title=title_text,
            description=description,
            author=author,
            markdown="",
            published_at=published_at,
            verification_level=verification_level,
            content_chars=(identity.body_prose_chars or content_chars),
        )
        if result.candidate_disposition == "formal_candidate":
            result.reason = "course_template_false_positive_recovered_v056k"

    if (
        result.reason == "insufficient_editorial_evidence"
        and verification_level in {"B", "C"}
        and identity.body_prose_chars >= 1800
        and _trusted_editorial_domain(url)
    ):
        reporting_score = _count_markers(_REPORTING_MARKERS, sample)
        structural_signal = identity.heading_count >= 2 or identity.title_similarity >= 0.75
        if _EDITORIAL_TITLE_RE.search(title_text) or (reporting_score >= 2 and structural_signal):
            result = _formal(
                reason=(
                    "strong_editorial_body_without_reliable_date_v056k"
                    if verification_level == "C"
                    else "strong_editorial_structure_v056k"
                ),
                content_type="analysis_or_commentary",
            )

    # Transparent hosted republication remains usable when the full article is
    # present, but the source relationship must be explicit.
    if result.candidate_disposition == "formal_candidate" and _domain(url).endswith("chinanews.com.cn"):
        source_match = _SOURCE_LINE_RE.search(main[:5000])
        if source_match:
            source = source_match.group("source").strip()
            if source and "中新" not in source:
                result.source_relationship = "secondary_republish"
                result.original_publisher = source
                result.source_action = "retain_with_source_label"
                result.reason = f"{result.reason}; transparent_source_line_v056k"

    return result


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056k"]
