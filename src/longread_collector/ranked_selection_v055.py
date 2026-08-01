from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url
from .quality import discovery_reject_reason

SELECTION_VERSION = "ranked-bucketed-v0.5.5"
NATIVE_BUCKET_TARGET = 16
OPEN_BUCKET_TARGET = 16
NATIVE_SOURCE_CAP = 4
OPEN_DOMAIN_CAP = 2
ABSOLUTE_HOST_CAP = 4

ARTICLE_PATH_RE = re.compile(
    r"/(?:articles?|contents?|detail|stories?|news)/|"
    r"/\d{4}/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/",
    re.IGNORECASE,
)
DATE_PATH_RE = re.compile(
    r"(?:/|\b)(20\d{2})[-/]?(0[1-9]|1[0-2])[-/]?([0-2]\d|3[01])(?:/|\b)"
)
NUMERIC_ARTICLE_RE = re.compile(
    r"/(?:\d{6,}|[a-f0-9]{16,})(?:\.[a-z]{2,5})?(?:$|[/?#])", re.I
)
DEPTH_RE = re.compile(
    r"(?:深度|调查|特稿|专访|访谈|解析|长文|in[- ]depth|investigation|"
    r"long\s*read|longform|feature|analysis|interview)",
    re.IGNORECASE,
)
LOW_VALUE_COMPANION_RE = re.compile(
    r"\b(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+takeaways?\b|"
    r"\bwhat\s+to\s+know\b|\bsummary\b|(?:要点|速览)",
    re.IGNORECASE,
)
INSTITUTIONAL_RE = re.compile(
    r"(?:upholds? research integrity|annual report|team update|工作总结|成果发布)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class _Candidate:
    item: DiscoveredURL
    original_index: int
    canonical_url: str
    domain: str
    group_key: str
    bucket: str
    group_cap: int
    score: tuple[int, int, int, int, int, int, int]
    score_components: dict[str, int]


def _is_native(item: DiscoveredURL) -> bool:
    return str(item.metadata.get("purpose", "")) == "native_source_scan"


def _date_ordinal(item: DiscoveredURL) -> int:
    raw = str(item.published_at or "").strip()
    if raw:
        try:
            return parsedate_to_datetime(raw).date().toordinal()
        except (TypeError, ValueError, OverflowError):
            pass
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().toordinal()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%B %d, %Y", "%b %d, %Y"):
            try:
                return datetime.strptime(raw[:40], fmt).date().toordinal()
            except ValueError:
                continue
    match = DATE_PATH_RE.search(item.url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date().toordinal()
        except ValueError:
            return 0
    return 0


def _score(item: DiscoveredURL, original_index: int) -> tuple[tuple[int, ...], dict[str, int]]:
    canonical = canonicalize_url(item.url)
    path = urlsplit(canonical).path.lower()
    title = str(item.title or "").strip()
    description = str(item.description or "")
    sample = f"{title} {description}"

    article_confidence = 0
    if ARTICLE_PATH_RE.search(path):
        article_confidence += 4
    if NUMERIC_ARTICLE_RE.search(path):
        article_confidence += 3
    if path.endswith((".html", ".shtml", ".htm")):
        article_confidence += 2
    if len([segment for segment in path.split("/") if segment]) >= 3:
        article_confidence += 1

    quality = 2
    if LOW_VALUE_COMPANION_RE.search(title):
        quality -= 6
    if INSTITUTIONAL_RE.search(title):
        quality -= 2
    depth = min(4, len(DEPTH_RE.findall(sample)))
    freshness = _date_ordinal(item)
    title_richness = min(len(title) // 18, 4)
    description_richness = min(len(description) // 100, 3)
    rank = int(item.rank or 0)
    rank_score = -(rank if rank > 0 else original_index + 1)
    components = {
        "quality": quality,
        "article_confidence": article_confidence,
        "depth": depth,
        "freshness_ordinal": freshness,
        "title_richness": title_richness,
        "description_richness": description_richness,
        "rank_score": rank_score,
    }
    return (
        quality,
        article_confidence,
        depth,
        freshness,
        title_richness,
        description_richness,
        rank_score,
    ), components


def _annotate(candidate: _Candidate) -> None:
    candidate.item.metadata.setdefault("selection", {})
    candidate.item.metadata["selection"].update(
        {
            "version": SELECTION_VERSION,
            "selection_bucket": candidate.bucket,
            "selection_group": candidate.group_key,
            "ranking_score_total": sum(candidate.score_components.values()),
            "page_type_score": candidate.score_components["quality"] + candidate.score_components["article_confidence"],
            "freshness_score": candidate.score_components["freshness_ordinal"],
            "depth_score": candidate.score_components["depth"],
            "source_quality_score": 2 if candidate.bucket == "native" else 0,
            "score_components": candidate.score_components,
        }
    )


def _round_robin(
    groups: list[tuple[str, list[_Candidate]]],
    *,
    target: int,
    accepted: list[_Candidate],
    host_counts: dict[str, int],
    rejected: list[dict[str, str]],
    max_rounds: int | None = None,
) -> None:
    round_index = 0
    while len(accepted) < target:
        if max_rounds is not None and round_index >= max_rounds:
            break
        progressed = False
        for _, candidates in groups:
            if round_index >= len(candidates):
                continue
            candidate = candidates[round_index]
            selection = candidate.item.metadata.setdefault("selection", {})
            if selection.get("selected_order"):
                continue
            if host_counts.get(candidate.domain, 0) >= ABSOLUTE_HOST_CAP:
                selection["capacity_bucket_reject_reason"] = "absolute_host_cap"
                rejected.append({"url": candidate.item.url, "reason": "per_domain_cap"})
                continue
            accepted.append(candidate)
            host_counts[candidate.domain] = host_counts.get(candidate.domain, 0) + 1
            selection["selected_order"] = len(accepted)
            progressed = True
            if len(accepted) >= target:
                break
        if not progressed:
            break
        round_index += 1


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Select a 16/16 native/open portfolio, then backfill unused capacity."""

    max_urls = max(0, int(max_urls))
    open_cap = max(1, int(max_per_domain))
    rejected: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    native_groups: OrderedDict[str, list[_Candidate]] = OrderedDict()
    open_groups: OrderedDict[str, list[_Candidate]] = OrderedDict()

    for original_index, item in enumerate(discovered):
        canonical = canonicalize_url(item.url)
        if canonical in seen_urls:
            item.metadata.setdefault("selection", {}).update(
                {"version": SELECTION_VERSION, "capacity_bucket_reject_reason": "duplicate_url"}
            )
            rejected.append({"url": item.url, "reason": "duplicate_url"})
            continue
        seen_urls.add(canonical)

        reason = discovery_reject_reason(item.url, item.title, item.description)
        if reason:
            item.metadata.setdefault("selection", {}).update(
                {"version": SELECTION_VERSION, "capacity_bucket_reject_reason": reason}
            )
            rejected.append({"url": item.url, "reason": reason})
            continue

        domain = domain_from_url(canonical)
        native = _is_native(item)
        bucket = "native" if native else "open"
        source_id = str(item.metadata.get("source_id", "")).strip()
        group_key = f"source:{source_id or domain}" if native else f"domain:{domain}"
        group_cap = NATIVE_SOURCE_CAP if native else open_cap
        score, components = _score(item, original_index)
        candidate = _Candidate(
            item=item,
            original_index=original_index,
            canonical_url=canonical,
            domain=domain,
            group_key=group_key,
            bucket=bucket,
            group_cap=group_cap,
            score=score,
            score_components=components,
        )
        _annotate(candidate)
        target_groups = native_groups if native else open_groups
        target_groups.setdefault(group_key, []).append(candidate)

    def prepare(groups: OrderedDict[str, list[_Candidate]], overflow_reason: str):
        prepared: list[tuple[str, list[_Candidate]]] = []
        for group_key, candidates in groups.items():
            candidates.sort(key=lambda candidate: candidate.score, reverse=True)
            cap = candidates[0].group_cap
            kept = candidates[:cap]
            for candidate in candidates[cap:]:
                candidate.item.metadata["selection"]["capacity_bucket_reject_reason"] = overflow_reason
                rejected.append({"url": candidate.item.url, "reason": overflow_reason})
            prepared.append((group_key, kept))
        prepared.sort(key=lambda pair: pair[1][0].score if pair[1] else tuple(), reverse=True)
        return prepared

    native_prepared = prepare(native_groups, "per_source_cap")
    open_prepared = prepare(open_groups, "per_domain_cap")

    accepted: list[_Candidate] = []
    host_counts: dict[str, int] = {}

    native_target = min(max_urls, NATIVE_BUCKET_TARGET)
    _round_robin(
        native_prepared,
        target=native_target,
        accepted=accepted,
        host_counts=host_counts,
        rejected=rejected,
        max_rounds=2,
    )

    open_target = min(max_urls, len(accepted) + OPEN_BUCKET_TARGET)
    _round_robin(
        open_prepared,
        target=open_target,
        accepted=accepted,
        host_counts=host_counts,
        rejected=rejected,
        max_rounds=2,
    )

    if len(accepted) < max_urls:
        _round_robin(
            native_prepared,
            target=max_urls,
            accepted=accepted,
            host_counts=host_counts,
            rejected=rejected,
            max_rounds=None,
        )
    if len(accepted) < max_urls:
        _round_robin(
            open_prepared,
            target=max_urls,
            accepted=accepted,
            host_counts=host_counts,
            rejected=rejected,
            max_rounds=None,
        )

    selected_urls = {candidate.canonical_url for candidate in accepted}
    for groups, bucket_reason in (
        (native_prepared, "native_bucket_capacity"),
        (open_prepared, "open_bucket_capacity"),
    ):
        for _, candidates in groups:
            for candidate in candidates:
                if candidate.canonical_url not in selected_urls:
                    candidate.item.metadata["selection"].setdefault(
                        "capacity_bucket_reject_reason", bucket_reason
                    )

    return [candidate.item for candidate in accepted], rejected


__all__ = [
    "SELECTION_VERSION",
    "NATIVE_BUCKET_TARGET",
    "OPEN_BUCKET_TARGET",
    "NATIVE_SOURCE_CAP",
    "OPEN_DOMAIN_CAP",
    "ABSOLUTE_HOST_CAP",
    "filter_discovered",
]
