"""PR-7.3.8 L4 primary-document issuer recovery from explicit page metadata.

The 2026-08-12 scheduled ``pre_report`` Natural Shadow exposed a government
primary-document page whose acquired body contained the explicit header
``发文机构：武汉市人民政府`` while the source resolver fell back to the whole page
``<title>`` as hosting/canonical source. This wrapper only repairs that narrow
fallback on direct ``.gov.cn`` primary-document pages using already-acquired,
bounded header evidence. Stronger republish/original-link/translation/wire
semantics remain untouched and no network I/O is introduced.
"""

from __future__ import annotations

from dataclasses import replace
import re

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    DiscoveryRecord,
    SourceAction,
    SourceRelationship,
)
from .evidence import host, make_evidence, normalize_space
from . import source_resolution_v0737 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.8"
SourceResolution = _base.SourceResolution

_DOCUMENT_ISSUER_RE = re.compile(
    r"(?:^|\n)\s*(?:[*+-]\s*)?"
    r"(?:发文机构|发文机关|发布机构|发布单位)\s*[：:]\s*"
    r"(?P<issuer>[^|｜\n\r]{2,80}?)"
    r"(?=(?:\s+(?:发文字号|成文日期|发布日期|索引号|主题分类|有效性|公开方式)\s*[：:])"
    r"|[|｜\n\r]|$)",
    re.M,
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

    issuer, excerpt = _bounded_document_issuer(
        record,
        bundle,
        resolved_title,
    )
    if not issuer:
        return replace(base, evidence=evidence)

    is_primary = primary_document_hint or base.asset_class is AssetClass.PRIMARY_DOCUMENT
    if not is_primary or not _direct_government_host(record.url):
        return replace(base, evidence=evidence)

    # Do not let issuer metadata erase already-stronger source semantics. A
    # third-party republication can carry the original document header verbatim;
    # this PR intentionally repairs only an ORIGINAL/NONE direct government page.
    if (
        base.relationship is not SourceRelationship.ORIGINAL
        or base.action is not SourceAction.NONE
    ):
        return replace(base, evidence=evidence)

    if not _identity_is_fallback(base, record, bundle, resolved_title):
        return replace(base, evidence=evidence)

    if _same_publisher(base.canonical_source, issuer) and _same_publisher(
        base.hosting_source, issuer
    ):
        return replace(base, evidence=evidence)

    confidence = max(base.confidence, 0.99)
    evidence = [
        item
        for item in evidence
        if item.evidence_type not in {"hosting_source", "source_relationship"}
    ]
    evidence.append(
        make_evidence(
            record.item_id,
            "document_issuer_evidence",
            "canonical_source",
            issuer,
            confidence=0.99,
            excerpt=excerpt[:360],
            extractor=SOURCE_VERSION,
        )
    )
    evidence.append(
        make_evidence(
            record.item_id,
            "document_issuer_hosting_source",
            "hosting_source",
            issuer,
            confidence=0.99,
            excerpt=f"direct_government_host={host(record.url)}; {excerpt[:260]}",
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
                "reason=explicit_primary_document_issuer_replaces_fallback; "
                f"hosting={issuer}; original={issuer}; action={SourceAction.NONE.value}"
            ),
            extractor=SOURCE_VERSION,
        )
    )
    return replace(
        base,
        hosting_source=issuer,
        canonical_source=issuer,
        original_publisher=issuer,
        canonical_content_url=record.url,
        relationship=SourceRelationship.ORIGINAL,
        action=SourceAction.NONE,
        evidence=tuple(evidence),
        confidence=confidence,
    )


def _bounded_document_issuer(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> tuple[str, str]:
    body = bundle.body_markdown or bundle.body_text or ""
    sample = _title_local_sample(
        body,
        record.title_hint or bundle.raw_title or resolved_title,
        limit=3600,
    )
    match = _DOCUMENT_ISSUER_RE.search(sample)
    if match is None:
        return "", ""
    issuer = normalize_space(match.group("issuer")).strip(" ：:|｜*-+")[:80]
    if not issuer or issuer.startswith(("http://", "https://")):
        return "", ""
    return issuer, _excerpt(sample, match)


def _identity_is_fallback(
    base: SourceResolution,
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> bool:
    fallback_keys = {
        _publisher_key(value)
        for value in (
            record.title_hint,
            bundle.raw_title,
            resolved_title,
            host(record.url),
        )
        if normalize_space(value)
    }
    canonical_key = _publisher_key(base.canonical_source)
    hosting_key = _publisher_key(base.hosting_source)
    return bool(
        canonical_key
        and hosting_key
        and canonical_key in fallback_keys
        and hosting_key in fallback_keys
    )


def _direct_government_host(url: str) -> bool:
    page_host = host(url)
    return bool(page_host == "gov.cn" or page_host.endswith(".gov.cn"))


def _title_local_sample(body: str, title: str, *, limit: int) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        needles = [clean_title]
        for width in (72, 56, 40, 28, 18):
            if len(clean_title) > width:
                needles.append(clean_title[:width])
        for needle in needles:
            position = value.find(needle)
            if 0 <= position <= 12000:
                return value[position : position + limit]
    return value[:limit]


def _same_publisher(left: str, right: str) -> bool:
    a = _publisher_key(left)
    b = _publisher_key(right)
    return bool(a and b and (a == b or a in b or b in a))


def _publisher_key(value: str) -> str:
    return re.sub(
        r"[\s·•（）()《》「」【】\[\]_:：|｜—–\-]+",
        "",
        normalize_space(value),
    ).lower()


def _excerpt(value: str, match: re.Match[str], limit: int = 320) -> str:
    start = max(0, match.start() - 100)
    end = min(len(value), match.end() + 140)
    return normalize_space(value[start:end])[:limit]


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
