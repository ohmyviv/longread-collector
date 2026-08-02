"""Supplemental, deterministic URL publication evidence for v0.5.6f."""

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


__all__ = ["supplemental_url_date_evidence"]
