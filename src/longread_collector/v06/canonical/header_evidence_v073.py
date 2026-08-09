"""Article-header and legacy date-evidence preparation for PR-7.3 L4.

This module only turns already-acquired facts into explicit evidence inputs. It
performs no network I/O and does not apply freshness policy.
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
_LEGACY_URL_DATE_SOURCE_RE = re.compile(r"(?:^|_)(?:url|urlpath|url_path)(?:_|$)", re.I)


def enrich_header_publication_evidence(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> DiscoveryRecord:
    """Prepare publication evidence without promoting weak legacy URL dates.

    PR-7.3 reads the underlying evidence again instead of trusting a legacy
    aggregate blindly. A legacy `published_at_resolved` whose own source says it
    came from the URL path is therefore removed from the selectable metadata
    surface. The URL itself remains available to `publication_v073`, where URL
    dates are recorded as contextual-only evidence.
    """

    metadata = dict(record.raw_metadata)
    freshness = metadata.get("freshness")
    if not isinstance(freshness, dict):
        freshness = {}
    else:
        freshness = dict(freshness)

    changed = False
    publication_url = record.url
    legacy_source = normalize_space(freshness.get("published_at_source")).lower()
    if legacy_source and _LEGACY_URL_DATE_SOURCE_RE.search(legacy_source):
        if freshness.get("published_at_resolved"):
            freshness["published_at_resolved"] = ""
            freshness["published_at_confidence"] = "unknown"
            changed = True
        publication_url = _normalize_legacy_date_url(publication_url)
        if publication_url != record.url:
            changed = True

    existing = freshness.get("body_publication_evidence")
    if not (isinstance(existing, dict) and normalize_space(existing.get("value"))):
        body = bundle.body_markdown or bundle.body_text or ""
        sample = _article_header_sample(body, record.title_hint or bundle.raw_title)
        match = _ZH_SOURCE_TIMESTAMP_RE.search(sample)
        if match is not None:
            raw = normalize_space(match.group(0))
            freshness["body_publication_evidence"] = {
                "value": match.group("date"),
                "source": "body_header_chinese_source_timestamp",
                "confidence": "high",
                "raw": raw,
                "extractor": HEADER_EVIDENCE_VERSION,
            }
            changed = True

    if not changed:
        return record

    metadata["freshness"] = freshness
    return replace(record, raw_metadata=metadata, url=publication_url)


def _article_header_sample(body: str, title: str) -> str:
    clean_title = normalize_space(title)
    if clean_title:
        position = body.find(clean_title)
        if 0 <= position <= 12000:
            return body[position : position + 2500]
    return body[:6000]


def _normalize_legacy_date_url(url: str) -> str:
    """Expose common compact URL dates to the contextual URL-date extractor."""

    # `/2026/0808/...` -> `/2026/08/08/...`
    value = re.sub(
        r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])([0-3]\d)(?=/|$)",
        r"/\1/\2/\3",
        url,
        count=1,
    )
    # `/20260808/...` -> `/2026/08/08/...`
    value = re.sub(
        r"/((?:19|20)\d{2})(0[1-9]|1[0-2])([0-3]\d)(?=/|$)",
        r"/\1/\2/\3",
        value,
        count=1,
    )
    return value


__all__ = ["HEADER_EVIDENCE_VERSION", "enrich_header_publication_evidence"]
