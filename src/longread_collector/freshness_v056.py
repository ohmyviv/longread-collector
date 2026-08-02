"""Auditable publication-date evidence and freshness policy for v0.5.6 PR-C."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from .models import DiscoveredURL

FRESHNESS_VERSION = "publication-evidence-v0.5.6"
BJ = ZoneInfo("Asia/Shanghai")

_URL_DATE_PATTERNS = (
    re.compile(r"/(20\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])(?:/|$)"),
    re.compile(r"/(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?:/|$)"),
    re.compile(r"/(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:/|\D|$)"),
)
_DEPTH_RE = re.compile(
    r"(?:深度|调查|特稿|专访|访谈|解析|长文|in[- ]depth|investigation|"
    r"long\s*read|longform|feature|analysis|interview|explainer)",
    re.IGNORECASE,
)
_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|story|stories|feature|features|analysis|investigation|"
    r"long-read|longread|news|detail|content)/|\.s?html?$",
    re.IGNORECASE,
)
_SPECIAL_PATH_RE = re.compile(
    r"\.pdf$|/(?:doi|journal|journals|paper|papers|publication|publications|"
    r"research-report|reports?|guidance|white-paper|working-paper)/",
    re.IGNORECASE,
)
_SPECIAL_DOMAIN_RE = re.compile(
    r"(?:^|\.)(?:doi\.org|ncbi\.nlm\.nih\.gov|academic\.oup\.com|"
    r"sciencedirect\.com|tandfonline\.com|onlinelibrary\.wiley\.com|"
    r"link\.springer\.com|jstor\.org|nature\.com)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DateEvidence:
    value: datetime
    source: str
    confidence: str
    priority: int
    raw: str
    role: str = "published"


@dataclass(frozen=True, slots=True)
class FreshnessDecision:
    allowed: bool
    reject_reason: str
    track: str
    age_days: int | None
    exception_reason: str
    unknown: bool
    score_ordinal: int
    score_penalty: int


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BJ)
    return value.astimezone(BJ)


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = date_parser.parse(text, fuzzy=False)
        except (TypeError, ValueError, OverflowError):
            return None
    return _normalise_datetime(parsed)


def _url_date(url: str) -> datetime | None:
    path = urlsplit(url).path
    for pattern in _URL_DATE_PATTERNS:
        match = pattern.search(path)
        if not match:
            continue
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                tzinfo=BJ,
            )
        except ValueError:
            continue
    return None


def _walk_date_fields(metadata: dict[str, Any]) -> Iterable[tuple[str, Any]]:
    keys = {
        "datepublished",
        "date_published",
        "publication_date",
        "published_at",
        "published",
        "pubdate",
        "article:published_time",
        "og:published_time",
        "datemodified",
        "date_modified",
        "modified_at",
        "article:modified_time",
    }
    ignored_containers = {"selection", "freshness", "schedule", "runtime"}

    def visit(value: Any, prefix: str = "", depth: int = 0) -> Iterable[tuple[str, Any]]:
        if depth > 3:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()
                if lowered in ignored_containers:
                    continue
                name = f"{prefix}.{key}" if prefix else str(key)
                if lowered in keys:
                    yield name, child
                elif isinstance(child, (dict, list, tuple)):
                    yield from visit(child, name, depth + 1)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value[:20]):
                yield from visit(child, f"{prefix}[{index}]", depth + 1)

    yield from visit(metadata)


def collect_date_evidence(item: DiscoveredURL) -> list[DateEvidence]:
    evidence: list[DateEvidence] = []
    native_method = str(item.metadata.get("native_method", "")).lower()
    raw_published = str(item.published_at or "").strip()
    parsed_published = parse_datetime(raw_published)
    if parsed_published is not None:
        if native_method in {"rss", "atom"}:
            source, confidence, priority = "rss_feed", "high", 100
        elif native_method == "news_sitemap":
            source, confidence, priority = "news_sitemap", "high", 95
        elif native_method == "sitemap":
            source, confidence, priority = "sitemap_lastmod", "low", 45
        elif str(item.discovery_method).lower() == "firecrawl_search":
            source, confidence, priority = "search_result", "low", 35
        else:
            source, confidence, priority = "discovery_metadata", "medium", 70
        evidence.append(
            DateEvidence(parsed_published, source, confidence, priority, raw_published)
        )

    for field_name, raw in _walk_date_fields(item.metadata):
        parsed = parse_datetime(raw)
        if parsed is None:
            continue
        lowered = field_name.lower()
        modified = "modified" in lowered
        if "datepublished" in lowered or "date_published" in lowered:
            source, confidence, priority = "structured_date_published", "high", 90
        elif "article:published_time" in lowered or "og:published_time" in lowered:
            source, confidence, priority = "article_meta_published", "high", 85
        elif modified:
            source, confidence, priority = "date_modified", "medium", 40
        else:
            source, confidence, priority = "page_metadata_published", "medium", 75
        evidence.append(
            DateEvidence(
                parsed,
                source,
                confidence,
                priority,
                str(raw),
                role="modified" if modified else "published",
            )
        )

    parsed_url = _url_date(item.url)
    if parsed_url is not None:
        evidence.append(
            DateEvidence(parsed_url, "url_path", "low", 30, parsed_url.date().isoformat())
        )

    # Captured/first-seen timestamps are deliberately not publication evidence.
    return evidence


def likely_special_document(item: DiscoveredURL) -> bool:
    parts = urlsplit(item.url)
    domain = parts.netloc.lower().removeprefix("www.")
    path = parts.path.lower()
    sample = f"{item.title} {item.description}".lower()
    if _SPECIAL_DOMAIN_RE.search(domain) or _SPECIAL_PATH_RE.search(path):
        return True
    return bool(
        re.search(
            r"\b(?:research report|working paper|white paper|guidance document|"
            r"journal article|systematic review)\b|(?:研究报告|工作论文|指导文件|白皮书|学术论文)",
            sample,
        )
    )


def _depth_and_structure(item: DiscoveredURL) -> tuple[bool, bool]:
    sample = f"{item.title} {item.description}"
    depth = bool(_DEPTH_RE.search(sample))
    path = urlsplit(item.url).path.lower()
    article_structure = bool(_ARTICLE_PATH_RE.search(path)) or len(
        [part for part in path.split("/") if part]
    ) >= 3
    return depth, article_structure


def resolve_publication_date(item: DiscoveredURL) -> dict[str, Any]:
    evidence = collect_date_evidence(item)
    published = [entry for entry in evidence if entry.role == "published"]
    modified = [entry for entry in evidence if entry.role == "modified"]
    published.sort(key=lambda entry: (entry.priority, entry.value), reverse=True)
    modified.sort(key=lambda entry: (entry.priority, entry.value), reverse=True)
    chosen = published[0] if published else None

    conflict_reason = ""
    if chosen is not None:
        materially_different = [
            entry
            for entry in published[1:]
            if abs((entry.value.date() - chosen.value.date()).days) > 2
        ]
        if materially_different:
            conflict_reason = "publication_evidence_conflict:" + "|".join(
                f"{entry.source}={entry.value.date().isoformat()}"
                for entry in materially_different[:4]
            )

    ignored_present = [
        key
        for key in ("captured_at_bj", "first_seen_at_bj", "captured_at", "first_seen_at")
        if item.metadata.get(key)
    ]
    result = {
        "version": FRESHNESS_VERSION,
        "published_at_resolved": chosen.value.isoformat() if chosen else "",
        "published_at_source": chosen.source if chosen else "unknown",
        "published_at_confidence": chosen.confidence if chosen else "unknown",
        "date_modified_at": modified[0].value.isoformat() if modified else "",
        "date_conflict_reason": conflict_reason,
        "freshness_unknown": chosen is None,
        "ignored_non_publication_fields": ignored_present,
        "evidence": [
            {
                **asdict(entry),
                "value": entry.value.isoformat(),
            }
            for entry in sorted(evidence, key=lambda entry: entry.priority, reverse=True)
        ],
    }
    item.metadata["freshness"] = result
    return result


def evaluate_freshness(
    item: DiscoveredURL,
    *,
    now: datetime | None = None,
) -> FreshnessDecision:
    now_bj = _normalise_datetime(now or datetime.now(timezone.utc))
    resolved = resolve_publication_date(item)
    raw = str(resolved["published_at_resolved"])
    parsed = parse_datetime(raw)
    special = likely_special_document(item)
    depth, article_structure = _depth_and_structure(item)
    native = str(item.metadata.get("purpose", "")) == "native_source_scan"

    if special:
        age = (now_bj.date() - parsed.date()).days if parsed else None
        decision = FreshnessDecision(
            True,
            "",
            "special_document",
            age,
            "independent_special_candidate_freshness",
            parsed is None,
            parsed.date().toordinal() if parsed else 0,
            0,
        )
    elif parsed is None:
        weak_open = not native and not (depth and article_structure)
        decision = FreshnessDecision(
            allowed=not weak_open,
            reject_reason="freshness_unknown_weak_open_evidence" if weak_open else "",
            track="ordinary_unknown",
            age_days=None,
            exception_reason=(
                "native_or_strong_article_structure_without_date" if not weak_open else ""
            ),
            unknown=True,
            score_ordinal=0,
            score_penalty=-4 if not native else -1,
        )
    else:
        age = (now_bj.date() - parsed.date()).days
        if age < -2:
            decision = FreshnessDecision(
                False,
                "publication_date_in_future",
                "ordinary",
                age,
                "",
                False,
                parsed.date().toordinal(),
                -8,
            )
        elif age <= 7:
            decision = FreshnessDecision(
                True,
                "",
                "ordinary_7d",
                age,
                "",
                False,
                parsed.date().toordinal(),
                0,
            )
        elif age <= 14 and depth:
            decision = FreshnessDecision(
                True,
                "",
                "deep_read_8_14d",
                age,
                "explicit_depth_signal",
                False,
                parsed.date().toordinal(),
                -1,
            )
        elif age <= 14:
            decision = FreshnessDecision(
                False,
                "stale_8_14d_without_depth",
                "ordinary",
                age,
                "",
                False,
                parsed.date().toordinal(),
                -6,
            )
        else:
            decision = FreshnessDecision(
                False,
                "stale_article_over_14d",
                "ordinary",
                age,
                "",
                False,
                parsed.date().toordinal(),
                -10,
            )

    item.metadata.setdefault("freshness", {}).update(
        {
            "decision_allowed": decision.allowed,
            "freshness_reject_reason": decision.reject_reason,
            "freshness_track": decision.track,
            "freshness_age_days": decision.age_days,
            "freshness_exception_reason": decision.exception_reason,
            "freshness_unknown": decision.unknown,
            "freshness_score_ordinal": decision.score_ordinal,
            "freshness_score_penalty": decision.score_penalty,
        }
    )
    return decision


__all__ = [
    "DateEvidence",
    "FRESHNESS_VERSION",
    "FreshnessDecision",
    "collect_date_evidence",
    "evaluate_freshness",
    "likely_special_document",
    "parse_datetime",
    "resolve_publication_date",
]
