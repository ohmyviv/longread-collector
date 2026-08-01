from __future__ import annotations

import re
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .ranked_selection_v055 import filter_discovered as _ranked_filter_discovered

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
    if domain.endswith("occrp.org") and title in {
        "Bad Practice",
        "OCCRP Under Attack",
        "Scam Empire",
        "Venezuela",
        "Ukraine",
        "Russia",
    }:
        return "investigation_project_page"

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
    return accepted, hard_rejected + ranked_rejected


__all__ = [
    "PREFILTER_VERSION",
    "discovery_hard_gate_reason",
    "filter_discovered",
]
