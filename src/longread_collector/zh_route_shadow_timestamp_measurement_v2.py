"""Fail-closed timestamp measurement for Chinese Route Shadow S1.

OFFLINE / READ-ONLY only: no Discovery, network, persisted-row mutation, or
Treatment/Control behavior change. The module derives a conservative S1
publication-time interval from existing route-item telemetry and classifies
freshness without pretending S1 listing evidence is Final Recall A-level proof.
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
_DAY_CLOCK_RE = re.compile(r"(?P<day>今天|昨天)\s*(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)")


@dataclass(slots=True)
class TimeInterval:
    start: datetime
    end: datetime
    evidence_kind: str
    evidence_value: str


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
    return TimeInterval(
        start=datetime.combine(parsed, time.min, tzinfo=tz),
        end=datetime.combine(parsed, time.max, tzinfo=tz),
        evidence_kind=kind,
        evidence_value=date_text,
    )


def _relative_interval(title: str, observed: datetime) -> TimeInterval | None:
    matches = list(_RELATIVE_AGE_RE.finditer(_text(title)))
    if not matches:
        return None
    match = matches[-1]
    amount = int(match.group("n"))
    if match.group("unit") == "小时":
        expected = observed - timedelta(hours=amount)
        uncertainty = timedelta(hours=RELATIVE_HOUR_UNCERTAINTY_HOURS)
    else:
        expected = observed - timedelta(minutes=amount)
        uncertainty = timedelta(minutes=RELATIVE_MINUTE_UNCERTAINTY_MINUTES)
    return TimeInterval(
        start=expected - uncertainty,
        end=min(observed, expected + uncertainty),
        evidence_kind="listing_relative_age_bounded",
        evidence_value=match.group(0),
    )


def _card_day_clock_interval(title: str, observed: datetime) -> TimeInterval | None:
    matches = list(_DAY_CLOCK_RE.finditer(_text(title)))
    if not matches:
        return None
    match = matches[-1]
    day = observed.date() - (timedelta(days=1) if match.group("day") == "昨天" else timedelta())
    value = datetime(
        day.year,
        day.month,
        day.day,
        int(match.group("h")),
        int(match.group("m")),
        tzinfo=observed.tzinfo,
    )
    if value > observed + timedelta(minutes=FUTURE_TOLERANCE_MINUTES):
        return None
    return TimeInterval(
        start=value,
        end=value,
        evidence_kind="listing_card_day_clock",
        evidence_value=match.group(0),
    )


def _persisted_interval(row: dict[str, Any], *, tz: ZoneInfo) -> tuple[TimeInterval | None, bool]:
    published_text = _text(row.get("published_at"))
    confidence = _text(row.get("publication_time_confidence")).lower()
    source = _text(row.get("publication_time_source"))
    if not published_text:
        return None, False
    if confidence not in {"high", "date_only"}:
        return None, True
    if _is_date_only(published_text, confidence, source):
        return _day_interval(published_text, tz=tz, kind="persisted_date_only"), False
    parsed = _parse_datetime(published_text, tz=tz)
    if parsed is None:
        return None, True
    return TimeInterval(
        start=parsed,
        end=parsed,
        evidence_kind="persisted_trusted_exact",
        evidence_value=published_text,
    ), False


def _intervals_compatible(a: TimeInterval, b: TimeInterval) -> bool:
    return max(a.start, b.start) <= min(a.end, b.end)


def _all_compatible(intervals: list[TimeInterval]) -> bool:
    return all(
        _intervals_compatible(intervals[i], intervals[j])
        for i in range(len(intervals))
        for j in range(i + 1, len(intervals))
    )


def _intersection(intervals: list[TimeInterval]) -> TimeInterval:
    return TimeInterval(
        start=max(value.start for value in intervals),
        end=min(value.end for value in intervals),
        evidence_kind="+".join(value.evidence_kind for value in intervals),
        evidence_value=" | ".join(value.evidence_value for value in intervals),
    )


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
    row: dict[str, Any], *, freshness_days: int = DEFAULT_FRESHNESS_DAYS
) -> TimestampMeasurement:
    """Derive one conservative S1 timestamp/freshness measurement."""

    tz = ZoneInfo("Asia/Shanghai")
    source_id = _text(row.get("source_id"))
    surface_id = _text(row.get("surface_id"))
    url = _text(row.get("url_canonical")) or _text(row.get("url"))
    observed = _parse_datetime(row.get("treatment_observed_at_bj"), tz=tz)
    flags: list[str] = []
    if observed is None:
        return TimestampMeasurement(
            source_id, surface_id, url, "unknown", "unknown",
            diagnostic_flags=("missing_or_invalid_observed_at",),
        )

    persisted, untrusted_persisted = _persisted_interval(row, tz=tz)
    if untrusted_persisted:
        flags.append("persisted_timestamp_not_trusted")
    title = _text(row.get("title"))
    relative = _relative_interval(title, observed)
    card_clock = _card_day_clock_interval(title, observed)
    path_date = url_path_date(url)
    path = _day_interval(path_date, tz=tz, kind="first_party_url_path_date") if path_date else None

    measurement_bearing = [
        value for value in (persisted, card_clock, relative) if value is not None
    ]
    if len(measurement_bearing) > 1 and not _all_compatible(measurement_bearing):
        return TimestampMeasurement(
            source_id,
            surface_id,
            url,
            "conflict",
            "conflict",
            primary_evidence="persisted_or_card_timestamp_conflict",
            diagnostic_flags=tuple(sorted(set(flags + ["trusted_evidence_conflict"]))),
        )

    if measurement_bearing:
        interval = _intersection(measurement_bearing)
        if path is not None and not _intervals_compatible(interval, path):
            return TimestampMeasurement(
                source_id,
                surface_id,
                url,
                "conflict",
                "conflict",
                primary_evidence="measurement_vs_url_path_date",
                diagnostic_flags=tuple(sorted(set(flags + ["url_path_date_conflict"]))),
            )
        if relative is not None:
            state = "bounded_relative"
        elif card_clock is not None:
            state = "card_clock_exact"
        elif interval.start == interval.end:
            state = "trusted_exact"
        else:
            state = "date_only"
        return TimestampMeasurement(
            source_id,
            surface_id,
            url,
            state,
            _freshness(interval, observed=observed, freshness_days=freshness_days),
            interval.start.isoformat(),
            interval.end.isoformat(),
            interval.evidence_kind,
            tuple(sorted(set(flags))),
        )

    if path is not None:
        return TimestampMeasurement(
            source_id,
            surface_id,
            url,
            "date_only",
            _freshness(path, observed=observed, freshness_days=freshness_days),
            path.start.isoformat(),
            path.end.isoformat(),
            path.evidence_kind,
            tuple(sorted(set(flags))),
        )

    return TimestampMeasurement(
        source_id,
        surface_id,
        url,
        "unknown",
        "unknown",
        diagnostic_flags=tuple(sorted(set(flags))),
    )


def replay_timestamp_rows(
    rows: Iterable[dict[str, Any]], *, freshness_days: int = DEFAULT_FRESHNESS_DAYS
) -> dict[str, Any]:
    """Aggregate v2 states without mutating source rows."""

    materialized = list(rows)
    measurements = [measure_item_timestamp(row, freshness_days=freshness_days) for row in materialized]
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
    interpretable = freshness_counts["fresh"] + freshness_counts["stale"]
    return {
        "version": S1_TIMESTAMP_MEASUREMENT_VERSION,
        "freshness_days": int(freshness_days),
        "item_rows": len(materialized),
        "measurement_counts": dict(sorted(measurement_counts.items())),
        "freshness_counts": dict(sorted(freshness_counts.items())),
        "interpretable_freshness_rows": interpretable,
        "interpretable_freshness_rate": interpretable / len(materialized) if materialized else None,
        "by_source": {key: dict(sorted(value.items())) for key, value in sorted(by_source.items())},
        "by_surface": {key: dict(sorted(value.items())) for key, value in sorted(by_surface.items())},
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
