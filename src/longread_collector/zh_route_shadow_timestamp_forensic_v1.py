"""Read-only timestamp forensic checks for Chinese Route Shadow S1.

This module never runs Discovery, fetches a URL, mutates a persisted row or
changes Treatment/Control behavior. It inspects already-persisted route item
rows and identifies timestamp evidence that is internally inconsistent with
first-party URL paths or article-local relative-age text.

The purpose is to prevent L4/L5 route-utility interpretation from treating a
measurement-association defect as route staleness or freshness.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

S1_TIMESTAMP_FORENSIC_VERSION = "zh-route-shadow-timestamp-forensic-v1.1"

# Conventional first-party date paths, e.g. /2026/08/27/ or /2026-08-27/.
_URL_PATH_DATE_RE = re.compile(
    r"/(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])(?:/|$)"
)
# EEO uses a compact month/day path, e.g. /2026/0827/1013692.shtml.
_URL_PATH_COMPACT_MD_RE = re.compile(
    r"/(20\d{2})/(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:/|$)"
)
_RELATIVE_AGE_RE = re.compile(r"(?P<n>\d{1,3})\s*(?P<unit>分钟|小时)前")


@dataclass(slots=True)
class TimestampForensicFinding:
    source_id: str
    surface_id: str
    url_canonical: str
    finding: str
    persisted_published_at: str
    url_path_date: str = ""
    relative_age_text: str = ""
    relative_age_expected_at: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any, *, tz: ZoneInfo) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _validated_path_date(year: str, month: str, day: str) -> str:
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError:
        return ""
    return parsed.isoformat()


def url_path_date(value: Any) -> str:
    """Return an explicit path date without inferring publication semantics.

    Supported first-party shapes are deliberately narrow:
    - YYYY/MM/DD or YYYY-MM-DD;
    - EEO-style YYYY/MMDD.
    """

    path = urlsplit(_text(value)).path
    match = _URL_PATH_DATE_RE.search(path)
    if match:
        return _validated_path_date(match.group(1), match.group(2), match.group(3))

    compact = _URL_PATH_COMPACT_MD_RE.search(path)
    if compact:
        return _validated_path_date(compact.group(1), compact.group(2), compact.group(3))
    return ""


def _relative_age_evidence(title: str, observed_at: datetime) -> tuple[str, datetime | None]:
    """Parse only explicit article-local `N分钟前/N小时前` text from the item title."""

    matches = list(_RELATIVE_AGE_RE.finditer(_text(title)))
    if not matches:
        return "", None
    match = matches[-1]
    amount = int(match.group("n"))
    delta = timedelta(minutes=amount) if match.group("unit") == "分钟" else timedelta(hours=amount)
    expected = observed_at - delta
    expected = expected.replace(second=0, microsecond=0)
    return match.group(0), expected


def audit_item_timestamp(row: dict[str, Any]) -> list[TimestampForensicFinding]:
    """Return only explicit, reproducible timestamp-association findings."""

    tz = ZoneInfo("Asia/Shanghai")
    source_id = _text(row.get("source_id"))
    surface_id = _text(row.get("surface_id"))
    url = _text(row.get("url_canonical")) or _text(row.get("url"))
    published_text = _text(row.get("published_at"))
    published = _parse_datetime(published_text, tz=tz)
    path_date = url_path_date(url)
    observed = _parse_datetime(row.get("treatment_observed_at_bj"), tz=tz)
    findings: list[TimestampForensicFinding] = []

    if path_date:
        if published is None:
            findings.append(
                TimestampForensicFinding(
                    source_id=source_id,
                    surface_id=surface_id,
                    url_canonical=url,
                    finding="url_path_date_available_but_unbound",
                    persisted_published_at=published_text,
                    url_path_date=path_date,
                )
            )
        elif published.date().isoformat() != path_date:
            findings.append(
                TimestampForensicFinding(
                    source_id=source_id,
                    surface_id=surface_id,
                    url_canonical=url,
                    finding="url_path_date_conflict",
                    persisted_published_at=published_text,
                    url_path_date=path_date,
                )
            )

    if observed is not None:
        relative_text, expected = _relative_age_evidence(_text(row.get("title")), observed)
        if relative_text and expected is not None:
            if published is None:
                findings.append(
                    TimestampForensicFinding(
                        source_id=source_id,
                        surface_id=surface_id,
                        url_canonical=url,
                        finding="relative_age_available_but_unbound",
                        persisted_published_at=published_text,
                        relative_age_text=relative_text,
                        relative_age_expected_at=expected.isoformat(),
                    )
                )
            else:
                # Relative-age labels are rounded UI evidence, so tolerate up to
                # two hours. The guard catches cross-card/day-scale binding, not
                # an exact publication timestamp.
                if abs((published - expected).total_seconds()) > 2 * 3600:
                    findings.append(
                        TimestampForensicFinding(
                            source_id=source_id,
                            surface_id=surface_id,
                            url_canonical=url,
                            finding="relative_age_binding_conflict",
                            persisted_published_at=published_text,
                            relative_age_text=relative_text,
                            relative_age_expected_at=expected.isoformat(),
                        )
                    )

    return findings


def audit_timestamp_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate timestamp-association findings without changing source rows."""

    materialized = list(rows)
    findings = [finding for row in materialized for finding in audit_item_timestamp(row)]
    counts = Counter(finding.finding for finding in findings)
    by_surface: dict[str, Counter[str]] = defaultdict(Counter)
    for finding in findings:
        key = f"{finding.source_id}:{finding.surface_id}"
        by_surface[key][finding.finding] += 1

    conflict_types = {"url_path_date_conflict", "relative_age_binding_conflict"}
    conflict_count = sum(counts[name] for name in conflict_types)
    availability_without_binding = (
        counts["url_path_date_available_but_unbound"]
        + counts["relative_age_available_but_unbound"]
    )

    return {
        "version": S1_TIMESTAMP_FORENSIC_VERSION,
        "item_rows": len(materialized),
        "finding_count": len(findings),
        "conflict_count": conflict_count,
        "available_but_unbound_count": availability_without_binding,
        "finding_counts": dict(sorted(counts.items())),
        "by_surface": {
            key: dict(sorted(value.items())) for key, value in sorted(by_surface.items())
        },
        "findings": [finding.as_dict() for finding in findings],
        "timestamp_utility_interpretable": conflict_count == 0,
    }


__all__ = [
    "S1_TIMESTAMP_FORENSIC_VERSION",
    "TimestampForensicFinding",
    "audit_item_timestamp",
    "audit_timestamp_rows",
    "url_path_date",
]
