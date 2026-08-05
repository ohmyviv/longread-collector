"""Publication-date evidence added after the v0.5.6k natural holdout."""

from __future__ import annotations

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from .content_identity_v056j import evaluate_content_identity
from .publication_date_v056k import BodyDateEvidence
from .publication_date_v056k_final import extract_body_publication_date_final as _base_extract

BJ = ZoneInfo("Asia/Shanghai")
BODY_DATE_VERSION = "body-publication-evidence-v0.5.6l"

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_BYLINE_DATE_RE = re.compile(
    r"(?:\[[^\]\n]{2,100}\]\([^)]+\)|(?:By\s+)?[A-Z][^\n•·|]{1,100})"
    r"\s*[•·|]\s*"
    r"(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+"
    r"(?P<day>3[01]|[12]\d|0?[1-9])\s*,?\s*(?P<year>20\d{2})",
    re.I,
)


def _article_window(markdown: str) -> str:
    text = str(markdown or "")
    identity = evaluate_content_identity(title="", markdown=text)
    heading = str(identity.body_heading or "").strip()
    if heading:
        index = text.find(heading)
        if index >= 0:
            return text[index : index + 3000]
    for match in re.finditer(r"(?m)^#\s+(.+)$", text):
        candidate = match.group(1).strip()
        if candidate.startswith("[![") or len(re.sub(r"\W", "", candidate)) < 6:
            continue
        return text[match.start() : match.start() + 3000]
    return text[:3000]


def extract_body_publication_date_v056l(markdown: str) -> BodyDateEvidence | None:
    evidence = _base_extract(markdown)
    if evidence is not None:
        return evidence

    match = _BYLINE_DATE_RE.search(_article_window(markdown))
    if not match:
        return None
    month_token = match.group("month").lower().rstrip(".")
    month = _MONTHS.get(month_token) or _MONTHS.get(month_token[:3])
    if month is None:
        return None
    try:
        value = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            tzinfo=BJ,
        )
    except (TypeError, ValueError):
        return None
    return BodyDateEvidence(
        value=value,
        source="body_header_byline_date",
        confidence="high",
        raw=match.group(0).strip(),
        version=BODY_DATE_VERSION,
    )


__all__ = ["BODY_DATE_VERSION", "extract_body_publication_date_v056l"]
