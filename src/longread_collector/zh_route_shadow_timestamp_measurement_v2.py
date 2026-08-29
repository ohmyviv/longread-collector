"""Fail-closed timestamp measurement for Chinese Route Shadow S1.

This is an OFFLINE / READ-ONLY measurement layer. It does not run Discovery,
fetch pages, mutate persisted telemetry, or change Treatment/Control behavior.
It derives an interpretable publication-time interval from already-persisted S1
item rows and classifies freshness conservatively.

The contract is intentionally narrower than Final Recall publication evidence:
S1 listing evidence can support S1 route-freshness measurement, but never
implicitly upgrades to Final Recall A-level publication-time evidence.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from .zh_route_shadow_timestamp_forensic_v1 import url_path_date

S1_TIMESTAMP_MEASUREMENT_VERSION = "zh-route-shadow-timestamp-measurement-v2"
DEFAULT_FRESHNESS_DAYS = 7
FUTURE_TOLERANCE_MINUTES = 5
RELATIVE_HOUR_UNCERTAINTY_HOURS = 2
RELATIVE_MINUTE_UNCERTAINTY_MINUTES = 2

_RELATIVE_AGE_RE = re.compile(r"(?P<n>\d{1,3})\s*(?P<unit>分钟|小时)前")


@dataclass(slots=True)
class TimeInterval:
    start: datetime
    end: datetime
    evidence_kind: str
    evidence_value: str

    def as_dict(self) -> dict[str, str]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "evidence_kind": self.evidence_kind,
            "evidence_value": self.evidence_value,
        }


@dataclass(slots=True)
class TimestampMeasurement:
    source_id: str
    surface_id: str
    url_canonical: str
    measurement_state: str
    freshness_state: str
    interval_start: str = ""
    interval_end: str = ""
    primary_evidence: str = ""
    diagnostic_flags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["diagnostic_flags"] = list(self.diagnostic_flags)
        return value


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


def _is_date_only(text: str, confidence: str, source: str) -> bool:
    value = _text(text)
    if not value:
        return False
    if _text(confidence).lower() == "date_only":
        return True
    if "date" in _text(source).lower() and "clock" not in _text(source).lower():
        return True
    return bool(re.fullmatch(r"20\d{2}-\d{1,2}-\d{1,2}", value))


def _day_interval(date_text: str, *, tz: ZoneInfo, kind: str) -> TimeInterval | None:
    try:
        parsed = date_parser.parse(date_text).date()
    except (TypeError, ValueError, OverflowError):
        return None
    start = datetime.combine(parsed, time.min, tzinfo=tz)
    end = datetime.combine(parsed, time.max, tzinfo=tz)
    return TimeInterval(start=start, end=end, evidence_kind=kind, evidence_value=date_text)


def _relative_interval(title: str, observed: datetime) -> TimeInterval | None:
    matches = list(_RELATIVE_AGE_RE.finditer(_text(title)))
    if not matches:
        return None
    match = matches[-1]
    amount = int(match.group("n"))
    unit = match.group("unit")
    if unit == "小时":
        expected = observed - timedelta(hours=amount)
        uncertainty = timedelta(hours=RELATIVE_HOUR_UNCERTAINTY_HOURS)
    else:
        expected = observed - timedelta(minutes=amount)
        uncertainty = timedelta(minutes=RELATIVE_MINUTE_UNCERTAINTY_MINUTES)
    # A relative-age label cannot imply publication after observation.
    start = expected - uncertainty
    end = min(observed, expected + uncertainty)
    return TimeInterval(
        start=start,
        end=end,
        evidence_kind="listing_relative_age_bounded",
        evidence_value=match.group(0),
    )


def _persisted_interval(row: dict[str, Any], *, tz: ZoneInfo) -> tuple[TimeInterval | None, bool]:
    published_text = _text(row.get("published_at"))
    confidence = _text(row.get("publication_time_confidence")).lower()
    source = _text(row.get("publication_time_source"))
    if not published_text:
        return None, False

    # Only explicitly trusted/high or date-only persisted evidence participates
    # in the v2 measurement. Other persisted values remain diagnostic only.
    trusted = confidence in {"high", "date_only"}
    if not trusted:
        return None, True

    if _is_date_only(published_text, confidence, source):
        return _day_interval(published_text, tz=tz, kind="persisted_date_only"), False

    parsed = _parse_datetime(published_text, tz=tz)
    if parsed is None:
        return None, True
    return (
        TimeInterval(
            start=parsed,
            end=parsed,
            evidence_kind="persisted_trusted_exact",
            evidence_value=published_text,
        ),
        False,
    )


def _intervals_compatible(a: TimeInterval, b: TimeInterval) -> bool:
    return max(a.start, b.start) <= min(a.end, b.end)


def _intersection(intervals: list[TimeInterval]) -> TimeInterval:
    start = max(value.start for value in intervals)
    end = min(value.end for value in intervals)
    evidence = "+".join(value.evidence_kind for value in intervals)
    values = " | ".join(value.evidence_value for value in intervals)
    return TimeInterval(start=start, end=end, evidence_kind=evidence, evidence_value=values)


def _freshness(interval: TimeInterval, *, observed: datetime, freshness_days: int) -> str:
    lower = observed - timedelta(days=max(1, int(freshness_days)))
    upper = observed + timedelta(minutes=FUTURE_TOLERANCE_MINUTES)
    if interval.start > upper:
        return "future"
    if interval.end < lower:
        return "stale"
    if interval.start >= lower and interval.end <= upper:
        return "fresh"
    return "boundary_unknown"


def measure_item_timestamp(
    row: dict[str, Any],
    *,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> TimestampMeasurement:
    """Derive a conservative S1 timestamp/freshness state from one persisted item."""

    tz = ZoneInfo("Asia/Shanghai")
    source_id = _text(row.get("source_id"))
    surface_id = _text(row.get("surface_id"))
    url = _text(row.get("url_canonical")) or _text(row.get("url"))
    observed = _parse_datetime(row.get("treatment_observed_at_bj"), tz=tz)
    flags: list[str] = []

    if observed is None:
        return TimestampMeasurement(
            source_id=source_id,
            surface_id=surface_id,
            url_canonical=url,
            measurement_state="unknown",
            freshness_state="unknown",
            diagnostic_flags=("missing_or_invalid_observed_at",),
        )

    persisted, untrusted_persisted = _persisted_interval(row, tz=tz)
    if untrusted_persisted:
        flags.append("persisted_timestamp_not_trusted")

    relative = _relative_interval(_text(row.get("title")), observed)
    path_date = url_path_date(url)
    path = _day_interval(path_date, tz=tz, kind="first_party_url_path_date") if path_date else None

    # High-confidence exact/date-only persisted evidence and explicit listing
    # relative-age evidence are both measurement-bearing. Contradiction is
    # fail-closed. URL path dates are lower precision: they can fill a missing
    # timestamp, but do not override a trusted exact timestamp on their own.
    measurement_bearing = [value for value in (persisted, relative) if value is not None]
    if len(measurement_bearing) == 2 and not _intervals_compatible(measurement_bearing[0], measurement_bearing[1]):
        return TimestampMeasurement(
            source_id=source_id,
            surface_id=surface_id,
            url_canonical=url,
            measurement_state="conflict",
            freshness_state="conflict",
            primary_evidence="persisted_vs_relative_age",
            diagnostic_flags=tuple(sorted(set(flags + ["trusted_evidence_conflict"]))),
        )

    if measurement_bearing:
        interval = _intersection(measurement_bearing)
        if path is not None and not _intervals_compatible(interval, path):
            # Path date is not strong enough to replace trusted/relative evidence,
            # but the mismatch is material provenance conflict and blocks utility
            # interpretation until resolved.
            return TimestampMeasurement(
                source_id=source_id,
                surface_id=surface_id,
                url_canonical=url,
                measurement_state="conflict",
                freshness_state="conflict",
                primary_evidence="measurement_vs_url_path_date",
                diagnostic_flags=tuple(sorted(set(flags + ["url_path_date_conflict"]))),
            )
        state = "trusted_exact" if interval.start == interval.end else (
            "bounded_relative" if relative is not None else "date_only"
        )
        return TimestampMeasurement(
            source_id=source_id,
            surface_id=surface_id,
            url_canonical=url,
            measurement_state=state,
            freshness_state=_freshness(interval, observed=observed, freshness_days=freshness_days),
            interval_start=interval.start.isoformat(),
            interval_end=interval.end.isoformat(),
            primary_evidence=interval.evidence_kind,
            diagnostic_flags=tuple(sorted(set(flags))),
        )

    if path is not None:
        # First-party path date is calendar-day evidence only. It can support S1
        # freshness when the full day sits inside the window, but never an exact
        # publication timestamp and never Final Recall A-level evidence.
        return TimestampMeasurement(
            source_id=source_id,
            surface_id=surface_id,
            url_canonical=url,
            measurement_state="date_only",
            freshness_state=_freshness(path, observed=observed, freshness_days=freshness_days),
            interval_start=path.start.isoformat(),
            interval_end=path.end.isoformat(),
            primary_evidence=path.evidence_kind,
            diagnostic_flags=tuple(sorted(set(flags))),
        )

    return TimestampMeasurement(
        source_id=source_id,
        surface_id=surface_id,
        url_canonical=url,
        measurement_state="unknown",
        freshness_state="unknown",
        diagnostic_flags=tuple(sorted(set(flags))),
    )


def replay_timestamp_rows(
    rows: Iterable[dict[str, Any]],
    *,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
) -> dict[str, Any]:
    """Aggregate v2 derived states without mutating the source rows."""

    materialized = list(rows)
    measurements = [
        measure_item_timestamp(row, freshness_days=freshness_days) for row in materialized
    ]
    measurement_counts = Counter(value.measurement_state for value in measurements)
    freshness_counts = Counter(value.freshness_state for value in measurements)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    by_surface: dict[str, Counter[str]] = defaultdict(Counter)
    for value in measurements:
        by_source[value.source_id][f"measurement:{value.measurement_state}"] += 1
        by_source[value.source_id][f"freshness:{value.freshness_state}"] += 1
        key = f"{value.source_id}:{value.surface_id}"
        by_surface[key][f"measurement:{value.measurement_state}"] += 1
        by_surface[key][f"freshness:{value.freshness_state}"] += 1

    interpretable = sum(
        freshness_counts[state] for state in ("fresh", "stale")
    )
    return {
        "version": S1_TIMESTAMP_MEASUREMENT_VERSION,
        "freshness_days": int(freshness_days),
        "item_rows": len(materialized),
        "measurement_counts": dict(sorted(measurement_counts.items())),
        "freshness_counts": dict(sorted(freshness_counts.items())),
        "interpretable_freshness_rows": interpretable,
        "interpretable_freshness_rate": (
            interpretable / len(materialized) if materialized else None
        ),
        "by_source": {
            key: dict(sorted(value.items())) for key, value in sorted(by_source.items())
        },
        "by_surface": {
            key: dict(sorted(value.items())) for key, value in sorted(by_surface.items())
        },
        "measurements": [value.as_dict() for value in measurements],
    }


__all__ = [
    "DEFAULT_FRESHNESS_DAYS",
    "S1_TIMESTAMP_MEASUREMENT_VERSION",
    "TimeInterval",
    "TimestampMeasurement",
    "measure_item_timestamp",
    "replay_timestamp_rows",
]
