"""High-confidence publication evidence recovered from extracted article bodies."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from zoneinfo import ZoneInfo

BJ = ZoneInfo("Asia/Shanghai")
BODY_DATE_VERSION = "body-publication-evidence-v0.5.6k"

_HEADER_ISO_RE = re.compile(
    r"(?P<year>20\d{2})[-/.](?P<month>1[0-2]|0?[1-9])[-/.]"
    r"(?P<day>3[01]|[12]\d|0?[1-9])"
    r"(?:\s+(?P<hour>[01]?\d|2[0-3])[:：](?P<minute>[0-5]\d)"
    r"(?::(?P<second>[0-5]\d))?)?"
    r"\s*(?:来源|作者|责任编辑|发布|刊发)",
    re.I,
)
_HEADER_CN_RE = re.compile(
    r"(?P<year>20\d{2})年(?P<month>1[0-2]|0?[1-9])月"
    r"(?P<day>3[01]|[12]\d|0?[1-9])日"
    r"(?:\s+(?P<hour>[01]?\d|2[0-3])[:：](?P<minute>[0-5]\d)"
    r"(?::(?P<second>[0-5]\d))?)?"
    r"\s*(?:来源|作者|责任编辑|发布|刊发)",
    re.I,
)
_PREFIX_DATE_RE = re.compile(
    r"(?:发布时间|发布日期|发布于|刊发时间)\s*[:：]?\s*"
    r"(?P<year>20\d{2})[-年/.](?P<month>1[0-2]|0?[1-9])[-月/.]"
    r"(?P<day>3[01]|[12]\d|0?[1-9])日?"
    r"(?:\s+(?P<hour>[01]?\d|2[0-3])[:：](?P<minute>[0-5]\d)"
    r"(?::(?P<second>[0-5]\d))?)?",
    re.I,
)
_ORIGINAL_LINK_DATE_RE = re.compile(
    r"(?:原文链接|original\s+(?:article|link))\s*[:：]?\s*\n?\s*"
    r"https?://[^\s)]+/(?P<year>20\d{2})/(?P<month>1[0-2]|0?[1-9])"
    r"/(?P<day>3[01]|[12]\d|0?[1-9])(?:/|\D)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class BodyDateEvidence:
    value: datetime
    source: str
    confidence: str
    raw: str
    version: str = BODY_DATE_VERSION

    def as_dict(self) -> dict[str, str]:
        payload = asdict(self)
        payload["value"] = self.value.isoformat()
        return payload


def _from_match(match: re.Match[str], source: str, confidence: str) -> BodyDateEvidence | None:
    groups = match.groupdict()
    try:
        value = datetime(
            int(groups["year"]),
            int(groups["month"]),
            int(groups["day"]),
            int(groups.get("hour") or 0),
            int(groups.get("minute") or 0),
            int(groups.get("second") or 0),
            tzinfo=BJ,
        )
    except (TypeError, ValueError):
        return None
    return BodyDateEvidence(value, source, confidence, match.group(0).strip())


def extract_body_publication_date(markdown: str) -> BodyDateEvidence | None:
    """Return only date evidence anchored to an article header or original link.

    Generic years and dates inside the prose are deliberately ignored. Header
    evidence is searched in the first 20k characters because some outlets emit
    a large navigation shell before the article H1.
    """

    text = str(markdown or "")[:20000]
    candidates: list[BodyDateEvidence] = []
    for pattern, source, confidence in (
        (_HEADER_ISO_RE, "body_header_date", "high"),
        (_HEADER_CN_RE, "body_header_date", "high"),
        (_PREFIX_DATE_RE, "body_header_date", "high"),
        (_ORIGINAL_LINK_DATE_RE, "body_original_url_date", "medium"),
    ):
        match = pattern.search(text)
        if not match:
            continue
        evidence = _from_match(match, source, confidence)
        if evidence is not None:
            candidates.append(evidence)
    if not candidates:
        return None
    candidates.sort(
        key=lambda entry: (entry.confidence == "high", entry.value),
        reverse=True,
    )
    return candidates[0]


__all__ = [
    "BODY_DATE_VERSION",
    "BodyDateEvidence",
    "extract_body_publication_date",
]
