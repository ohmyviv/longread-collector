"""Narrow real-shadow follow-up rules for v0.5.6i.

The v0.5.6h layer handles stale dates, video/event pages, roundups and
award/funding notices. This layer adds only three deterministic false-accept
classes observed in the later Aug 3 zh_evening shadow run: promotional author
or book launches, single-statistic news briefs, and operational public alerts.
"""

from __future__ import annotations

import re

from .classification import ClassificationResult
from .classification_v056h import classify_candidate_v056h as _base_classify

CLASSIFICATION_VERSION = "collector-v0.5.6i"

_PROMOTIONAL_LAUNCH_TITLE_RE = re.compile(
    r"(?:作者|作家|艺术家).{0,28}(?:推出|发布|出版|携).{0,45}"
    r"(?:力作|新作|新书|作品|系列)|"
    r"(?:新作|新书|作品).{0,35}(?:发布|首发|上市)",
    re.I,
)
_PROMOTIONAL_BODY_RE = re.compile(
    r"(?:扎根生活|潜心耕耘|持续拓宽.{0,20}表达边界|"
    r"兼具思想深度与情感温度|丹青叙古今|词韵展华章|"
    r"隆重推出|重磅推出|倾情打造)",
    re.I,
)
_OPERATIONAL_ALERT_TITLE_RE = re.compile(
    r"^(?:.{0,18}(?:联合)?发布)?(?:橙色|红色|黄色|蓝色)?"
    r"(?:地质灾害|暴雨|台风|高温|山洪|气象|森林火险).{0,18}预警$|"
    r"^.{0,18}(?:气象|灾害|风险).{0,18}(?:预警|提示)$",
    re.I,
)
_SINGLE_STAT_BRIEF_TITLE_RE = re.compile(
    r"^(?:今年以来|上半年|截至目前|目前).{0,35}"
    r"(?:共|累计|已).{0,25}(?:超|达|突破)\s*[0-9一二三四五六七八九十百千万亿]+",
    re.I,
)
_REPORTED_GUARD_RE = re.compile(
    r"(?:调查|分析|观察|为何|如何|背后|困境|争议|影响|反思|"
    r"investigation|analysis|why|how|behind|impact|controversy)",
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


def classify_candidate_v056i(
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
    title_text = str(title or "").strip()
    body = " ".join((str(description or ""), str(markdown or "")[:7000]))

    if (
        _PROMOTIONAL_LAUNCH_TITLE_RE.search(title_text)
        and _PROMOTIONAL_BODY_RE.search(body)
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _reject(
            "promotional_author_or_book_launch_v056i",
            "promotional_article",
            "promotional_content",
        )

    if _OPERATIONAL_ALERT_TITLE_RE.search(title_text):
        return _reject(
            "operational_public_alert_v056i",
            "operational_alert",
            "public_warning",
        )

    if (
        _SINGLE_STAT_BRIEF_TITLE_RE.search(title_text)
        and not _REPORTED_GUARD_RE.search(title_text)
    ):
        return _reject(
            "single_statistic_news_brief_v056i",
            "news_brief",
            "straight_news_brief",
        )

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


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056i"]
