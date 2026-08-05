"""Final article-header date fallback for v0.5.6k."""

from __future__ import annotations

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from .content_identity_v056j import evaluate_content_identity
from .publication_date_v056k import (
    BODY_DATE_VERSION,
    BodyDateEvidence,
    extract_body_publication_date as _base_extract,
)

BJ = ZoneInfo("Asia/Shanghai")
_EMPHASIZED_DATE_RE = re.compile(
    r"_?(?P<year>20\d{2})-(?P<month>1[0-2]|0?[1-9])-"
    r"(?P<day>3[01]|[12]\d|0?[1-9])\s+"
    r"(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)"
    r"(?::(?P<second>[0-5]\d))?_?",
)


def _article_window(markdown: str) -> str:
    text = str(markdown or "")
    identity = evaluate_content_identity(title="", markdown=text)
    heading = str(identity.body_heading or "").strip()
    if heading:
        index = text.find(heading)
        if index >= 0:
            return text[index : index + 1800]
    for match in re.finditer(r"(?m)^#\s+(.+)$", text):
        candidate = match.group(1).strip()
        if candidate.startswith("[![") or len(re.sub(r"\W", "", candidate)) < 6:
            continue
        return text[match.start() : match.start() + 1800]
    return text[:1800]


def extract_body_publication_date_final(markdown: str) -> BodyDateEvidence | None:
    evidence = _base_extract(markdown)
    if evidence is not None:
        return evidence
    match = _EMPHASIZED_DATE_RE.search(_article_window(markdown))
    if not match:
        return None
    groups = match.groupdict()
    try:
        value = datetime(
            int(groups["year"]),
            int(groups["month"]),
            int(groups["day"]),
            int(groups["hour"]),
            int(groups["minute"]),
            int(groups.get("second") or 0),
            tzinfo=BJ,
        )
    except (TypeError, ValueError):
        return None
    return BodyDateEvidence(
        value=value,
        source="body_header_emphasized_date",
        confidence="high",
        raw=match.group(0).strip("_"),
        version=BODY_DATE_VERSION,
    )


__all__ = ["BODY_DATE_VERSION", "extract_body_publication_date_final"]
