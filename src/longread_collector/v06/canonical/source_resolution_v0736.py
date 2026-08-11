"""PR-7.3.6 L4 source-identity follow-up from natural zh_midday evidence.

The 2026-08-11 scheduled natural shadow exposed three narrow source facts that
remain recoverable from already-acquired evidence:

* registered ``source_name`` metadata can sit at the top level of the discovery
  record while the PR-2 hosting resolver only checks nested legacy shapes;
* compact Chinese article headers can place ``作者/编辑`` metadata on the same
  line as ``来源：publisher``, contaminating the explicit publisher capture; and
* a strict lead ``新华社...日电`` dateline is strong agency-republication evidence
  even when the hosting page itself is a registered publisher page.

This wrapper stays L4-only and performs no network I/O. It preserves stronger
PR-7.3.2/7.3.3 original-link, translation, Reuters/AP wire, and self-source
semantics unless one of the narrowly defined corrections below applies.
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
from . import source_resolution_v0733 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.6"
SourceResolution = _base.SourceResolution

_XINHUA_DIRECT_DOMAINS = ("news.cn", "xinhuanet.com")
_SOURCE_LABEL_RE = re.compile(
    r"(?:来源|來源|稿源|原载|原載|转载自|轉載自)\s*[：:]\s*"
    r"(?P<publisher>[^|｜\n\r]{2,80}?)"
    r"(?=(?:\s*(?:作者|编辑|編輯|责编|責編|记者|記者|校对|校對|审核|審核)\s*[：:])"
    r"|[|｜\n\r]|$)",
    re.I,
)
_SOURCE_METADATA_RE = re.compile(
    r"(?:作者|编辑|編輯|责编|責編|记者|記者|校对|校對|审核|審核)\s*[：:]",
    re.I,
)
_XINHUA_DATELINE_RE = re.compile(
    r"(?:^|\n)\s*(?:据\s*)?新华社"
    r"(?P<dateline>[\u4e00-\u9fff]{1,12}\d{1,2}月\d{1,2}日)"
    r"电(?:[\s，,。（(]|$)",
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

    registered = _registered_hosting_source(record)
    hosting_recovered = bool(
        registered
        and _hosting_is_title_fallback(
            base.hosting_source,
            record,
            bundle,
            resolved_title,
        )
    )
    hosting = registered if hosting_recovered else base.hosting_source

    # Preserve already stronger relationship semantics. A registered hosting
    # label may still repair the hosting field, but it must not erase an
    # explicit original URL, translation, or Reuters/AP wire classification.
    stronger_relationship = base.relationship in {
        SourceRelationship.TRANSLATED_REPUBLISH,
        SourceRelationship.WIRE_REPUBLISH,
    }
    stronger_original_url = base.action is SourceAction.REPLACE_WITH_ORIGINAL

    xinhua_excerpt = _xinhua_lead_dateline(record, bundle, resolved_title)
    if (
        xinhua_excerpt
        and not _direct_xinhua_publisher(record, base, hosting, registered)
        and not stronger_relationship
        and not stronger_original_url
    ):
        confidence = max(base.confidence, 0.99)
        evidence = _base_evidence(
            base,
            drop_relationship=True,
            drop_hosting=hosting_recovered,
        )
        if hosting_recovered:
            evidence.append(_registered_hosting_evidence(record, registered))
        evidence.append(
            make_evidence(
                record.item_id,
                "agency_dateline_evidence",
                "original_publisher",
                "新华社",
                confidence=0.99,
                excerpt=xinhua_excerpt[:360],
                extractor=SOURCE_VERSION,
            )
        )
        evidence.append(
            make_evidence(
                record.item_id,
                "source_relationship",
                "source_relationship",
                SourceRelationship.WIRE_REPUBLISH.value,
                confidence=confidence,
                excerpt=(
                    "reason=strict_xinhua_lead_dateline; "
                    f"hosting={hosting}; original=新华社; "
                    f"action={SourceAction.FIND_ORIGINAL_ARTICLE.value}"
                ),
                extractor=SOURCE_VERSION,
            )
        )
        return replace(
            base,
            hosting_source=hosting,
            canonical_source="新华社",
            original_publisher="新华社",
            canonical_content_url=record.url,
            relationship=SourceRelationship.WIRE_REPUBLISH,
            action=SourceAction.FIND_ORIGINAL_ARTICLE,
            evidence=tuple(evidence),
            confidence=confidence,
        )

    clean_source, source_excerpt = _bounded_explicit_source(
        record,
        bundle,
        resolved_title,
    )
    if (
        clean_source
        and not stronger_relationship
        and not stronger_original_url
        and _explicit_source_is_metadata_contaminated(base, clean_source)
    ):
        same_host = _same_publisher(clean_source, hosting)
        relationship = (
            SourceRelationship.ORIGINAL
            if same_host
            else SourceRelationship.SECONDARY_REPUBLISH
        )
        if relationship is SourceRelationship.ORIGINAL:
            action = SourceAction.NONE
        elif base.asset_class is AssetClass.PRIMARY_DOCUMENT:
            action = SourceAction.FIND_PRIMARY_DOCUMENT
        else:
            action = SourceAction.RETAIN_CURRENT_DISPLAY_URL
        confidence = max(base.confidence, 0.98)
        evidence = _base_evidence(
            base,
            drop_relationship=True,
            drop_hosting=hosting_recovered,
            drop_explicit_source=True,
        )
        if hosting_recovered:
            evidence.append(_registered_hosting_evidence(record, registered))
        evidence.append(
            make_evidence(
                record.item_id,
                "explicit_source_label_boundary",
                "canonical_source",
                clean_source,
                confidence=0.99,
                excerpt=source_excerpt[:360],
                extractor=SOURCE_VERSION,
            )
        )
        evidence.append(
            make_evidence(
                record.item_id,
                "source_relationship",
                "source_relationship",
                relationship.value,
                confidence=confidence,
                excerpt=(
                    "reason=source_label_stopped_before_editorial_metadata; "
                    f"hosting={hosting}; original={clean_source}; action={action.value}"
                ),
                extractor=SOURCE_VERSION,
            )
        )
        return replace(
            base,
            hosting_source=hosting,
            canonical_source=clean_source,
            original_publisher=clean_source,
            canonical_content_url=record.url,
            relationship=relationship,
            action=action,
            evidence=tuple(evidence),
            confidence=confidence,
        )

    if hosting_recovered:
        evidence = _base_evidence(base, drop_hosting=True)
        evidence.append(_registered_hosting_evidence(record, registered))

        # Only replace canonical/original identity when the old canonical source
        # was itself the same title-derived hosting fallback. If a separate
        # explicit publisher relationship already exists, preserve it and repair
        # hosting_source only.
        if (
            base.relationship is SourceRelationship.ORIGINAL
            and base.action is SourceAction.NONE
            and _same_publisher(base.canonical_source, base.hosting_source)
        ):
            confidence = max(base.confidence, 0.97)
            evidence = [
                item for item in evidence if item.evidence_type != "source_relationship"
            ]
            evidence.append(
                make_evidence(
                    record.item_id,
                    "source_relationship",
                    "source_relationship",
                    SourceRelationship.ORIGINAL.value,
                    confidence=confidence,
                    excerpt=(
                        "reason=registered_hosting_replaces_title_fallback; "
                        f"hosting={registered}; original={registered}; "
                        f"action={SourceAction.NONE.value}"
                    ),
                    extractor=SOURCE_VERSION,
                )
            )
            return replace(
                base,
                hosting_source=registered,
                canonical_source=registered,
                original_publisher=registered,
                canonical_content_url=record.url,
                relationship=SourceRelationship.ORIGINAL,
                action=SourceAction.NONE,
                evidence=tuple(evidence),
                confidence=confidence,
            )

        return replace(
            base,
            hosting_source=registered,
            evidence=tuple(evidence),
        )

    return replace(base, evidence=tuple(_base_evidence(base)))


def _registered_hosting_source(record: DiscoveryRecord) -> str:
    metadata = record.raw_metadata
    candidate = normalize_space(metadata.get("source_name", ""))
    source_id = normalize_space(metadata.get("source_id", "")) or normalize_space(
        record.source_id
    )
    if not candidate or not source_id or len(candidate) > 80:
        return ""
    if candidate.startswith(("http://", "https://")):
        return ""
    return candidate


def _hosting_is_title_fallback(
    hosting_source: str,
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> bool:
    hosting_key = _publisher_key(hosting_source)
    if not hosting_key:
        return False
    for title in (record.title_hint, bundle.raw_title, resolved_title):
        if hosting_key == _publisher_key(title):
            return True
    return False


def _bounded_explicit_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> tuple[str, str]:
    body = bundle.body_markdown or bundle.body_text or ""
    sample = _title_local_sample(
        body,
        record.title_hint or bundle.raw_title or resolved_title,
        limit=2600,
    )
    match = _SOURCE_LABEL_RE.search(sample)
    if match is None:
        return "", ""
    publisher = normalize_space(match.group("publisher")).strip(" ：:|｜")[:80]
    if not publisher:
        return "", ""
    return publisher, _excerpt(sample, match)


def _explicit_source_is_metadata_contaminated(
    base: SourceResolution,
    clean_source: str,
) -> bool:
    clean_key = _publisher_key(clean_source)
    if not clean_key:
        return False
    for item in base.evidence:
        if item.evidence_type != "explicit_source_label":
            continue
        value = normalize_space(str(item.value or ""))
        if (
            value
            and _publisher_key(value).startswith(clean_key)
            and _SOURCE_METADATA_RE.search(value) is not None
        ):
            return True
    return False


def _xinhua_lead_dateline(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> str:
    body = bundle.body_markdown or bundle.body_text or ""
    sample = _title_local_sample(
        body,
        record.title_hint or bundle.raw_title or resolved_title,
        limit=1400,
    )
    match = _XINHUA_DATELINE_RE.search(sample)
    if match is None:
        return ""
    return _excerpt(sample, match)


def _direct_xinhua_publisher(
    record: DiscoveryRecord,
    base: SourceResolution,
    hosting: str,
    registered: str,
) -> bool:
    for publisher in (
        registered,
        hosting,
        base.canonical_source,
        base.original_publisher,
    ):
        if _publisher_key(publisher) in {"新华社", "新华网"}:
            return True

    page_host = host(record.url)
    return any(
        page_host == domain or page_host.endswith("." + domain)
        for domain in _XINHUA_DIRECT_DOMAINS
    )


def _title_local_sample(body: str, title: str, *, limit: int) -> str:
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
                return value[position : position + limit]
    return value[:limit]


def _registered_hosting_evidence(record: DiscoveryRecord, publisher: str):
    source_id = normalize_space(record.raw_metadata.get("source_id", "")) or normalize_space(
        record.source_id
    )
    return make_evidence(
        record.item_id,
        "registered_hosting_source",
        "hosting_source",
        publisher,
        confidence=0.98,
        excerpt=f"source_id={source_id}; raw_metadata.source_name={publisher}",
        extractor=SOURCE_VERSION,
    )


def _base_evidence(
    base: SourceResolution,
    *,
    drop_relationship: bool = False,
    drop_hosting: bool = False,
    drop_explicit_source: bool = False,
) -> list:
    output = []
    for item in _retag_version(base.evidence):
        if drop_relationship and item.evidence_type == "source_relationship":
            continue
        if drop_hosting and item.evidence_type == "hosting_source":
            continue
        if drop_explicit_source and item.evidence_type == "explicit_source_label":
            continue
        output.append(item)
    return output


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


def _excerpt(value: str, match: re.Match[str], limit: int = 300) -> str:
    start = max(0, match.start() - 100)
    end = min(len(value), match.end() + 120)
    return normalize_space(value[start:end])[:limit]


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
