"""Article-header evidence recovery used by the PR-7.3 L4 resolver.

This module only turns already-acquired body text into explicit factual metadata.
It performs no network I/O and does not apply freshness policy.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import AcquisitionBundle, DiscoveryRecord
from .evidence import normalize_space

HEADER_EVIDENCE_VERSION = "canonical-header-evidence-v0.6-pr7.3"

_ZH_SOURCE_TIMESTAMP_RE = re.compile(
    r"(?P<date>(?:19|20)\d{2}年\d{1,2}月\d{1,2}日)"
    r"(?:\s*(?P<time>\d{1,2}:\d{2}))?"
    # Markdown extraction commonly leaves the timestamp in bold immediately
    # before the source label, e.g. **2026年08月08日08:12**来源：...
    r"\s*[*_]{0,3}\s*(?:来源|來源)\s*[：:]?",
    re.I,
)


def enrich_header_publication_evidence(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> DiscoveryRecord:
    """Add a missing body-header publication fact without overwriting evidence."""

    metadata = dict(record.raw_metadata)
    freshness = metadata.get("freshness")
    if not isinstance(freshness, dict):
        freshness = {}
    else:
        freshness = dict(freshness)

    existing = freshness.get("body_publication_evidence")
    if isinstance(existing, dict) and normalize_space(existing.get("value")):
        return record

    body = bundle.body_markdown or bundle.body_text or ""
    sample = _article_header_sample(body, record.title_hint or bundle.raw_title)
    match = _ZH_SOURCE_TIMESTAMP_RE.search(sample)
    if match is None:
        return record

    raw = normalize_space(match.group(0))
    freshness["body_publication_evidence"] = {
        "value": match.group("date"),
        "source": "body_header_chinese_source_timestamp",
        "confidence": "high",
        "raw": raw,
        "extractor": HEADER_EVIDENCE_VERSION,
    }
    metadata["freshness"] = freshness
    return replace(record, raw_metadata=metadata)


def _article_header_sample(body: str, title: str) -> str:
    clean_title = normalize_space(title)
    if clean_title:
        position = body.find(clean_title)
        if 0 <= position <= 12000:
            return body[position : position + 2500]
    return body[:6000]


__all__ = ["HEADER_EVIDENCE_VERSION", "enrich_header_publication_evidence"]
