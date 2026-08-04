"""P0 content-identity and page-format rejects for v0.5.6j.

This layer is deliberately narrow. It addresses severe false accepts observed
in the Aug 4 natural shadow run: client-template titles, CCTV video pages,
visual data cards, conference roundtable recaps, and short briefs inflated by
site chrome. Existing v0.5.6i rules remain the base policy.
"""

from __future__ import annotations

import re

from .classification import ClassificationResult
from .classification_v056i import classify_candidate_v056i as _base_classify
from .content_identity_v056j import evaluate_content_identity

CLASSIFICATION_VERSION = "collector-v0.5.6j"

_VIDEO_BODY_RE = re.compile(
    r"(?:新闻1\+1|完整视频|视频丨|△视频|建议打开央视新闻观看|"
    r"当前非Wi-?Fi网络|视频播放失败|\.m3u8)",
    re.I,
)
_VISUAL_TITLE_RE = re.compile(r"^(?:一组数据读懂|一图读懂|图解|海报)[：:：]?", re.I)
_EVENT_RECAP_BODY_RE = re.compile(
    r"(?:由.{0,80}(?:主办|承办).{0,120}(?:圆桌|论坛|研讨会|学术交流)|"
    r"(?:圆桌|论坛|研讨会|学术交流).{0,120}(?:主持人|嘉宾|主办方))",
    re.I | re.S,
)
_EVENT_SPEECH_RE = re.compile(r"(?:表示|指出|认为|介绍|提问|回答|谈到)")
_REPORTED_GUARD_RE = re.compile(
    r"(?:调查|深度|分析|观察|追踪|为何|如何|背后|困境|争议|影响|反思|"
    r"investigation|analysis|why|how|behind|impact|controversy)",
    re.I,
)
_SHORT_BRIEF_GUARD_RE = re.compile(
    r"(?:专访|调查|深度|分析|观察|评论|述评|特稿|报告|研究|"
    r"interview|investigation|analysis|commentary|report)",
    re.I,
)


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


def classify_candidate_v056j(
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
    title_text = identity.resolved_title or str(title or "").strip()
    body = " ".join((str(description or ""), str(markdown or "")[:9000]))

    if identity.generic_title and not identity.body_heading:
        return _reject(
            "template_title_unresolved_v056j",
            "template_or_client_shell",
            "non_article_shell",
        )

    if identity.video_count >= 1 and _VIDEO_BODY_RE.search(body):
        return _reject(
            "video_program_page_v056j",
            "video_page",
            "video_or_multimedia",
        )

    if (
        _VISUAL_TITLE_RE.search(title_text)
        and identity.image_count >= 3
        and identity.body_prose_chars < 2200
    ):
        return _reject(
            "visual_data_card_v056j",
            "visual_data_card",
            "infographic",
        )

    event_excerpt = body[:5000]
    if (
        _EVENT_RECAP_BODY_RE.search(event_excerpt)
        and len(_EVENT_SPEECH_RE.findall(event_excerpt)) >= 3
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _reject(
            "conference_roundtable_recap_v056j",
            "event_or_release_announcement",
            "event_news",
        )

    if (
        identity.body_prose_chars < 900
        and not _SHORT_BRIEF_GUARD_RE.search(title_text)
        and identity.image_count <= 4
    ):
        return _reject(
            "short_news_brief_v056j",
            "news_brief",
            "straight_news_brief",
        )

    return _base_classify(
        url=url,
        title=title_text,
        description=description,
        author=author,
        markdown=markdown,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=(identity.body_prose_chars or content_chars),
    )


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056j"]
