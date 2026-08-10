"""PR-7.3.3 source relationship follow-up for Canonical Article (L4).

The first scheduled natural shadow after PR-7.3.2 exposed a narrow false
``secondary_republish`` class on publisher-hosted reporter pages. The acquired
Jiemian pages carried all of the following title-local evidence:

* an on-site author/byline link;
* an absolute publication datetime;
* ``浏览`` / ``阅读`` metadata;
* ``来源：<publisher>``; and
* a page-title suffix identifying the same publisher.

The older PR-2-compatible resolver can still treat a machine hosting label/domain
as different from the human publisher label and preserve ``secondary_republish``
with ``retain_current_display_url``. This wrapper does not add a site allow-list.
It recovers ``original`` only when the title-local self-source label agrees with
the page's own title brand and no stronger external-original, wire, translation,
or primary-document action has already been established.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    SourceAction,
    SourceRelationship,
)
from .evidence import make_evidence, normalize_space
from . import source_resolution_v0732 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.3"
SourceResolution = _base.SourceResolution

_SOURCE_LABEL_RE = re.compile(
    r"(?:来源|來源)\s*[：:]\s*(?P<publisher>[^|｜\n]{2,80})\s*$",
    re.I,
)
_DATE_RE = re.compile(
    r"(?:19|20)\d{2}(?:[-/.]\d{1,2}[-/.]\d{1,2}|年\d{1,2}月\d{1,2}(?:日)?)"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?",
    re.I,
)
_READ_MARKER_RE = re.compile(r"(?:浏览|瀏覽|阅读|閱讀)", re.I)


def resolve_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    resolved_title: str,
    primary_document_hint: bool,
    transcript_hint: bool,
) -> SourceResolution:
    base = _base.resolve_source(
        record,
        bundle,
        resolved_title=resolved_title,
        primary_document_hint=primary_document_hint,
        transcript_hint=transcript_hint,
    )

    # Do not override any stronger relationship/action established by PR-7.3 or
    # PR-7.3.2. In particular, explicit original links, wire evidence,
    # translations, and primary-document chase actions remain authoritative.
    if (
        base.relationship is not SourceRelationship.SECONDARY_REPUBLISH
        or base.action is not SourceAction.RETAIN_CURRENT_DISPLAY_URL
    ):
        return replace(base, evidence=_retag_version(base.evidence))

    publisher, excerpt = _title_local_self_source(record, bundle, resolved_title)
    if not publisher:
        return replace(base, evidence=_retag_version(base.evidence))

    confidence = max(base.confidence, 0.97)
    evidence = [
        item
        for item in _retag_version(base.evidence)
        if item.evidence_type != "source_relationship"
    ]
    evidence.append(
        make_evidence(
            record.item_id,
            "self_source_title_metadata",
            "canonical_source",
            publisher,
            confidence=0.98,
            excerpt=excerpt[:360],
            extractor=SOURCE_VERSION,
        )
    )
    evidence.append(
        make_evidence(
            record.item_id,
            "source_relationship",
            "source_relationship",
            SourceRelationship.ORIGINAL.value,
            confidence=confidence,
            excerpt=(
                "reason=title_local_self_source_matches_title_brand; "
                f"hosting={base.hosting_source}; publisher={publisher}; "
                f"action={SourceAction.NONE.value}"
            ),
            extractor=SOURCE_VERSION,
        )
    )

    return replace(
        base,
        canonical_source=publisher,
        original_publisher=publisher,
        canonical_content_url=record.url,
        relationship=SourceRelationship.ORIGINAL,
        action=SourceAction.NONE,
        evidence=tuple(evidence),
        confidence=confidence,
    )


def _title_local_self_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> tuple[str, str]:
    body = bundle.body_markdown or bundle.body_text or ""
    title = record.title_hint or bundle.raw_title or resolved_title
    sample = _base._title_local_sample(body, title)

    for line in sample.splitlines():
        compact = normalize_space(line)
        if not compact or len(compact) > 520:
            continue
        if _DATE_RE.search(compact) is None or _READ_MARKER_RE.search(compact) is None:
            continue
        match = _SOURCE_LABEL_RE.search(compact)
        if match is None:
            continue

        date_match = _DATE_RE.search(compact)
        prefix = compact[: date_match.start()] if date_match is not None else ""
        if not any(marker in prefix for marker in ("·", "•", "](", "作者", "记者", "記者")):
            continue

        publisher = normalize_space(match.group("publisher")).strip(" ：:|｜")[:80]
        if publisher and _publisher_matches_title_brand(title, publisher):
            return publisher, compact

    return "", ""


def _publisher_matches_title_brand(title: str, publisher: str) -> bool:
    title_value = normalize_space(title)
    publisher_value = normalize_space(publisher)
    if not title_value or not publisher_value:
        return False

    publisher_key = _publisher_key(publisher_value)
    if not publisher_key:
        return False

    # Prefer an explicit trailing brand segment such as ``|界面新闻``. The
    # fallback ``endswith`` covers titles whose site suffix is not separated by
    # a conventional pipe/dash after extraction normalization.
    segments = re.split(r"[|｜—–\-]+", title_value)
    for segment in segments[-3:]:
        if _publisher_key(segment) == publisher_key:
            return True
    return _publisher_key(title_value).endswith(publisher_key)


def _publisher_key(value: str) -> str:
    return re.sub(r"[\s·•（）()《》「」【】\[\]_:：]+", "", normalize_space(value)).lower()


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
