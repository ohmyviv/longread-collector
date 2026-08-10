"""PR-7.3.2 publication follow-up for Canonical Article (L4).

PR-7.3.1 fixed provenance loss and demoted the legacy 6000-character
``body_header_standalone_date`` heuristic when its hit was not truly local to
the article header. The first post-hotfix zh_midday natural run then exposed the
opposite narrow gap: an aggregator page displayed an explicit absolute datetime
immediately below the article title (``2026-08-10 08:00 [查看原文]``), but no
labeled-date rule recognized it.

This wrapper adds one conservative positive cue: a standalone numeric absolute
date/datetime on its own header line inside a tight title-local window. It does
not restore broad body scanning and therefore keeps the C&EN Related-card guard.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import AcquisitionBundle, Evidence, StageName
from .evidence import normalize_space
from . import publication_v0731 as _base

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.3.2"
PublicationResolution = _base.PublicationResolution
_SOURCE = "body_header_standalone_datetime"

_TITLE_LOCAL_STANDALONE_DATETIME_RE = re.compile(
    r"(?m)^[ \t]*"
    r"(?P<value>(?:19|20)\d{2}(?:"
    r"[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"年\d{1,2}月\d{1,2}(?:日)?"
    r")"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?)?)"
    r"[ \t]*(?=(?:\[|$|作者[：:]|来源[：:]|來源[：:]|阅读|閱讀))",
    re.I,
)


def resolve_publication(record, bundle: AcquisitionBundle) -> PublicationResolution:
    candidate = _title_local_candidate(record, bundle)
    if candidate is not None:
        bundle = replace(bundle, evidence=tuple(bundle.evidence) + (candidate,))

    result = _base.resolve_publication(record, bundle)
    evidence = tuple(
        replace(item, extractor=PUBLICATION_VERSION)
        if item.extractor == _base.PUBLICATION_VERSION
        else item
        for item in result.evidence
    )
    return replace(result, evidence=evidence)


def _title_local_candidate(record, bundle: AcquisitionBundle) -> Evidence | None:
    body = bundle.body_markdown or bundle.body_text or ""
    title = record.title_hint or bundle.raw_title
    sample = _title_local_sample(body, title)
    match = _TITLE_LOCAL_STANDALONE_DATETIME_RE.search(sample)
    if match is None:
        return None

    raw = normalize_space(match.group("value"))
    normalized = _base.normalize_publication_date(raw)
    if not normalized:
        return None

    return Evidence(
        evidence_id=f"{record.item_id}-pr732-title-local-publication",
        evidence_type="legacy_publication_date_candidate",
        source_stage=StageName.ACQUISITION,
        field="publication_date_candidate",
        value={
            "value": raw,
            "source": _SOURCE,
            "confidence": 0.96,
            "raw": raw,
            "role": "published",
            "priority": 112,
        },
        confidence=0.96,
        extractor=PUBLICATION_VERSION,
        excerpt=normalize_space(sample[max(0, match.start() - 80) : match.end() + 120])[:280],
    )


def _title_local_sample(body: str, title: str) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        # Exact title first; then progressively shorter leading fragments to
        # survive aggregator-added site suffixes while remaining title-anchored.
        needles = [clean_title]
        for width in (64, 48, 36, 24, 16):
            if len(clean_title) > width:
                needles.append(clean_title[:width])
        for needle in needles:
            position = value.find(needle)
            if 0 <= position <= 12000:
                return value[position : position + 1200]
    return value[:1200]


normalize_publication_date = _base.normalize_publication_date
normalize_publication_fact = _base.normalize_publication_fact

__all__ = [
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "normalize_publication_date",
    "normalize_publication_fact",
    "resolve_publication",
]
