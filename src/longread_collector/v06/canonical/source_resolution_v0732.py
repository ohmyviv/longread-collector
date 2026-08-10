"""PR-7.3.2 source relationship follow-up for Canonical Article (L4).

The first PR-7.3.1 natural zh_midday run exposed a narrow source-evidence gap:
several republished pages contained explicit original-source links, but the
PR-7.3 resolver only recognized a smaller ``来源/稿源/原载/转载自`` vocabulary.
This wrapper preserves all PR-7.3 wire/translation behavior and adds only two
high-precision body cues observed in the natural run:

* ``本文来自微信公众号：[publisher](url)``-style attribution; and
* a title-adjacent ``[查看原文](url)`` / ``[原文链接](url)`` link.

Ordinary external links are not treated as source evidence.
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
from . import source_resolution_v073 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.2"
SourceResolution = _base.SourceResolution

_WECHAT_ORIGINAL_RE = re.compile(
    r"(?:本文|文章|稿件|本稿)?\s*"
    r"(?:来自|來源於|来源于|转载自|轉載自)\s*"
    r"(?:微信公众(?:号|號)|微信公众号|微信公眾號)\s*[：:]?\s*"
    r"\[(?P<publisher>[^\]\n]{1,80})\]\((?P<url>https?://[^)\s]+)\)",
    re.I,
)
_TITLE_LOCAL_ORIGINAL_LINK_RE = re.compile(
    r"\[(?P<label>查看原文|原文链接|原文鏈接|原文)\]"
    r"\((?P<url>https?://[^)\s]+)\)",
    re.I,
)


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

    # Preserve stronger PR-7.3 semantics. Explicit translation and wire evidence
    # already encode a more specific relationship than a generic original link.
    if base.relationship in {
        SourceRelationship.TRANSLATED_REPUBLISH,
        SourceRelationship.WIRE_REPUBLISH,
    }:
        return replace(base, evidence=_retag_version(base.evidence))

    publisher, original_url, excerpt, cue_type = _explicit_original_source(
        record,
        bundle,
    )
    if not original_url:
        return replace(base, evidence=_retag_version(base.evidence))

    canonical_source = (
        publisher
        or _base._publisher_from_url(original_url)
        or base.canonical_source
    )
    original_publisher = canonical_source or base.original_publisher
    confidence = max(base.confidence, 0.98)

    evidence = [
        item
        for item in _retag_version(base.evidence)
        if item.evidence_type != "source_relationship"
    ]
    evidence.append(
        make_evidence(
            record.item_id,
            "explicit_original_source_link",
            "canonical_content_url",
            original_url,
            confidence=0.99,
            excerpt=(
                f"cue={cue_type}; publisher={publisher or canonical_source}; {excerpt}"
            )[:400],
            extractor=SOURCE_VERSION,
        )
    )
    evidence.append(
        make_evidence(
            record.item_id,
            "source_relationship",
            "source_relationship",
            SourceRelationship.SECONDARY_REPUBLISH.value,
            confidence=confidence,
            excerpt=(
                "reason=explicit_original_source_link; "
                f"hosting={base.hosting_source}; original={original_publisher}; "
                f"action={SourceAction.REPLACE_WITH_ORIGINAL.value}"
            ),
            extractor=SOURCE_VERSION,
        )
    )

    return replace(
        base,
        canonical_source=canonical_source,
        original_publisher=original_publisher,
        canonical_content_url=original_url,
        relationship=SourceRelationship.SECONDARY_REPUBLISH,
        action=SourceAction.REPLACE_WITH_ORIGINAL,
        evidence=tuple(evidence),
        confidence=confidence,
    )


def _explicit_original_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> tuple[str, str, str, str]:
    body = bundle.body_markdown or bundle.body_text or ""

    # A publisher-named WeChat attribution is strong even when the site's
    # "原文链接" is repeated near the footer, so scan only the early article
    # region for this literal cue rather than interpreting arbitrary links.
    early = body[:9000]
    match = _WECHAT_ORIGINAL_RE.search(early)
    if match is not None:
        url = normalize_space(match.group("url"))
        if _base._credible_external_url(record.url, url):
            publisher = normalize_space(match.group("publisher"))[:80]
            return publisher, url, _excerpt(early, match), "wechat_original_attribution"

    # Generic "查看原文" is accepted only immediately around the article title.
    # This covers aggregator headers such as ByDrug without turning reference
    # links later in a long article into source-relationship evidence.
    local = _title_local_sample(body, record.title_hint or bundle.raw_title)
    match = _TITLE_LOCAL_ORIGINAL_LINK_RE.search(local)
    if match is not None:
        url = normalize_space(match.group("url"))
        if _base._credible_external_url(record.url, url):
            return "", url, _excerpt(local, match), "title_local_original_link"

    return "", "", "", ""


def _title_local_sample(body: str, title: str) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        needles = [clean_title]
        for width in (64, 48, 36, 24, 16):
            if len(clean_title) > width:
                needles.append(clean_title[:width])
        for needle in needles:
            position = value.find(needle)
            if 0 <= position <= 12000:
                return value[position : position + 1800]
    return value[:1800]


def _excerpt(value: str, match: re.Match[str], limit: int = 260) -> str:
    start = max(0, match.start() - 80)
    end = min(len(value), match.end() + 100)
    return normalize_space(value[start:end])[:limit]


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
