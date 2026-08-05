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
    re.compile(r"(?:主旨报告|主题报告|主旨发言|分论坛|议程|agenda)", re.I),
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
_SOURCE_LINE_RE = re.compile(
    r"来源[:：]\s*[_*\[]*"
    r"(?P<source>[\u4e00-\u9fffA-Za-z0-9·（）()《》.\-]{2,40})",
    re.I,
)
_TRANSLATION_BYLINE_RE = re.compile(
    r"(?:translated\s+by|translation\s+by|译者\s*[:：]|翻译\s*[:：])",
    re.I,
)
_PRIMARY_DOCUMENT_TITLE_RE = re.compile(
    r"(?:通知|规划|条例|办法|意见|公告|决定|通告|批复|令)$|"
    r"(?:关于.{0,80}(?:通知|意见|公告|决定|批复))",
    re.I,
)
_HOST_SOURCE_TOKENS: dict[str, tuple[str, ...]] = {
    "chinanews.com.cn": ("中新网", "中国新闻网"),
    "cnr.cn": ("央广网", "中央广播电视总台"),
    "news.cn": ("新华社", "新华网"),
    "xinhuanet.com": ("新华社", "新华网"),
    "cssn.cn": ("中国社会科学网", "中国社会科学院", "财经战略研究院"),
    "mee.gov.cn": ("生态环境部",),
    "cq.gov.cn": ("重庆市人民政府", "重庆市政府网"),
    "china.com": ("中华网",),
    "eeo.com.cn": ("经济观察网", "经济观察报"),
    "yicai.com": ("第一财经",),
}


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


def _source_is_current_host(source: str, url: str) -> bool:
    domain = _domain(url)
    for suffix, tokens in _HOST_SOURCE_TOKENS.items():
        if domain == suffix or domain.endswith(f".{suffix}"):
            return any(token in source for token in tokens)
    return False


def _transparent_source(main: str, url: str) -> str:
    source_match = _SOURCE_LINE_RE.search(main[:2500])
    if not source_match:
        return ""
    source = source_match.group("source").strip(" _*[]")
    if not source or _source_is_current_host(source, url):
        return ""
    return source


def _apply_transparent_source(
    result: ClassificationResult,
    *,
    source: str,
) -> ClassificationResult:
    if not source or result.source_relationship == "translated_republish":
        return result
    result.source_relationship = "secondary_republish"
    result.original_publisher = source
    if result.candidate_disposition != "reject":
        result.source_action = "retain_with_source_label"
    marker = "transparent_source_line_v056k"
    if marker not in result.reason:
        result.reason = f"{result.reason}; {marker}" if result.reason else marker
    return result


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
    transparent_source = _transparent_source(main, url)

    if _DIGEST_RE.search(sample):
        return _apply_transparent_source(
            _reject(
                "curated_news_digest_v056k",
                "newsletter_or_roundup",
                "curated_news_digest",
            ),
            source=transparent_source,
        )

    if (
        _IMAGE_POLICY_RE.search(title_text)
        and _IMAGE_POLICY_RE.search(sample)
        and identity.image_count >= 1
        and identity.body_prose_chars < 2200
    ):
        return _apply_transparent_source(
            _reject(
                "visual_policy_card_v056k",
                "visual_data_card",
                "infographic",
            ),
            source=transparent_source,
        )

    if (
        _FINANCING_TITLE_RE.search(title_text)
        and len(_FINANCING_BODY_RE.findall(sample)) >= 2
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _apply_transparent_source(
            _reject(
                "financing_promotion_v056k",
                "press_release",
                "financing_promotion",
            ),
            source=transparent_source,
        )

    if (
        _STUDENT_ACTIVITY_TITLE_RE.search(title_text)
        and _STUDENT_ACTIVITY_BODY_RE.search(sample)
    ):
        return _apply_transparent_source(
            _reject(
                "student_or_internship_activity_v056k",
                "institutional_activity",
                "student_social_practice_recap",
            ),
            source=transparent_source,
        )

    event_evidence = "\n".join((title_text, main[:3000]))
    if (
        _EVENT_TITLE_RE.search(event_evidence)
        and _count_markers(_EVENT_BODY_MARKERS, main[:6000]) >= 3
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _apply_transparent_source(
            _reject(
                "institutional_event_recap_v056k",
                "event_or_release_announcement",
                "conference_recap",
            ),
            source=transparent_source,
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

    # A contextual mention of a translation must not relabel an original
    # article. Require an explicit translation byline or an original link.
    if (
        result.source_relationship == "translated_republish"
        and original_link is None
        and not _TRANSLATION_BYLINE_RE.search(main[:2500])
    ):
        result.source_relationship = "original"
        result.original_publisher = ""
        result.original_url = ""
        result.source_action = "retain_with_source_label"
        result.reason = "translation_context_false_positive_recovered_v056k"

    result = _apply_transparent_source(result, source=transparent_source)

    # A reliable hosting page may carry either a primary government document
    # or a full reported article. Keep actual primary documents in the special
    # lane, but convert transparent media republications back to the article
    # lane instead of treating the host domain as authorship evidence.
    if (
        result.candidate_disposition == "special_candidate"
        and result.source_relationship == "secondary_republish"
        and not _PRIMARY_DOCUMENT_TITLE_RE.search(title_text)
        and identity.body_prose_chars >= 1800
    ):
        result = _formal(
            reason="transparent_reported_republish_v056k",
            content_type="reported_republish",
            source_relationship="secondary_republish",
            original_publisher=transparent_source,
        )

    return result


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056k"]
