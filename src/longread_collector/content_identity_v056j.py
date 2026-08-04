"""Content identity and main-body metrics for the v0.5.6j shadow gate.

The collector previously trusted extractor titles and total Markdown character
counts. Real shadow runs showed two failure modes: client-download template
strings replacing article titles, and navigation/media/template text making a
short brief look like a long article. This module derives a conservative body
heading and main-body character count without changing extraction budgets.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from urllib.parse import urlsplit

CONTENT_IDENTITY_VERSION = "content-identity-v0.5.6j"

_GENERIC_TITLE_RE = re.compile(
    r"^(?:更多资讯请下载.+客户端|请下载.+客户端|下载.+客户端|"
    r"打开.+客户端查看更多|查看更多精彩内容|untitled|home|首页)$",
    re.I,
)
_HEADING_RE = re.compile(r"(?m)^\s*#\s+(.+?)\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^\)]*\)")
_VIDEO_LINK_RE = re.compile(r"\[Video\s*\d*\]\([^\)]*\)|\.m3u8\b", re.I)
_URL_RE = re.compile(r"https?://\S+")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]*\)")
_TEMPLATE_CUTOFF_RE = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?(?:热门推荐|相关推荐|评论(?:\s*\d+)?|"
    r"阅读下一篇|一周热新闻|大家都在看|编辑推荐|Copyright\b|"
    r"扫码下载|关于我们|联系我们)\s*$",
    re.I,
)
_TEMPLATE_LINE_RE = re.compile(
    r"(?:下载客户端|打开.+客户端|我用心你放心|责任编辑[:：]|"
    r"未经授权不得转载|版权所有|网站无障碍|手机版|PC版本)",
    re.I,
)


@dataclass(slots=True)
class ContentIdentityResult:
    original_title: str
    resolved_title: str
    body_heading: str
    title_similarity: float
    gate_result: str
    generic_title: bool
    raw_markdown_chars: int
    body_prose_chars: int
    template_chars: int
    image_count: int
    video_count: int
    heading_count: int
    external_target_domain: str
    evidence: list[str]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["version"] = CONTENT_IDENTITY_VERSION
        return payload


def _plain(value: str) -> str:
    text = re.sub(r"[`*_~]", "", str(value or ""))
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" -|:：")
    return text


def _normalized(value: str) -> str:
    text = _plain(value).lower().replace("’", "'")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def _bigrams(value: str) -> set[str]:
    text = _normalized(value)
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def title_similarity(left: str, right: str) -> float:
    a = _normalized(left)
    b = _normalized(right)
    if not a or not b:
        return 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    a_bigrams = _bigrams(a)
    b_bigrams = _bigrams(b)
    union = a_bigrams | b_bigrams
    jaccard = len(a_bigrams & b_bigrams) / len(union) if union else 0.0
    containment = min(
        len(a_bigrams & b_bigrams) / max(1, len(a_bigrams)),
        len(a_bigrams & b_bigrams) / max(1, len(b_bigrams)),
    )
    return round(max(sequence, jaccard, containment), 4)


def first_body_heading(markdown: str) -> str:
    for match in _HEADING_RE.finditer(str(markdown or "")):
        heading = _plain(match.group(1))
        if heading and not _GENERIC_TITLE_RE.fullmatch(heading):
            return heading[:300]
    return ""


def main_body_metrics(markdown: str) -> dict[str, int]:
    raw = str(markdown or "")
    image_count = len(_IMAGE_RE.findall(raw))
    video_count = len(_VIDEO_LINK_RE.findall(raw))
    heading_count = len(re.findall(r"(?m)^\s*#{1,6}\s+", raw))

    cutoff = _TEMPLATE_CUTOFF_RE.search(raw)
    main = raw[: cutoff.start()] if cutoff else raw
    main = re.sub(r"```.*?```", " ", main, flags=re.S)
    main = _IMAGE_RE.sub(" ", main)
    main = _VIDEO_LINK_RE.sub(" ", main)
    main = _MARKDOWN_LINK_RE.sub(r"\1", main)
    main = _URL_RE.sub(" ", main)

    lines: list[str] = []
    for raw_line in main.splitlines():
        line = _plain(re.sub(r"^\s*(?:#{1,6}|[-*+]|\d+[.)])\s*", "", raw_line))
        if not line or _TEMPLATE_LINE_RE.search(line):
            continue
        if len(line) <= 45 and re.fullmatch(r"[\w\u4e00-\u9fff\s|/·—-]+", line):
            nav_words = ("首页", "要闻", "精选", "国际", "时事", "财经", "思想", "更多")
            if sum(word in line for word in nav_words) >= 2:
                continue
        lines.append(line)

    prose = " ".join(lines)
    prose = re.sub(r"\s+", " ", prose).strip()
    body_prose_chars = len(prose)
    return {
        "raw_markdown_chars": len(raw),
        "body_prose_chars": body_prose_chars,
        "template_chars": max(0, len(raw) - body_prose_chars),
        "image_count": image_count,
        "video_count": video_count,
        "heading_count": heading_count,
    }


def evaluate_content_identity(
    *,
    title: str,
    markdown: str,
    discovered_title: str = "",
    external_link: str = "",
) -> ContentIdentityResult:
    original = _plain(title or discovered_title)
    heading = first_body_heading(markdown)
    generic = bool(_GENERIC_TITLE_RE.fullmatch(original))
    similarity = title_similarity(original, heading) if heading else 0.0
    resolved = original
    evidence: list[str] = []
    gate_result = "pass"

    if generic and heading:
        resolved = heading
        gate_result = "title_recovered_from_body_heading"
        evidence.append("generic_extractor_title")
        evidence.append("credible_markdown_h1")
    elif heading and original and similarity < 0.22:
        gate_result = "title_heading_mismatch"
        evidence.append("low_title_heading_similarity")
    elif not original and heading:
        resolved = heading
        gate_result = "title_recovered_from_body_heading"
        evidence.append("missing_extractor_title")

    external_domain = urlsplit(str(external_link or "")).netloc.lower().removeprefix("www.")
    if external_domain:
        evidence.append(f"external_target_domain={external_domain}")

    metrics = main_body_metrics(markdown)
    return ContentIdentityResult(
        original_title=original,
        resolved_title=resolved,
        body_heading=heading,
        title_similarity=similarity,
        gate_result=gate_result,
        generic_title=generic,
        external_target_domain=external_domain,
        evidence=evidence,
        **metrics,
    )


__all__ = [
    "CONTENT_IDENTITY_VERSION",
    "ContentIdentityResult",
    "evaluate_content_identity",
    "first_body_heading",
    "main_body_metrics",
    "title_similarity",
]
