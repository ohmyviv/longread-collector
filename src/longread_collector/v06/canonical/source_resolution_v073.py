"""PR-7.3 source relationship resolution for Canonical Article (L4).

This wrapper preserves PR-2 source behavior unless stronger relationship evidence
is available from canonical links, explicit translation/original-source cues, or
wire-service signatures already present in the acquired evidence.
"""

from __future__ import annotations

from dataclasses import replace
import re
from urllib.parse import urlsplit

from ..contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    SourceAction,
    SourceRelationship,
)
from .evidence import external_link, host, make_evidence, normalize_space
from .source_resolution import SourceResolution, resolve_source as _resolve_source

SOURCE_VERSION = "canonical-source-v0.6-pr7.3"

_WIRE_DOMAINS = {
    "reuters.com": "Reuters",
    "apnews.com": "AP",
}
_KNOWN_PUBLISHERS = {
    "peopleapp.com": "人民日报",
    "paper.people.com.cn": "人民日报",
    "people.com.cn": "人民网",
    "news.cctv.com": "央视网",
    "cctv.com": "央视网",
    "pbc.gov.cn": "中国人民银行",
    "reuters.com": "Reuters",
    "apnews.com": "AP",
}

_REUTERS_AUTHOR_RE = re.compile(
    r"^(?:by\s+)?(?:reuters|reuters staff|reuters reporters?)$", re.I
)
_AP_AUTHOR_RE = re.compile(
    r"^(?:by\s+)?(?:the\s+)?associated press$|^(?:by\s+)?ap(?:\s+news)?$", re.I
)
_REUTERS_DATELINE_RE = re.compile(
    r"^[A-Z][A-Z .'-]{2,40},?\s+(?:[A-Z][a-z]+\s+\d{1,2},?\s+20\d{2}\s+)?"
    r"\(Reuters\)\s*[-–—]",
    re.M,
)
_AP_DATELINE_RE = re.compile(
    r"^[A-Z][A-Z .'-]{2,40}\s*\(AP\)\s*[-–—]",
    re.M,
)
_REUTERS_BYLINE_RE = re.compile(
    r"^(?:By\s+[^\n]{2,100}\n)?Reporting by\s+[^\n]{2,180}(?:;|\n|$)",
    re.I | re.M,
)
_AP_BYLINE_RE = re.compile(
    r"^(?:By\s+)?(?:The\s+)?Associated Press\s*$",
    re.I | re.M,
)
_REUTERS_COPYRIGHT_RE = re.compile(
    r"(?:©|copyright)\s*(?:20\d{2}\s*)?Reuters\b", re.I
)
_AP_COPYRIGHT_RE = re.compile(
    r"(?:©|copyright)\s*(?:20\d{2}\s*)?(?:The\s+)?Associated Press\b", re.I
)
_REUTERS_ORIGINAL_RE = re.compile(
    r"(?:originally|first)\s+(?:published|reported)\s+(?:by|in|on)\s+Reuters\b|"
    r"this\s+(?:article|story)\s+was\s+(?:originally\s+)?published\s+by\s+Reuters\b",
    re.I,
)
_AP_ORIGINAL_RE = re.compile(
    r"(?:originally|first)\s+(?:published|reported)\s+(?:by|in|on)\s+"
    r"(?:The\s+)?Associated Press\b|this\s+(?:article|story)\s+was\s+"
    r"(?:originally\s+)?published\s+by\s+(?:The\s+)?Associated Press\b",
    re.I,
)
_REUTERS_SOURCE_RE = re.compile(
    r"^(?:来源|來源|稿源|原载|原載|转载自|轉載自)\s*[：:]\s*Reuters\s*$",
    re.I | re.M,
)
_AP_SOURCE_RE = re.compile(
    r"^(?:来源|來源|稿源|原载|原載|转载自|轉載自)\s*[：:]\s*(?:The\s+)?Associated Press\s*$",
    re.I | re.M,
)
_NEGATIVE_WIRE_CONTEXT_RE = re.compile(
    r"(?:designed|design|funded|supported|commissioned|partnered|produced)\s+by\s+"
    r"(?:the\s+)?Thomson Reuters Foundation|"
    r"Thomson Reuters Foundation\s+(?:as|was|is|provided|supported|designed)|"
    r"(?:references?|bibliography|works cited).{0,300}\bReuters\b",
    re.I | re.S,
)

_TRANSLATION_PATTERNS = (
    re.compile(
        r"(?:编译自|編譯自|译自|譯自|翻译自|翻譯自)\s*[：:]?\s*"
        r"(?P<publisher>[^|\n，。；;]{2,80})",
        re.I,
    ),
    re.compile(
        r"(?:translated\s+from|translation\s+of)\s+(?P<publisher>[^|\n.;]{2,80})",
        re.I,
    ),
)


def resolve_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    resolved_title: str,
    primary_document_hint: bool,
    transcript_hint: bool,
) -> SourceResolution:
    base = _resolve_source(
        record,
        bundle,
        resolved_title=resolved_title,
        primary_document_hint=primary_document_hint,
        transcript_hint=transcript_hint,
    )
    body = bundle.body_markdown or bundle.body_text or ""
    author = normalize_space(bundle.raw_author)
    current_host = host(record.url)

    external_target, target_kind = _external_original_target(record, bundle)
    target_publisher = _publisher_from_url(external_target) if external_target else ""

    wire_service, wire_type, wire_excerpt, direct_wire = _wire_evidence(
        record.url,
        author=author,
        body=body,
    )
    translation_publisher, translation_excerpt = _translation_evidence(body)

    relationship = base.relationship
    action = base.action
    canonical_url = base.canonical_content_url
    canonical_source = base.canonical_source
    original_publisher = base.original_publisher
    confidence = base.confidence
    reason = "pr2_compatible_source_resolution"

    if direct_wire and wire_service:
        relationship = SourceRelationship.ORIGINAL
        action = SourceAction.NONE
        canonical_url = record.url
        canonical_source = wire_service
        original_publisher = wire_service
        confidence = max(confidence, 0.98)
        reason = f"direct_wire_publisher:{wire_service}"
    elif translation_publisher:
        relationship = SourceRelationship.TRANSLATED_REPUBLISH
        original_publisher = translation_publisher
        canonical_source = translation_publisher
        confidence = max(confidence, 0.94)
        reason = "explicit_translation_source"
        if external_target:
            canonical_url = external_target
            action = SourceAction.REPLACE_WITH_ORIGINAL
        else:
            canonical_url = record.url
            action = SourceAction.FIND_ORIGINAL_ARTICLE
    elif wire_service:
        relationship = SourceRelationship.WIRE_REPUBLISH
        original_publisher = wire_service
        canonical_source = wire_service
        confidence = max(confidence, 0.96)
        reason = f"strong_wire_evidence:{wire_type}"
        if external_target and _wire_domain(host(external_target)) == wire_service:
            canonical_url = external_target
            action = SourceAction.REPLACE_WITH_ORIGINAL
        else:
            canonical_url = record.url
            action = SourceAction.FIND_ORIGINAL_ARTICLE
    elif external_target:
        relationship = SourceRelationship.SECONDARY_REPUBLISH
        action = SourceAction.REPLACE_WITH_ORIGINAL
        canonical_url = external_target
        canonical_source = target_publisher or base.canonical_source
        original_publisher = target_publisher or base.original_publisher or canonical_source
        confidence = max(
            confidence,
            0.96 if target_kind == "metadata_external_target" else 0.93,
        )
        reason = f"external_{target_kind}"
    elif base.relationship is SourceRelationship.SECONDARY_REPUBLISH:
        # PR-2 already has explicit source-label evidence. Preserve its primary
        # document action and display-URL semantics.
        reason = "pr2_explicit_source_differs_from_host"
        confidence = max(confidence, 0.90)

    evidence = [
        item
        for item in base.evidence
        if item.evidence_type != "source_relationship"
    ]

    if external_target and target_kind == "canonical_link":
        evidence.append(
            make_evidence(
                record.item_id,
                "canonical_link_relation",
                "canonical_content_url",
                external_target,
                confidence=0.95,
                excerpt=(
                    f"external rel=canonical target; current_host={current_host}; "
                    f"target_host={host(external_target)}"
                ),
                extractor=SOURCE_VERSION,
            )
        )

    if wire_service:
        evidence.append(
            make_evidence(
                record.item_id,
                "wire_service_evidence",
                "original_publisher",
                wire_service,
                confidence=0.99 if direct_wire else 0.96,
                excerpt=f"type={wire_type}; {wire_excerpt}",
                extractor=SOURCE_VERSION,
            )
        )

    if translation_publisher:
        evidence.append(
            make_evidence(
                record.item_id,
                "translation_source_evidence",
                "original_publisher",
                translation_publisher,
                confidence=0.95,
                excerpt=translation_excerpt,
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
                f"reason={reason}; hosting={base.hosting_source}; "
                f"original={original_publisher}; action={action.value}"
            ),
            extractor=SOURCE_VERSION,
        )
    )

    return replace(
        base,
        canonical_source=canonical_source,
        original_publisher=original_publisher,
        canonical_content_url=canonical_url,
        relationship=relationship,
        action=action,
        evidence=tuple(evidence),
        confidence=confidence,
    )


def _external_original_target(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> tuple[str, str]:
    metadata_target = external_link(record.raw_metadata)
    if _credible_external_url(record.url, metadata_target):
        return metadata_target, "metadata_external_target"

    for raw in bundle.raw_canonical_links:
        candidate = normalize_space(raw)
        if _credible_external_url(record.url, candidate):
            return candidate, "canonical_link"
    return "", ""


def _credible_external_url(current_url: str, candidate: str) -> bool:
    if not candidate.startswith(("http://", "https://")):
        return False
    current = host(current_url)
    target = host(candidate)
    if not current or not target or _same_site(current, target):
        return False
    if re.search(r"(?:^|\.)(?:cdn|static|assets?|images?|img)\.", target):
        return False
    path = urlsplit(candidate).path
    return bool(path and path != "/")


def _same_site(left: str, right: str) -> bool:
    """Treat direct parent/subdomain canonicalization as one hosting site."""
    return bool(
        left
        and right
        and (
            left == right
            or left.endswith("." + right)
            or right.endswith("." + left)
        )
    )


def _publisher_from_url(url: str) -> str:
    domain = host(url)
    if not domain:
        return ""
    for suffix, publisher in _KNOWN_PUBLISHERS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return publisher
    return domain


def _wire_domain(domain: str) -> str:
    for suffix, service in _WIRE_DOMAINS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return service
    return ""


def _wire_evidence(
    url: str,
    *,
    author: str,
    body: str,
) -> tuple[str, str, str, bool]:
    direct = _wire_domain(host(url))
    if direct:
        return direct, "direct_publisher_domain", host(url), True

    lead = body[:4000]
    author_clean = normalize_space(author)
    negative = bool(_NEGATIVE_WIRE_CONTEXT_RE.search("\n".join((author_clean, lead))))
    checks = (
        ("Reuters", "structured_author", _REUTERS_AUTHOR_RE, author_clean),
        ("AP", "structured_author", _AP_AUTHOR_RE, author_clean),
        ("Reuters", "wire_dateline", _REUTERS_DATELINE_RE, lead),
        ("AP", "wire_dateline", _AP_DATELINE_RE, lead),
        ("Reuters", "wire_byline", _REUTERS_BYLINE_RE, lead),
        ("AP", "wire_byline", _AP_BYLINE_RE, lead),
        ("Reuters", "source_label", _REUTERS_SOURCE_RE, lead),
        ("AP", "source_label", _AP_SOURCE_RE, lead),
        ("Reuters", "copyright_notice", _REUTERS_COPYRIGHT_RE, lead),
        ("AP", "copyright_notice", _AP_COPYRIGHT_RE, lead),
        ("Reuters", "explicit_original_statement", _REUTERS_ORIGINAL_RE, lead),
        ("AP", "explicit_original_statement", _AP_ORIGINAL_RE, lead),
    )
    for service, evidence_type, pattern, value in checks:
        match = pattern.search(value)
        if match is None:
            continue
        # Structured attribution is direct evidence. Negative context only
        # blocks free-text original-source wording that may occur in references.
        if negative and evidence_type == "explicit_original_statement":
            continue
        return service, evidence_type, _excerpt(value, match), False
    return "", "negative_context_only" if negative else "no_strong_wire_evidence", "", False


def _translation_evidence(body: str) -> tuple[str, str]:
    sample = body[:5000]
    for pattern in _TRANSLATION_PATTERNS:
        match = pattern.search(sample)
        if match is None:
            continue
        publisher = _clean_publisher(match.group("publisher"))
        if publisher:
            return publisher, _excerpt(sample, match)
    return "", ""


def _clean_publisher(value: str) -> str:
    candidate = normalize_space(value)
    candidate = re.sub(
        r"\s+(?:article|story|report|报道|報道|文章).*$",
        "",
        candidate,
        flags=re.I,
    )
    candidate = candidate.strip(" ：:|｜,，.;；。")
    return candidate[:80]


def _excerpt(value: str, match: re.Match[str], limit: int = 220) -> str:
    start = max(0, match.start() - 40)
    end = min(len(value), match.end() + 80)
    return normalize_space(value[start:end])[:limit]


__all__ = [
    "SOURCE_VERSION",
    "SourceResolution",
    "resolve_source",
]
