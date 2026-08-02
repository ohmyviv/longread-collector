"""Supplemental deterministic publication evidence for v0.5.6f."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .freshness_v056 import BJ, DateEvidence

_SEPARATED_DATE_PATTERNS = (
    re.compile(r"/(20\d{2})-(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])(?:/|$)"),
    re.compile(r"/(20\d{2})/(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?:/|$)"),
    re.compile(r"/(20\d{2})/(0[1-9]|1[0-2])([0-3]\d)(?:/|$)"),
    re.compile(r"(?:/|[t_-])(20\d{2})(0[1-9]|1[0-2])([0-3]\d)(?:[_./-]|$)"),
)
_MONTH_SEGMENT_RE = re.compile(r"/(20\d{2})(0[1-9]|1[0-2])(?:/|$)")
_UNIX_DETAIL_RE = re.compile(r"/(?:detail|article)/(1[0-9]{9})(?:\d+)?(?:\.s?html?)?(?:/|$)")

# Only explicit self-publication/republication language is accepted.  A bare
# year in an article summary remains contextual evidence and is ignored.
_ZH_PUBLICATION_YEAR_RE = re.compile(
    r"(?P<year>20\d{2})年.{0,24}?(?:首次)?(?:发布|发表|刊发|上线|转载|重刊|获授权转载)",
    re.I,
)
_EN_PUBLICATION_YEAR_RES = (
    re.compile(
        r"(?:originally|first)\s+(?:published|posted|released)\s+(?:in\s+)?(?P<year>20\d{2})",
        re.I,
    ),
    re.compile(
        r"(?:republished|reprinted|updated)\s+(?:in\s+)?(?P<year>20\d{2})",
        re.I,
    ),
)


def _date(year: str, month: str, day: str) -> datetime | None:
    try:
        return datetime(int(year), int(month), int(day), tzinfo=BJ)
    except ValueError:
        return None


def supplemental_url_date_evidence(url: str) -> list[DateEvidence]:
    path = urlsplit(url).path
    evidence: list[DateEvidence] = []

    for pattern in _SEPARATED_DATE_PATTERNS:
        match = pattern.search(path)
        if not match:
            continue
        parsed = _date(*match.groups())
        if parsed is not None:
            evidence.append(
                DateEvidence(
                    parsed,
                    "url_path_legacy_date",
                    "medium",
                    34,
                    parsed.date().isoformat(),
                )
            )
            return evidence

    unix_match = _UNIX_DETAIL_RE.search(path)
    if unix_match:
        try:
            parsed = datetime.fromtimestamp(
                int(unix_match.group(1)), timezone.utc
            ).astimezone(BJ)
        except (OverflowError, OSError, ValueError):
            parsed = None
        if parsed is not None and 2000 <= parsed.year <= 2100:
            evidence.append(
                DateEvidence(
                    parsed,
                    "url_unix_timestamp",
                    "medium",
                    38,
                    unix_match.group(1),
                )
            )
            return evidence

    month_match = _MONTH_SEGMENT_RE.search(path)
    if month_match:
        parsed = _date(month_match.group(1), month_match.group(2), "1")
        if parsed is not None:
            evidence.append(
                DateEvidence(
                    parsed,
                    "url_month_segment",
                    "low",
                    28,
                    f"{month_match.group(1)}-{month_match.group(2)}",
                )
            )
    return evidence


def supplemental_text_date_evidence(text: str) -> list[DateEvidence]:
    sample = str(text or "")[:4000]
    match = _ZH_PUBLICATION_YEAR_RE.search(sample)
    if match is None:
        for pattern in _EN_PUBLICATION_YEAR_RES:
            match = pattern.search(sample)
            if match is not None:
                break
    if match is None:
        return []

    parsed = _date(match.group("year"), "1", "1")
    if parsed is None:
        return []
    return [
        DateEvidence(
            parsed,
            "snippet_explicit_publication_year",
            "low",
            27,
            match.group(0),
        )
    ]


__all__ = [
    "supplemental_text_date_evidence",
    "supplemental_url_date_evidence",
]
