from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url
from .ranked_selection_v055 import (
    ABSOLUTE_HOST_CAP,
    NATIVE_SOURCE_CAP,
    OPEN_DOMAIN_CAP,
    filter_discovered as _ranked_filter_discovered,
)

PREFILTER_VERSION = "deterministic-prefilter-v0.5.5"

_CORRECTION_RE = re.compile(
    r"^(?:author\s+)?correction\s*:|^corrigendum\b|^erratum\b|^(?:更正|勘误)[：:]?",
    re.IGNORECASE,
)
_ROUNDUP_RE = re.compile(
    r"\bcheat\s+sheet\b|^the\s+download\s*:|^briefing\s+chat\s*:|"
    r"\bbooks?\s+in\s+brief\b|\bweek(?:ly)?\s+in\s+review\b|"
    r"\bdaily\s+briefing\b|\bmorning\s+briefing\b|(?:一周|每周)(?:简报|回顾|速览)",
    re.IGNORECASE,
)
_MARKET_REPORT_RE = re.compile(
    r"\bmarket\s+(?:report|size|forecast)\b.*\b20\d{2}\s*[-–]\s*20\d{2}\b|"
    r"\bworth\s+\$?[\d,.]+\s+(?:million|billion|trillion)\s+by\s+20\d{2}\b",
    re.IGNORECASE,
)
_COURSE_RE = re.compile(
    r"\bbest\s+.+\s+(?:courses?|programs?)\b|\bcourses?\s+after\b|"
    r"\btraining\s+(?:course|program)\b|(?:课程|培训班|研修班|招生简章)",
    re.IGNORECASE,
)
_EVENT_RE = re.compile(
    r"\b(?:annual\s+)?(?:workshop|webinar|conference|summit|symposium|forum)\b|"
    r"(?:研讨会|峰会|论坛|大会|工作坊)",
    re.IGNORECASE,
)
_GOV_EVENT_RE = re.compile(
    r"(?:开展|举办|举行|召开).{0,20}(?:实践|活动|座谈会|交流会|培训|宣讲)|"
    r"(?:圆满举行|顺利举办|调研实践)",
    re.IGNORECASE,
)
_PRESS_RELEASE_DOMAINS = (
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
)
_LAWFARE_CHANNEL_TITLES = {
    "armed conflict",
    "congress",
    "courts & litigation",
    "criminal justice & rule of law",
    "cybersecurity & tech",
    "democracy & elections",
}
_BACKFILL_REASONS = {"native_bucket_capacity", "open_bucket_capacity"}


def _domain_and_path(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.netloc.lower().removeprefix("www."), (parts.path or "/").lower()


def discovery_hard_gate_reason(item: DiscoveredURL) -> str:
    domain, path = _domain_and_path(item.url)
    title = str(item.title or "").strip()
    description = str(item.description or "")
    sample = f"{title} {description}"
    lowered = title.lower()

    if domain == "cen.acs.org" and re.search(
        r"/explore/(?:features|perspectives|interviews)\.html$", path
    ):
        return "listing_page"
    if domain == "lawfaremedia.org" and (
        "/topics/" in path or lowered in _LAWFARE_CHANNEL_TITLES
    ):
        return "search_or_listing_page"
    if domain.endswith("eurekalert.org") and lowered.startswith(
        "eurekalert! news by subject"
    ):
        return "listing_page"
    if domain.endswith("mdpi.com") and "special issues" in lowered:
        return "listing_page"
    if (
        domain.endswith("frontiersin.org")
        and lowered.startswith("frontiers in ")
        and "/articles/" not in path
    ):
        return "listing_page"

    if _CORRECTION_RE.search(title):
        return "correction_notice"
    if _ROUNDUP_RE.search(title):
        return "news_roundup"
    if any(
        domain == suffix or domain.endswith("." + suffix)
        for suffix in _PRESS_RELEASE_DOMAINS
    ):
        return "press_release"
    if _MARKET_REPORT_RE.search(sample) or (
        domain.endswith("marketsandmarkets.com") and "report" in sample.lower()
    ):
        return "market_report_sales"
    if _COURSE_RE.search(sample):
        return "course_or_training"
    if _EVENT_RE.search(title) and re.search(
        r"\b(register|registration|agenda|save the date)\b|(?:报名|议程|参会)",
        sample,
        re.IGNORECASE,
    ):
        return "event_page"
    if _GOV_EVENT_RE.search(title):
        return "institutional_event_news"
    return ""


def _score_key(item: DiscoveredURL) -> tuple[int, int, int, int, int, int, int, int]:
    selection = item.metadata.get("selection", {})
    components = selection.get("score_components", {})
    bucket_priority = 1 if selection.get("selection_bucket") == "native" else 0
    return (
        bucket_priority,
        int(components.get("quality", 0)),
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        int(components.get("freshness_ordinal", 0)),
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        int(components.get("rank_score", 0)),
    )


def _backfill_unused_capacity(
    accepted: list[DiscoveredURL],
    candidates: list[DiscoveredURL],
    *,
    max_urls: int,
) -> list[DiscoveredURL]:
    if len(accepted) >= max_urls:
        return accepted

    selected_urls = {canonicalize_url(item.url) for item in accepted}
    group_counts: Counter[str] = Counter()
    host_counts: Counter[str] = Counter()
    for item in accepted:
        selection = item.metadata.get("selection", {})
        group_counts[str(selection.get("selection_group", ""))] += 1
        host_counts[domain_from_url(item.url)] += 1

    remaining = []
    for item in candidates:
        if canonicalize_url(item.url) in selected_urls:
            continue
        selection = item.metadata.get("selection", {})
        if selection.get("capacity_bucket_reject_reason") not in _BACKFILL_REASONS:
            continue
        remaining.append(item)
    remaining.sort(key=_score_key, reverse=True)

    for item in remaining:
        if len(accepted) >= max_urls:
            break
        selection = item.metadata.get("selection", {})
        bucket = str(selection.get("selection_bucket", "open"))
        group = str(selection.get("selection_group", ""))
        host = domain_from_url(item.url)
        group_cap = NATIVE_SOURCE_CAP if bucket == "native" else OPEN_DOMAIN_CAP
        if group_counts[group] >= group_cap or host_counts[host] >= ABSOLUTE_HOST_CAP:
            continue
        selection.pop("capacity_bucket_reject_reason", None)
        selection["selected_order"] = len(accepted) + 1
        selection["capacity_backfill"] = True
        accepted.append(item)
        selected_urls.add(canonicalize_url(item.url))
        group_counts[group] += 1
        host_counts[host] += 1
    return accepted


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    candidates: list[DiscoveredURL] = []
    hard_rejected: list[dict[str, str]] = []
    for item in discovered:
        reason = discovery_hard_gate_reason(item)
        if not reason:
            candidates.append(item)
            continue
        item.metadata.setdefault("selection", {}).update(
            {
                "prefilter_version": PREFILTER_VERSION,
                "deterministic_page_gate": reason,
                "capacity_bucket_reject_reason": reason,
            }
        )
        hard_rejected.append({"url": item.url, "reason": reason})

    accepted, ranked_rejected = _ranked_filter_discovered(
        candidates,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )
    accepted = _backfill_unused_capacity(
        accepted,
        candidates,
        max_urls=max_urls,
    )
    return accepted, hard_rejected + ranked_rejected


__all__ = [
    "PREFILTER_VERSION",
    "discovery_hard_gate_reason",
    "filter_discovered",
]
