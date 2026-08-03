"""Narrow post-extraction editorial-quality fixes for v0.5.6h.

This layer keeps the validated v0.5.6d source-relationship and special-document
policy, while rejecting page types confirmed as severe false accepts in real
shadow runs: video pages, event announcements/recaps, news roundups, and award
or funding announcements.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .classification import ClassificationResult
from .classification_v056 import classify_candidate_v056 as _base_classify

CLASSIFICATION_VERSION = "collector-v0.5.6h"

_VIDEO_PATH_RE = re.compile(r"/(?:videos?|watch)(?:/|$)", re.I)
_VIDEO_TITLE_RE = re.compile(r"\b(?:video|watch)\b|(?:视频|影像)", re.I)
_ROUNDUP_TITLE_RE = re.compile(
    r"^(?:财新闻|财经早报|新闻早报|今日快讯|每日快讯|"
    r"daily briefing|morning briefing|news roundup)\s*[｜|:：-]",
    re.I,
)
_AWARD_OR_FUNDING_TITLE_RE = re.compile(
    r"\b(?:awarded?|wins?|receives?)\b.{0,90}\b(?:award|prize|premium|medal)\b|"
    r"\b(?:funding program|new grantees?|grant recipients?|award recipients?)\b|"
    r"(?:获奖名单|获奖公告|奖项公告|荣获.{0,30}(?:奖|奖项)|"
    r"获得.{0,30}(?:奖|奖项)|资助项目名单|获资助名单|拟资助名单)",
    re.I,
)
_REPORTED_AWARD_GUARD_RE = re.compile(
    r"\b(?:investigation|analysis|why|how|controversy|fraud|corruption)\b|"
    r"(?:调查|分析|为何|如何|争议|造假|腐败|内幕)",
    re.I,
)
_CN_EVENT_TITLE_RE = re.compile(
    r"(?:成功|顺利|圆满)?(?:举办|召开|举行|开幕).{0,36}"
    r"(?:论坛|年会|会议|研讨会|峰会|大会|工作坊)|"
    r"(?:论坛|年会|会议|研讨会|峰会|大会|工作坊).{0,30}"
    r"(?:成功举办|顺利召开|圆满举行|开幕|回顾|综述|里的)",
    re.I,
)
_EN_EVENT_TITLE_RE = re.compile(
    r"\b(?:conference|summit|webinar|forum|symposium|workshop)\b.{0,80}"
    r"\b(?:opens?|begins?|starts?|agenda|registration|preview|guide|schedule)\b|"
    r"\b(?:opens?|begins?|starts?|agenda|registration|preview|guide|schedule)\b"
    r".{0,80}\b(?:conference|summit|webinar|forum|symposium|workshop)\b",
    re.I,
)
_EVENT_OPENING_TITLE_RE = re.compile(
    r"\b(?:opens?|begins?|starts?)\b(?:\s+(?:monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|today|tomorrow))?",
    re.I,
)
_EVENT_BODY_RE = re.compile(
    r"\b(?:register|registration|rsvp|tickets?|agenda|speakers?|schedule|"
    r"standard pass|vip pass|join us|first webinar)\b|"
    r"(?:报名|参会|议程|嘉宾|主办|承办|举办|召开|会场|门票)",
    re.I,
)
_EVENT_BODY_TYPE_RE = re.compile(
    r"\b(?:conference|summit|webinar|forum|symposium|workshop)\b|"
    r"(?:论坛|年会|会议|研讨会|峰会|大会|工作坊)",
    re.I,
)
_BRIEF_EVENT_TITLE_RE = re.compile(r"\bbrief\b", re.I)


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


def _non_editorial_result(
    *,
    url: str,
    title: str,
    description: str,
    markdown: str,
) -> ClassificationResult | None:
    path = (urlsplit(url).path or "/").lower()
    title_text = str(title or "").strip()
    body = " ".join((str(description or ""), str(markdown or "")[:7000]))

    if _VIDEO_PATH_RE.search(path) or (
        _VIDEO_TITLE_RE.search(title_text) and re.search(r"\bvideo\b|(?:视频)", body, re.I)
    ):
        return _reject("video_page_v056h", "video_page", "video_or_multimedia")

    if _ROUNDUP_TITLE_RE.search(title_text):
        return _reject(
            "news_roundup_v056h",
            "newsletter_or_roundup",
            "news_roundup",
        )

    if _AWARD_OR_FUNDING_TITLE_RE.search(title_text) and not _REPORTED_AWARD_GUARD_RE.search(
        title_text
    ):
        return _reject(
            "award_or_funding_announcement_v056h",
            "award_or_public_notice",
            "institutional_announcement",
        )

    event_title = bool(
        _CN_EVENT_TITLE_RE.search(title_text) or _EN_EVENT_TITLE_RE.search(title_text)
    )
    event_body = bool(_EVENT_BODY_RE.search(body) and _EVENT_BODY_TYPE_RE.search(body))
    event_opening = bool(_EVENT_OPENING_TITLE_RE.search(title_text) and event_body)
    brief_webinar = bool(
        _BRIEF_EVENT_TITLE_RE.search(title_text)
        and re.search(r"\b(?:first\s+)?webinar\b", body, re.I)
        and re.search(r"\bspeakers?\s*:", body, re.I)
    )
    if (event_title and event_body) or event_opening or brief_webinar:
        return _reject(
            "event_announcement_or_recap_v056h",
            "event_or_release_announcement",
            "event_news",
        )
    return None


def classify_candidate_v056h(
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
    non_editorial = _non_editorial_result(
        url=url,
        title=title,
        description=description,
        markdown=markdown,
    )
    if non_editorial is not None:
        return non_editorial
    return _base_classify(
        url=url,
        title=title,
        description=description,
        author=author,
        markdown=markdown,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=content_chars,
    )


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056h"]
