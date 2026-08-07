"""Publication-date evidence resolution for Canonical Article.

This module resolves factual publication evidence only. Freshness policy belongs
to the later policy layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts import AcquisitionBundle, DiscoveryRecord, Evidence
from .evidence import make_evidence, nested, normalize_space, text

PUBLICATION_VERSION = "canonical-publication-v0.6-pr2"


@dataclass(frozen=True, slots=True)
class PublicationResolution:
    value: str
    confidence: float
    source: str
    evidence: tuple[Evidence, ...]


def resolve_publication(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> PublicationResolution:
    metadata = record.raw_metadata
    candidates: list[tuple[str, float, str, str]] = []

    body_evidence = nested(metadata, "freshness", "body_publication_evidence", default={})
    body_value = text(body_evidence.get("value") if hasattr(body_evidence, "get") else "")
    body_conf = text(body_evidence.get("confidence") if hasattr(body_evidence, "get") else "")
    if body_value:
        candidates.append(
            (
                body_value,
                0.97 if body_conf.lower() == "high" else 0.88,
                "body_publication_evidence",
                text(body_evidence.get("raw") if hasattr(body_evidence, "get") else ""),
            )
        )

    resolved = text(nested(metadata, "freshness", "published_at_resolved"))
    resolved_conf = text(nested(metadata, "freshness", "published_at_confidence"))
    resolved_source = text(nested(metadata, "freshness", "published_at_source"))
    if resolved:
        conf = {"high": 0.95, "medium": 0.82, "low": 0.58}.get(
            resolved_conf.lower(), 0.72
        )
        candidates.append((resolved, conf, resolved_source or "freshness_metadata", resolved))

    for raw in bundle.raw_dates:
        value = text(raw)
        if value:
            candidates.append((value, 0.76, "acquisition_raw_date", value))

    for raw in record.published_at_hints:
        value = text(raw)
        if value:
            candidates.append((value, 0.66, "discovery_date_hint", value))

    body_date = _extract_labeled_body_date(bundle.body_markdown or bundle.body_text)
    if body_date:
        candidates.append((body_date, 0.90, "body_labeled_date", body_date))

    if not candidates:
        return PublicationResolution("", 0.0, "unknown", ())

    candidates.sort(key=lambda item: item[1], reverse=True)
    value, confidence, source, raw = candidates[0]
    evidence = make_evidence(
        record.item_id,
        "publication_date",
        "published_at",
        value,
        confidence=confidence,
        excerpt=raw,
        extractor=PUBLICATION_VERSION,
    )
    return PublicationResolution(value, confidence, source, (evidence,))


_DATE_PATTERNS = (
    r"(?:出版时间|文章日期|发布日期|发布时间|印发日期|日期)\s*[：:]\s*"
    r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
    r"(?:出版時間|文章日期|發布日期|發布時間|印發日期|日期)\s*[：:]\s*"
    r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
)


def _extract_labeled_body_date(body: str) -> str:
    sample = body[:12000]
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, sample, flags=re.IGNORECASE)
        if not match:
            continue
        raw = normalize_space(match.group(1))
        normalized = (
            raw.replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
        )
        pieces = normalized.split("-")
        if len(pieces) == 3:
            try:
                year, month, day = (int(piece) for piece in pieces)
            except ValueError:
                return raw
            return f"{year:04d}-{month:02d}-{day:02d}"
        return raw
    return ""


__all__ = ["PUBLICATION_VERSION", "PublicationResolution", "resolve_publication"]
