"""PR-7.3.7 explicit publisher identity normalization (L4).

The 2026-08-11 scheduled ``zh_evening`` Natural Shadow exposed two cases where
an otherwise-correct explicit source relationship retained presentation syntax
inside ``canonical_source``:

* ``来源：[实况网](http://www.cqtimes.cn/)`` kept the Markdown link verbatim;
* ``来源：《光明日报》（2026年08月10日 13版）`` kept newspaper issue metadata.

This wrapper changes identity only when a prior explicit-source observation is
present and the entire canonical publisher matches one of those narrow shapes.
Relationship/action/URL semantics from PR-7.3.6 remain unchanged. No site
allow-list or network I/O is introduced.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import AcquisitionBundle, DiscoveryRecord
from .evidence import make_evidence, normalize_space
from . import source_resolution_v0736 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.7"
SourceResolution = _base.SourceResolution

_MARKDOWN_PUBLISHER_RE = re.compile(
    r"^\[(?P<label>[^\]\n]{1,80})\]\((?P<url>https?://[^)\n]+)\)$",
    re.I,
)
_NEWSPAPER_ISSUE_RE = re.compile(
    r"^《(?P<label>[^》\n]{1,80})》\s*[（(]\s*"
    r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日\s+\d{1,3}版\s*[）)]$"
)
_EXPLICIT_SOURCE_EVIDENCE = frozenset(
    {"explicit_source_label", "explicit_source_label_boundary"}
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
    evidence = _retag_version(base.evidence)

    raw_identity = normalize_space(base.canonical_source)
    normalized, rule = _normalize_explicit_publisher_identity(raw_identity)
    if (
        not normalized
        or normalized == raw_identity
        or not _has_explicit_source_observation(base, raw_identity)
    ):
        return replace(base, evidence=evidence)

    original = base.original_publisher
    if normalize_space(original) == raw_identity:
        original = normalized

    evidence = (*evidence, make_evidence(
        record.item_id,
        "explicit_source_identity_normalized",
        "canonical_source",
        normalized,
        confidence=0.99,
        excerpt=f"rule={rule}; raw={raw_identity}",
        extractor=SOURCE_VERSION,
    ))
    return replace(
        base,
        canonical_source=normalized,
        original_publisher=original,
        evidence=evidence,
        confidence=max(base.confidence, 0.98),
    )


def _has_explicit_source_observation(base: SourceResolution, raw_identity: str) -> bool:
    raw_key = _publisher_key(raw_identity)
    if not raw_key:
        return False
    for item in base.evidence:
        if item.evidence_type not in _EXPLICIT_SOURCE_EVIDENCE:
            continue
        value = normalize_space(str(item.value or ""))
        if value and _publisher_key(value) == raw_key:
            return True
    return False


def _normalize_explicit_publisher_identity(value: str) -> tuple[str, str]:
    raw = normalize_space(value).strip(" ：:|｜")
    markdown = _MARKDOWN_PUBLISHER_RE.fullmatch(raw)
    if markdown is not None:
        label = normalize_space(markdown.group("label")).strip(" ：:|｜")
        if label:
            return label, "markdown_link_label"

    newspaper = _NEWSPAPER_ISSUE_RE.fullmatch(raw)
    if newspaper is not None:
        label = normalize_space(newspaper.group("label")).strip(" ：:|｜")
        if label:
            return label, "newspaper_issue_citation"

    return raw, "none"


def _publisher_key(value: str) -> str:
    return re.sub(
        r"[\s·•（）()《》「」【】\[\]_:：|｜—–\-]+",
        "",
        normalize_space(value),
    ).lower()


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
