from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url
from .quality import discovery_reject_reason

NATIVE_SOURCE_CAP = 4
OPEN_DOMAIN_CAP = 2
ABSOLUTE_HOST_CAP = 4

# Strong structural signals that a URL is a listing, channel or media index rather
# than a standalone article. These are rejected before any source/domain cap is
# applied so they cannot consume scarce extraction slots.
LISTING_PATH_RE = re.compile(
    r"/(?:pro/)?lists?(?:/|$)|/video/lists?(?:/|$)|/(?:channels?|sections?)(?:/|$)",
    re.IGNORECASE,
)
ARTICLE_PATH_RE = re.compile(
    r"/(?:articles?|contents?|detail|features?|stories?|news)/|"
    r"/\d{4}/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/",
    re.IGNORECASE,
)
DATE_PATH_RE = re.compile(
    r"(?:/|\b)(20\d{2})[-/]?(0[1-9]|1[0-2])[-/]?([0-2]\d|3[01])(?:/|\b)"
)
NUMERIC_ARTICLE_RE = re.compile(r"/(?:\d{6,}|[a-f0-9]{16,})(?:\.[a-z]{2,5})?(?:$|[/?#])", re.I)
DEPTH_KEYWORDS = (
    "深度",
    "调查",
    "特稿",
    "专访",
    "访谈",
    "长文",
    "解析",
    "观察",
    "报告",
    "investigation",
    "long read",
    "longform",
    "feature",
    "analysis",
    "interview",
)


@dataclass(slots=True)
class _Candidate:
    item: DiscoveredURL
    original_index: int
    canonical_url: str
    domain: str
    group_key: str
    group_cap: int
    score: tuple[int, int, int, int, int, int]


def _is_native_source(item: DiscoveredURL) -> bool:
    return str(item.metadata.get("purpose", "")) == "native_source_scan"


def _selection_group(item: DiscoveredURL, domain: str) -> tuple[str, int]:
    if _is_native_source(item):
        source_id = str(item.metadata.get("source_id", "")).strip()
        return f"source:{source_id or domain}", NATIVE_SOURCE_CAP
    return f"domain:{domain}", OPEN_DOMAIN_CAP


def _date_ordinal(item: DiscoveredURL) -> int:
    raw = str(item.published_at or "").strip()
    if raw:
        normalized = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date().toordinal()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw[:32], fmt).date().toordinal()
            except ValueError:
                continue

    match = DATE_PATH_RE.search(item.url)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).date().toordinal()
        except ValueError:
            return 0
    return 0


def _selection_score(item: DiscoveredURL, original_index: int) -> tuple[int, int, int, int, int, int]:
    canonical = canonicalize_url(item.url)
    path = urlsplit(canonical).path.lower()
    title = str(item.title or "").strip()
    combined = f"{title} {item.description or ''}".lower()

    article_confidence = 0
    if ARTICLE_PATH_RE.search(path):
        article_confidence += 4
    if NUMERIC_ARTICLE_RE.search(path):
        article_confidence += 3
    if path.endswith((".html", ".shtml", ".htm")):
        article_confidence += 2
    if len(path.strip("/").split("/")) >= 3:
        article_confidence += 1

    depth_score = sum(1 for keyword in DEPTH_KEYWORDS if keyword in combined)
    title_score = min(len(title) // 20, 3)
    description_score = min(len(str(item.description or "")) // 120, 2)
    freshness = _date_ordinal(item)
    rank = int(item.rank or 0)
    rank_score = -(rank if rank > 0 else original_index + 1)

    return (
        article_confidence,
        freshness,
        depth_score,
        title_score,
        description_score,
        rank_score,
    )


def _selection_reject_reason(item: DiscoveredURL) -> str:
    reason = discovery_reject_reason(item.url, item.title, item.description)
    if reason:
        return reason
    path = urlsplit(canonicalize_url(item.url)).path
    if LISTING_PATH_RE.search(path):
        return "listing_page"
    return ""


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Rank candidates before applying source-aware extraction limits.

    Native source scans may contribute up to four articles per source. Open or
    Firecrawl search results remain limited to two per host. A hard four-item
    host ceiling prevents native and open discovery paths from combining into
    an excessive allocation. The global ``max_urls`` extraction budget remains
    unchanged.
    """

    open_cap = max(1, int(max_per_domain))
    rejected: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    groups: OrderedDict[str, list[_Candidate]] = OrderedDict()

    for original_index, item in enumerate(discovered):
        canonical = canonicalize_url(item.url)
        if canonical in seen_urls:
            rejected.append({"url": item.url, "reason": "duplicate_url"})
            continue
        seen_urls.add(canonical)

        reason = _selection_reject_reason(item)
        if reason:
            rejected.append({"url": item.url, "reason": reason})
            continue

        domain = domain_from_url(canonical)
        group_key, default_cap = _selection_group(item, domain)
        group_cap = NATIVE_SOURCE_CAP if _is_native_source(item) else open_cap
        groups.setdefault(group_key, []).append(
            _Candidate(
                item=item,
                original_index=original_index,
                canonical_url=canonical,
                domain=domain,
                group_key=group_key,
                group_cap=group_cap or default_cap,
                score=_selection_score(item, original_index),
            )
        )

    ranked_groups: list[tuple[str, list[_Candidate]]] = []
    for group_key, candidates in groups.items():
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        cap = candidates[0].group_cap
        kept = candidates[:cap]
        overflow_reason = (
            "per_source_cap"
            if group_key.startswith("source:")
            else "per_domain_cap"
        )
        for candidate in candidates[cap:]:
            rejected.append({"url": candidate.item.url, "reason": overflow_reason})
        ranked_groups.append((group_key, kept))

    # Give each source/domain one high-quality slot before allocating second,
    # third and fourth slots. This protects diversity without allowing low-value
    # early results to win solely because they appeared first.
    ranked_groups.sort(
        key=lambda pair: pair[1][0].score if pair[1] else (0, 0, 0, 0, 0, 0),
        reverse=True,
    )
    accepted: list[DiscoveredURL] = []
    host_counts: dict[str, int] = {}
    round_index = 0
    while len(accepted) < max_urls:
        progressed = False
        for _, candidates in ranked_groups:
            if round_index >= len(candidates):
                continue
            candidate = candidates[round_index]
            if host_counts.get(candidate.domain, 0) >= ABSOLUTE_HOST_CAP:
                rejected.append({"url": candidate.item.url, "reason": "per_domain_cap"})
                continue
            accepted.append(candidate.item)
            host_counts[candidate.domain] = host_counts.get(candidate.domain, 0) + 1
            progressed = True
            if len(accepted) >= max_urls:
                break
        if not progressed:
            break
        round_index += 1

    return accepted, rejected
