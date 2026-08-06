"""Chinese article-header publication evidence added after v0.5.6l Day 1."""

from __future__ import annotations

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from .publication_date_v056k import BodyDateEvidence
from .publication_date_v056l import extract_body_publication_date_v056l as _base_extract

BJ = ZoneInfo("Asia/Shanghai")
BODY_DATE_VERSION = "body-publication-evidence-v0.5.6m"

_CN_LABEL_DATE_RE = re.compile(
    r"(?:出版时间|文章日期|发布日期|发布时间|日期)\s*[:：]\s*"
    r"(?P<year>20\d{2})[-年/.](?P<month>1[0-2]|0?[1-9])[-月/.]"
    r"(?P<day>3[01]|[12]\d|0?[1-9])日?",
    re.I,
)
_CN_BYLINE_DATE_RE = re.compile(
    r"(?:作者|记者)\s*[:：][^\n]{1,100}?"
    r"(?:来源\s*[:：][^\n]{1,100}?)?"
    r"日期\s*[:：]\s*(?P<year>20\d{2})[-年/.]"
    r"(?P<month>1[0-2]|0?[1-9])[-月/.](?P<day>3[01]|[12]\d|0?[1-9])日?",
    re.I,
)


def _from_match(match: re.Match[str], source: str) -> BodyDateEvidence | None:
    try:
        value = datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            tzinfo=BJ,
        )
    except (TypeError, ValueError):
        return None
    return BodyDateEvidence(
        value=value,
        source=source,
        confidence="high",
        raw=match.group(0).strip(),
        version=BODY_DATE_VERSION,
    )


def extract_body_publication_date_v056m(markdown: str) -> BodyDateEvidence | None:
    evidence = _base_extract(markdown)
    text = str(markdown or "")[:24000]
    candidates: list[BodyDateEvidence] = []
    if evidence is not None:
        candidates.append(evidence)
    for pattern, source in (
        (_CN_BYLINE_DATE_RE, "body_header_chinese_byline_date"),
        (_CN_LABEL_DATE_RE, "body_header_chinese_labeled_date"),
    ):
        for match in pattern.finditer(text):
            candidate = _from_match(match, source)
            if candidate is not None:
                candidates.append(candidate)
    if not candidates:
        return None
    # Prefer the oldest high-confidence article-header date when a live site
    # clock is also present. Generic unlabelled timestamps never enter here.
    candidates.sort(key=lambda item: item.value)
    return candidates[0]


__all__ = ["BODY_DATE_VERSION", "extract_body_publication_date_v056m"]
