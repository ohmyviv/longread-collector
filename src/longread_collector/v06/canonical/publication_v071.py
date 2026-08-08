"""PR-7.1 publication evidence calibration.

Keep publication resolution factual, but distinguish article-local publication
signals from page/template metadata and surface material conflicts explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
import re
from typing import Iterable

from ..contracts import AcquisitionBundle, DiscoveryRecord, Evidence
from .evidence import make_evidence, nested, normalize_space, text

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.1"


@dataclass(frozen=True, slots=True)
class PublicationResolution:
    value: str
    confidence: float
    source: str
    evidence: tuple[Evidence, ...]
    conflict: bool = False
    conflict_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    value: str
    normalized: str
    confidence: float
    priority: int
    source: str
    raw: str
    article_local: bool


def resolve_publication(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> PublicationResolution:
    candidates = list(_collect_candidates(record, bundle))
    if not candidates:
        return PublicationResolution("", 0.0, "unknown", ())

    candidates.sort(
        key=lambda item: (item.priority, item.confidence, bool(item.normalized)),
        reverse=True,
    )
    selected = candidates[0]

    local_dates = {
        item.normalized
        for item in candidates
        if item.article_local and item.normalized and item.priority >= 110
    }
    credible_dates = {
        item.normalized
        for item in candidates
        if item.normalized and item.priority >= 75 and item.confidence >= 0.72
    }

    conflict_values: tuple[str, ...] = ()
    if len(local_dates) > 1:
        conflict_values = tuple(sorted(local_dates))
    elif not local_dates and _material_date_conflict(credible_dates):
        conflict_values = tuple(sorted(credible_dates))

    conflict = bool(conflict_values)
    confidence = min(selected.confidence, 0.45) if conflict else selected.confidence
    source = "conflicting_publication_evidence" if conflict else selected.source

    evidence_rows: list[Evidence] = []
    for candidate in candidates[:8]:
        evidence_rows.append(
            make_evidence(
                record.item_id,
                "publication_date_candidate",
                "published_at",
                candidate.normalized or candidate.value,
                confidence=candidate.confidence,
                excerpt=(
                    f"source={candidate.source}; priority={candidate.priority}; "
                    f"article_local={candidate.article_local}; raw={candidate.raw}"
                ),
                extractor=PUBLICATION_VERSION,
            )
        )
    if conflict:
        evidence_rows.append(
            make_evidence(
                record.item_id,
                "publication_date_conflict",
                "published_at_conflict",
                conflict_values,
                confidence=0.98,
                excerpt="credible publication evidence disagrees materially",
                extractor=PUBLICATION_VERSION,
            )
        )

    return PublicationResolution(
        selected.normalized or selected.value,
        confidence,
        source,
        tuple(evidence_rows),
        conflict=conflict,
        conflict_values=conflict_values,
    )


def _collect_candidates(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> Iterable[_Candidate]:
    metadata = record.raw_metadata

    body_evidence = nested(metadata, "freshness", "body_publication_evidence", default={})
    if hasattr(body_evidence, "get"):
        value = text(body_evidence.get("value"))
        if value:
            source = text(body_evidence.get("source")) or "body_publication_evidence"
            raw = text(body_evidence.get("raw")) or value
            confidence_label = text(body_evidence.get("confidence")).lower()
            confidence = 0.98 if confidence_label == "high" else 0.90
            yield _candidate(
                value,
                confidence,
                122 if _body_source(source) else 108,
                source,
                raw,
                article_local=_body_source(source),
            )

    body_date, body_source, body_raw = _extract_article_local_date(
        bundle.body_markdown or bundle.body_text or "",
        record.title_hint or bundle.raw_title,
    )
    if body_date:
        yield _candidate(
            body_date,
            0.96,
            120,
            body_source,
            body_raw,
            article_local=True,
        )

    resolved = text(nested(metadata, "freshness", "published_at_resolved"))
    if resolved:
        resolved_conf = text(nested(metadata, "freshness", "published_at_confidence")).lower()
        resolved_source = text(nested(metadata, "freshness", "published_at_source")) or "freshness_metadata"
        confidence = {"high": 0.95, "medium": 0.82, "low": 0.58}.get(
            resolved_conf, 0.72
        )
        local = _body_source(resolved_source)
        yield _candidate(
            resolved,
            confidence,
            116 if local else 80,
            resolved_source,
            resolved,
            article_local=local,
        )

    for raw in bundle.raw_dates:
        value = text(raw)
        if value:
            yield _candidate(
                value,
                0.76,
                75,
                "acquisition_raw_date",
                value,
                article_local=False,
            )

    for raw in record.published_at_hints:
        value = text(raw)
        if value:
            yield _candidate(
                value,
                0.68,
                65,
                "discovery_date_hint",
                value,
                article_local=False,
            )


def _candidate(
    value: str,
    confidence: float,
    priority: int,
    source: str,
    raw: str,
    *,
    article_local: bool,
) -> _Candidate:
    return _Candidate(
        value=value,
        normalized=normalize_publication_date(value),
        confidence=confidence,
        priority=priority,
        source=source,
        raw=normalize_space(raw),
        article_local=article_local,
    )


def _body_source(source: str) -> bool:
    lowered = (source or "").lower()
    return lowered.startswith("body_") or "body_header" in lowered or "article_header" in lowered


def _extract_article_local_date(body: str, title: str) -> tuple[str, str, str]:
    sample = _article_start(body, title)[:7000]
    patterns = (
        (
            r"(?:出版时间|文章日期|发布日期|发布时间|印发日期|日期|来源日期)\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_labeled_date",
        ),
        (
            r"(?:出版時間|文章日期|發布日期|發布時間|印發日期|日期)\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_labeled_date",
        ),
        (
            r"(?:Published|Posted|Created)(?:\s+in|\s+on)?\s*[:：-]?\s*"
            r"([A-Z][a-z]+\s+\d{1,2},\s+(?:19|20)\d{2})",
            "article_header_english_published_date",
        ),
        (
            r"(?:Published|Posted|Created)(?:\s+in|\s+on)?\s*[:：-]?\s*"
            r"((?:19|20)\d{2}-\d{1,2}-\d{1,2})",
            "article_header_english_published_date",
        ),
    )
    for pattern, source in patterns:
        match = re.search(pattern, sample, flags=re.IGNORECASE)
        if match:
            raw = normalize_space(match.group(0))
            return match.group(1), source, raw
    return "", "", ""


def _article_start(body: str, title: str) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        position = value.find(clean_title)
        if 0 <= position <= 12000:
            return value[position:]
    return value[:18000]


def normalize_publication_date(value: str) -> str:
    raw = normalize_space(value)
    if not raw:
        return ""

    chinese = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    match = re.fullmatch(r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?", chinese)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).date().isoformat()
        except ValueError:
            pass

    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass

    for pattern in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return ""


def _material_date_conflict(values: set[str]) -> bool:
    parsed = []
    for value in values:
        try:
            parsed.append(datetime.fromisoformat(value).date())
        except ValueError:
            continue
    if len(parsed) < 2:
        return False
    return (max(parsed) - min(parsed)).days > 7


__all__ = [
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "normalize_publication_date",
    "resolve_publication",
]
