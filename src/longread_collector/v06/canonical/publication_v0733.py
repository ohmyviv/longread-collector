"""PR-7.3.3 publication follow-up for Canonical Article (L4).

The first post-PR-7.3.2 scheduled natural shadow exposed a narrow title-local
metadata shape that remained invisible to the publication resolver. Jiemian-style
article headers place the author link, absolute datetime, view count and source
label on the same line, for example::

    [Author](...) · 2026年08月06日 05:07 浏览 8.7w 来源：Publisher

PR-7.3.2 intentionally required a standalone datetime to begin its own line so
that the old broad body-date scan could not reintroduce Related-card false
positives. This wrapper keeps that guard and adds one equally narrow cue: an
absolute date/datetime inside a tight title-local byline/metadata line that also
contains a byline separator, a view/read marker and an explicit source label.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import AcquisitionBundle, Evidence, StageName
from .evidence import normalize_space
from . import publication_v0732 as _base

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.3.3"
PublicationResolution = _base.PublicationResolution
_SOURCE = "body_header_byline_datetime"

_ABSOLUTE_DATETIME_RE = re.compile(
    r"(?P<value>(?:19|20)\d{2}(?:"
    r"[-/.]\d{1,2}[-/.]\d{1,2}|"
    r"年\d{1,2}月\d{1,2}(?:日)?"
    r")"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?)?)",
    re.I,
)
_SOURCE_MARKER_RE = re.compile(r"(?:来源|來源)\s*[：:]", re.I)
_READ_MARKER_RE = re.compile(r"(?:浏览|瀏覽|阅读|閱讀)", re.I)


def resolve_publication(record, bundle: AcquisitionBundle) -> PublicationResolution:
    candidate = _title_local_byline_candidate(record, bundle)
    if candidate is not None:
        bundle = replace(bundle, evidence=tuple(bundle.evidence) + (candidate,))

    result = _base.resolve_publication(record, bundle)
    evidence = tuple(
        replace(item, extractor=PUBLICATION_VERSION)
        if item.extractor.startswith("canonical-publication-")
        else item
        for item in result.evidence
    )
    return replace(result, evidence=evidence)


def _title_local_byline_candidate(record, bundle: AcquisitionBundle) -> Evidence | None:
    body = bundle.body_markdown or bundle.body_text or ""
    title = record.title_hint or bundle.raw_title
    sample = _base._title_local_sample(body, title)

    for line in sample.splitlines():
        compact = normalize_space(line)
        if not compact or len(compact) > 520:
            continue
        if _SOURCE_MARKER_RE.search(compact) is None:
            continue
        if _READ_MARKER_RE.search(compact) is None:
            continue

        match = _ABSOLUTE_DATETIME_RE.search(compact)
        if match is None:
            continue

        prefix = compact[: match.start()]
        # Require a real byline/metadata cue before the date rather than merely
        # accepting any title-local sentence that happens to contain a date.
        if not any(marker in prefix for marker in ("·", "•", "](", "作者", "记者", "記者")):
            continue

        raw = normalize_space(match.group("value"))
        normalized = _base.normalize_publication_date(raw)
        if not normalized:
            continue

        return Evidence(
            evidence_id=f"{record.item_id}-pr733-title-local-byline-publication",
            evidence_type="legacy_publication_date_candidate",
            source_stage=StageName.CANONICAL,
            field="publication_date_candidate",
            value={
                "value": raw,
                "source": _SOURCE,
                "confidence": 0.97,
                "raw": raw,
                "role": "published",
                "priority": 113,
            },
            confidence=0.97,
            extractor=PUBLICATION_VERSION,
            excerpt=compact[:320],
        )

    return None


normalize_publication_date = _base.normalize_publication_date
normalize_publication_fact = _base.normalize_publication_fact

__all__ = [
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "normalize_publication_date",
    "normalize_publication_fact",
    "resolve_publication",
]
