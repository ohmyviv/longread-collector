"""Hosting/original publisher and source-action resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    DiscoveryRecord,
    Evidence,
    SourceAction,
    SourceRelationship,
)
from .evidence import (
    different_host,
    external_link,
    first_match,
    host,
    make_evidence,
    nested,
    normalize_space,
    text,
)

SOURCE_VERSION = "canonical-source-v0.6-pr2"

_OFFICIAL_TERMS = (
    "人民政府",
    "人民银行",
    "国务院",
    "委员会",
    "办公厅",
    "办公室",
    "人民法院",
    "人民检察院",
    "财政部",
    "教育部",
    "商务部",
    "国家",
)
_PRIMARY_TITLE_TERMS = (
    "通知",
    "公告",
    "办法",
    "规定",
    "意见",
    "条例",
    "规划",
    "决定",
    "批复",
    "工作会议",
    "会议",
    "方案",
    "报告",
)

_DOMAIN_PUBLISHERS = {
    "peopleapp.com": "人民日报",
    "paper.people.com.cn": "人民日报",
    "people.com.cn": "人民网",
    "news.cctv.com": "央视网",
    "cctv.com": "央视网",
    "pbc.gov.cn": "中国人民银行",
}


@dataclass(frozen=True, slots=True)
class SourceResolution:
    hosting_source: str
    canonical_source: str
    original_publisher: str
    canonical_content_url: str
    relationship: SourceRelationship
    action: SourceAction
    asset_class: AssetClass
    evidence: tuple[Evidence, ...]
    confidence: float


def resolve_source(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    resolved_title: str,
    primary_document_hint: bool,
    transcript_hint: bool,
) -> SourceResolution:
    metadata = record.raw_metadata
    body = bundle.body_markdown or bundle.body_text
    target_url = external_link(metadata)
    hosting = _hosting_source(record, bundle)
    explicit = _explicit_publisher(body, resolved_title)
    target_publisher = _publisher_from_domain(host(target_url)) if target_url else ""

    title_publisher = _publisher_from_title(resolved_title) if primary_document_hint else ""
    canonical = (
        explicit
        or target_publisher
        or title_publisher
        or hosting
        or _publisher_from_domain(host(record.url))
    )
    original = canonical

    target_is_external = bool(target_url and different_host(record.url, target_url))
    explicit_differs = bool(explicit and hosting and not _same_publisher(explicit, hosting))

    if target_is_external or explicit_differs:
        relationship = SourceRelationship.SECONDARY_REPUBLISH
    else:
        relationship = SourceRelationship.ORIGINAL

    asset_class = _asset_class(
        canonical,
        resolved_title,
        body,
        primary_document_hint=primary_document_hint,
        transcript_hint=transcript_hint,
    )

    if target_is_external:
        action = SourceAction.REPLACE_WITH_ORIGINAL
        canonical_url = target_url
    elif relationship is SourceRelationship.SECONDARY_REPUBLISH:
        if asset_class is AssetClass.PRIMARY_DOCUMENT:
            action = SourceAction.FIND_PRIMARY_DOCUMENT
        else:
            action = SourceAction.RETAIN_CURRENT_DISPLAY_URL
        canonical_url = record.url
    else:
        action = SourceAction.NONE
        canonical_url = record.url

    evidence: list[Evidence] = []
    if hosting:
        evidence.append(
            make_evidence(
                record.item_id,
                "hosting_source",
                "hosting_source",
                hosting,
                confidence=0.82,
                extractor=SOURCE_VERSION,
            )
        )
    if explicit:
        evidence.append(
            make_evidence(
                record.item_id,
                "explicit_source_label",
                "canonical_source",
                explicit,
                confidence=0.97,
                excerpt=_source_excerpt(body, explicit),
                extractor=SOURCE_VERSION,
            )
        )
    if target_url:
        evidence.append(
            make_evidence(
                record.item_id,
                "external_original_target",
                "canonical_content_url",
                target_url,
                confidence=0.96 if target_is_external else 0.70,
                extractor=SOURCE_VERSION,
            )
        )
    evidence.append(
        make_evidence(
            record.item_id,
            "source_relationship",
            "source_relationship",
            relationship.value,
            confidence=0.94 if (target_is_external or explicit_differs) else 0.78,
            extractor=SOURCE_VERSION,
        )
    )
    return SourceResolution(
        hosting_source=hosting,
        canonical_source=canonical,
        original_publisher=original,
        canonical_content_url=canonical_url,
        relationship=relationship,
        action=action,
        asset_class=asset_class,
        evidence=tuple(evidence),
        confidence=0.94 if (explicit or target_publisher) else 0.76,
    )


def _hosting_source(record: DiscoveryRecord, bundle: AcquisitionBundle) -> str:
    metadata = record.raw_metadata
    for value in (
        nested(metadata, "discovery", "source_name"),
        nested(metadata, "source_resolution", "resolved"),
        nested(metadata, "source_resolution", "source_name"),
    ):
        candidate = text(value)
        if candidate and candidate.lower() not in {"gov", "gdjr", "shanghai", "udn", "thepaper"}:
            return candidate

    body = bundle.body_markdown or bundle.body_text
    copyright_holder = first_match(
        (
            r"(?:版权|版權)\s*[：:]\s*([^\n]{2,50})",
            r"(?:主办单位|主辦單位)\s*[：:]\s*([^\n]{2,50})",
        ),
        body,
    )
    if copyright_holder:
        return copyright_holder

    raw_title = normalize_space(bundle.raw_title or record.title_hint)
    if raw_title and _looks_like_institution(raw_title) and len(raw_title) <= 40:
        return raw_title
    return host(record.url)


def _explicit_publisher(body: str, title: str) -> str:
    source = first_match(
        (
            r"^[ \t]*(?:来源|來源|稿源|原载|原載|转载自|轉載自)\s*[：:]\s*([^|\n]{2,50})",
            r"(?:来源|來源)\s*[：:]\s*([^|\n]{2,50})\s*$",
        ),
        body,
    )
    if source:
        return _clean_publisher(source)

    bracket = re.search(r"【([^】]{2,30})】\s*$", title)
    if bracket:
        return _clean_publisher(bracket.group(1))

    published_by = re.search(
        r"[《「]([^》」]{2,30}(?:日报|日報|周报|週報|财经|財經|新闻|新聞|报道|報道))[》」]"
        r"(?:刊发|刊發|刊登|发表|發表|报道|報道)",
        body[:5000],
    )
    if published_by:
        return _clean_publisher(published_by.group(1))
    return ""


def _clean_publisher(value: str) -> str:
    candidate = normalize_space(value)
    candidate = re.sub(r"\s*[|｜].*$", "", candidate)
    candidate = re.sub(r"\s+\d{4}[-年].*$", "", candidate)
    return candidate.strip(" ：:|｜")


def _source_excerpt(body: str, publisher: str) -> str:
    index = body.find(publisher)
    if index < 0:
        return ""
    return normalize_space(body[max(0, index - 40) : index + len(publisher) + 80])


def _publisher_from_title(title: str) -> str:
    match = re.match(
        r"^(.{2,40}?(?:人民政府|人民银行|人民銀行|委员会|委員會|办公厅|辦公廳|办公室|辦公室|部|厅|廳|局))"
        r"(?:关于|關於|召开|召開|印发|印發|发布|發布|制定|修订|修訂)",
        title,
    )
    return normalize_space(match.group(1)) if match else ""


def _publisher_from_domain(domain: str) -> str:
    if not domain:
        return ""
    for suffix, publisher in _DOMAIN_PUBLISHERS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return publisher
    return ""


def _asset_class(
    publisher: str,
    title: str,
    body: str,
    *,
    primary_document_hint: bool,
    transcript_hint: bool,
) -> AssetClass:
    if primary_document_hint or (
        _looks_official(publisher) and _looks_primary_document(title, body)
    ):
        return AssetClass.PRIMARY_DOCUMENT
    if transcript_hint:
        return AssetClass.TRANSCRIPT
    return AssetClass.MEDIA_ARTICLE


def _looks_official(publisher: str) -> bool:
    return any(term in publisher for term in _OFFICIAL_TERMS)


def _looks_like_institution(value: str) -> bool:
    return _looks_official(value) or value.endswith(("银行", "銀行", "大学", "大學"))


def _looks_primary_document(title: str, body: str) -> bool:
    if any(term in title for term in _PRIMARY_TITLE_TERMS):
        return True
    prefix = body[:5000]
    return bool(
        re.search(r"[〔\[]20\d{2}[〕\]]\s*\d+\s*号", prefix)
        or re.search(r"(?:各镇|各區|各区|各部门|各部門|会议强调|會議強調|会议指出|會議指出)", prefix)
    )


def _same_publisher(left: str, right: str) -> bool:
    def compact(value: str) -> str:
        value = re.sub(r"[\s·•（）()《》「」【】]", "", value)
        for suffix in ("官方网站", "官网", "網站", "网站"):
            value = value.removesuffix(suffix)
        return value

    a, b = compact(left), compact(right)
    return bool(a and b and (a == b or a in b or b in a))


__all__ = ["SOURCE_VERSION", "SourceResolution", "resolve_source"]
