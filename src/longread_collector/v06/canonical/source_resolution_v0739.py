"""PR-7.3.9 L4 source-evidence follow-up from post-PR-7.3.8 Natural Shadow.

Two scheduled 2026-08-12 Natural Shadow runs exposed three source facts that
remain recoverable from already-acquired title-local evidence:

* publisher-hosted reporter pages can carry the PR-7.3.3 self-source evidence
  on a long rendered line where ``来源：publisher`` is followed by image/template
  metadata rather than a newline;
* a strict Xinhua lead dateline can share its rendered line with publication
  metadata, while a Markdown-emphasized ``_来源：新华社_`` footer can otherwise
  leak presentation syntax into publisher identity; and
* a syndicated page can expose an external article link together with a same-
  named ``官方账号`` provenance cue even when no external URL was promoted into
  Discovery metadata.

This wrapper is deliberately L4-only. It performs no network I/O and does not
change publication, PageSurface, Discovery, Acquisition, L5, or L6 semantics.
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
from .evidence import different_host, host, make_evidence, normalize_space
from . import source_resolution_v0738 as _base

SOURCE_VERSION = "canonical-source-v0.6-pr7.3.9"
SourceResolution = _base.SourceResolution

_XINHUA_DIRECT_DOMAINS = ("news.cn", "xinhuanet.com")
_XINHUA_HEADER_DATELINE_RE = re.compile(
    r"(?:据\s*)?新华社"
    r"(?P<dateline>[\u4e00-\u9fff]{1,12}\d{1,2}月\d{1,2}日)"
    r"电(?:[\s，,。（(]|$)",
    re.M,
)
_SELF_SOURCE_RE = re.compile(
    r"(?:来源|來源)\s*[：:]\s*"
    r"(?P<publisher>[^|｜\n\r!]{2,80}?)"
    r"(?=\s*(?:!\[|图片来源|圖片來源|图源|圖源|[|｜\n\r]|$))",
    re.I,
)
_DATE_RE = re.compile(
    r"(?:19|20)\d{2}(?:[-/.]\d{1,2}[-/.]\d{1,2}|年\d{1,2}月\d{1,2}(?:日)?)"
    r"(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?",
    re.I,
)
_READ_MARKER_RE = re.compile(r"(?:浏览|瀏覽|阅读|閱讀)", re.I)
_BYLINE_LINK_RE = re.compile(
    r"\[[^\]\n]{1,120}\]\((?P<url>https?://[^)\s]+)\)",
    re.I,
)
_EXTERNAL_OFFICIAL_ACCOUNT_RE = re.compile(
    r"\[(?P<label>[^\]\n]{2,80})\]"
    r"\((?P<url>https?://[^)\s]+)\)"
    r"\s*(?P=label)\s*(?:官方账号|官方帐号|官方帳號)",
    re.I,
)
_MARKDOWN_SOURCE_RE = re.compile(
    r"(?:^|\s)(?:[_*]{1,2})?"
    r"(?:来源|來源|稿源|原载|原載|转载自|轉載自)\s*[：:]\s*"
    r"(?P<label>[^|｜\n\r_*]{2,80}?)"
    r"(?P<close>[_*]{1,2})(?=\s|$|[|｜])",
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
    evidence = list(_retag_version(base.evidence))

    # Strong agency evidence wins before generic explicit-source normalization.
    xinhua_excerpt = _bounded_xinhua_header_dateline(
        record, bundle, resolved_title
    )
    if (
        xinhua_excerpt
        and not _direct_xinhua_publisher(record, base)
        and base.relationship is not SourceRelationship.TRANSLATED_REPUBLISH
        and base.action is not SourceAction.REPLACE_WITH_ORIGINAL
    ):
        hosting = _recovered_hosting_identity(base, record, bundle, resolved_title)
        confidence = max(base.confidence, 0.99)
        evidence = [
            item
            for item in evidence
            if item.evidence_type not in {"source_relationship", "explicit_source_label"}
        ]
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
                    "reason=title_local_xinhua_header_dateline; "
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

    # Re-apply the PR-7.3.3 self-source contract without depending on rendered
    # line length or the source label being the final token on that line.
    if (
        base.relationship is SourceRelationship.SECONDARY_REPUBLISH
        and base.action is SourceAction.RETAIN_CURRENT_DISPLAY_URL
    ):
        publisher, excerpt = _title_local_self_source(
            record, bundle, resolved_title
        )
        if publisher:
            confidence = max(base.confidence, 0.98)
            evidence = [
                item
                for item in evidence
                if item.evidence_type != "source_relationship"
            ]
            evidence.append(
                make_evidence(
                    record.item_id,
                    "self_source_title_metadata",
                    "canonical_source",
                    publisher,
                    confidence=0.99,
                    excerpt=excerpt[:400],
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
                        "reason=title_local_self_source_with_same_site_byline_profile; "
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

    # A title-local external article link accompanied by a same-named official
    # account cue is direct provenance, not an arbitrary reference link. Apply
    # only when the previous result is the weakest ORIGINAL/NONE fallback.
    if (
        base.relationship is SourceRelationship.ORIGINAL
        and base.action is SourceAction.NONE
        and _identity_is_fallback(base, record, bundle, resolved_title)
    ):
        publisher, original_url, excerpt = _title_local_external_official_account(
            record, bundle, resolved_title
        )
        if publisher and original_url:
            hosting = _recovered_hosting_identity(base, record, bundle, resolved_title)
            confidence = max(base.confidence, 0.99)
            evidence = [
                item
                for item in evidence
                if item.evidence_type not in {"source_relationship", "hosting_source"}
            ]
            evidence.append(
                make_evidence(
                    record.item_id,
                    "external_official_account_source",
                    "canonical_source",
                    publisher,
                    confidence=0.99,
                    excerpt=excerpt[:420],
                    extractor=SOURCE_VERSION,
                )
            )
            evidence.append(
                make_evidence(
                    record.item_id,
                    "external_original_target",
                    "canonical_content_url",
                    original_url,
                    confidence=0.99,
                    excerpt=f"publisher={publisher}; {excerpt[:330]}",
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
                        "reason=title_local_external_official_account_article; "
                        f"hosting={hosting}; original={publisher}; "
                        f"action={SourceAction.REPLACE_WITH_ORIGINAL.value}"
                    ),
                    extractor=SOURCE_VERSION,
                )
            )
            return replace(
                base,
                hosting_source=hosting,
                canonical_source=publisher,
                original_publisher=publisher,
                canonical_content_url=original_url,
                relationship=SourceRelationship.SECONDARY_REPUBLISH,
                action=SourceAction.REPLACE_WITH_ORIGINAL,
                evidence=tuple(evidence),
                confidence=confidence,
            )

    # Finally remove Markdown emphasis leaked into a proven explicit publisher
    # label without changing its already-established relationship/action.
    cleaned = _bounded_markdown_source_identity(record, bundle, resolved_title)
    if cleaned and _matches_explicit_source_evidence(base, cleaned):
        raw = normalize_space(base.canonical_source)
        if _publisher_key(raw) != _publisher_key(cleaned) or raw != cleaned:
            original = base.original_publisher
            if _publisher_key(original) == _publisher_key(raw):
                original = cleaned
            evidence.append(
                make_evidence(
                    record.item_id,
                    "explicit_source_markdown_normalized",
                    "canonical_source",
                    cleaned,
                    confidence=0.99,
                    excerpt=f"raw={raw}; normalized={cleaned}",
                    extractor=SOURCE_VERSION,
                )
            )
            return replace(
                base,
                canonical_source=cleaned,
                original_publisher=original,
                evidence=tuple(evidence),
                confidence=max(base.confidence, 0.98),
            )

    return replace(base, evidence=tuple(evidence))


def _bounded_xinhua_header_dateline(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> str:
    sample = _title_local_sample(
        bundle.body_markdown or bundle.body_text or "",
        record.title_hint or bundle.raw_title or resolved_title,
        limit=1100,
    )
    match = _XINHUA_HEADER_DATELINE_RE.search(sample)
    if match is None or match.start() > 700:
        return ""

    # A true lead/dateline can share a line with date/byline metadata, but it
    # should precede substantive article prose. Multiple completed sentences
    # before the cue indicate a mid-body attribution rather than a lead dateline.
    prefix = sample[: match.start()]
    if sum(prefix.count(mark) for mark in "。！？!?") > 4:
        return ""
    return _excerpt(sample, match)


def _title_local_self_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> tuple[str, str]:
    sample = _title_local_sample(
        bundle.body_markdown or bundle.body_text or "",
        record.title_hint or bundle.raw_title or resolved_title,
        limit=3200,
    )
    for match in _SELF_SOURCE_RE.finditer(sample):
        publisher = normalize_space(match.group("publisher")).strip(
            " ：:|｜_*`~"
        )[:80]
        if not publisher or not _publisher_matches_title_brand(
            record.title_hint or bundle.raw_title or resolved_title,
            publisher,
        ):
            continue

        prefix = sample[max(0, match.start() - 760) : match.start()]
        if _DATE_RE.search(prefix) is None or _READ_MARKER_RE.search(prefix) is None:
            continue
        if not _has_same_site_byline_profile(record.url, prefix):
            continue
        return publisher, _excerpt(sample, match, limit=420)
    return "", ""


def _title_local_external_official_account(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> tuple[str, str, str]:
    sample = _title_local_sample(
        bundle.body_markdown or bundle.body_text or "",
        record.title_hint or bundle.raw_title or resolved_title,
        limit=2600,
    )
    match = _EXTERNAL_OFFICIAL_ACCOUNT_RE.search(sample)
    if match is None:
        return "", "", ""
    publisher = normalize_space(match.group("label")).strip(" ：:|｜_*`~")[:80]
    original_url = normalize_space(match.group("url"))
    if (
        not publisher
        or not original_url
        or not different_host(record.url, original_url)
        or host(original_url) in {"", host(record.url)}
    ):
        return "", "", ""
    return publisher, original_url, _excerpt(sample, match, limit=440)


def _bounded_markdown_source_identity(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> str:
    sample = _title_local_sample(
        bundle.body_markdown or bundle.body_text or "",
        record.title_hint or bundle.raw_title or resolved_title,
        limit=3600,
    )
    match = _MARKDOWN_SOURCE_RE.search(sample)
    if match is None:
        return ""
    return normalize_space(match.group("label")).strip(" ：:|｜_*`~")[:80]


def _matches_explicit_source_evidence(base: SourceResolution, cleaned: str) -> bool:
    clean_key = _publisher_key(cleaned)
    if not clean_key:
        return False
    for item in base.evidence:
        if item.evidence_type not in {
            "explicit_source_label",
            "explicit_source_label_boundary",
        }:
            continue
        value = normalize_space(str(item.value or ""))
        if value and _publisher_key(value) == clean_key:
            return True
    return False


def _direct_xinhua_publisher(record: DiscoveryRecord, base: SourceResolution) -> bool:
    registered = normalize_space(record.raw_metadata.get("source_name", ""))
    for publisher in (
        registered,
        base.hosting_source,
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
    return bool(
        _publisher_key(base.canonical_source) in fallback_keys
        and _publisher_key(base.hosting_source) in fallback_keys
    )


def _recovered_hosting_identity(
    base: SourceResolution,
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    resolved_title: str,
) -> str:
    if _identity_is_fallback(base, record, bundle, resolved_title):
        return host(record.url) or base.hosting_source
    return base.hosting_source


def _has_same_site_byline_profile(page_url: str, prefix: str) -> bool:
    page_host = host(page_url)
    if not page_host:
        return False
    for match in _BYLINE_LINK_RE.finditer(prefix):
        profile_host = host(match.group("url"))
        if profile_host and profile_host != page_host and _same_site(page_host, profile_host):
            return True
    return False


def _same_site(left: str, right: str) -> bool:
    return bool(
        left
        and right
        and (
            left == right
            or left.endswith("." + right)
            or right.endswith("." + left)
        )
    )


def _publisher_matches_title_brand(title: str, publisher: str) -> bool:
    title_value = normalize_space(title)
    publisher_key = _publisher_key(publisher)
    if not title_value or not publisher_key:
        return False
    segments = re.split(r"[|｜—–\-]+", title_value)
    return any(
        _publisher_key(segment) == publisher_key for segment in segments[-3:]
    ) or _publisher_key(title_value).endswith(publisher_key)


def _title_local_sample(body: str, title: str, *, limit: int) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        needles = [clean_title]
        for width in (72, 64, 56, 48, 40, 36, 28, 24, 18, 16):
            if len(clean_title) > width:
                needles.append(clean_title[:width])
        for needle in needles:
            position = value.find(needle)
            if 0 <= position <= 12000:
                return value[position : position + limit]
    return value[:limit]


def _publisher_key(value: str) -> str:
    return re.sub(
        r"[\s·•（）()《》「」【】\[\]_:：|｜—–\-_*`~]+",
        "",
        normalize_space(value),
    ).lower()


def _excerpt(value: str, match: re.Match[str], limit: int = 360) -> str:
    start = max(0, match.start() - 120)
    end = min(len(value), match.end() + 160)
    return normalize_space(value[start:end])[:limit]


def _retag_version(evidence: tuple) -> tuple:
    return tuple(
        replace(item, extractor=SOURCE_VERSION)
        if item.extractor.startswith("canonical-source-")
        else item
        for item in evidence
    )


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]