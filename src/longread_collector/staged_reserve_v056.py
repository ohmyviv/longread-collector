"""Bounded two-stage reserve allocation for collector v0.5.6 PR-B."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url
from .ranked_selection_v056 import (
    ABSOLUTE_HOST_CAP,
    NATIVE_SOURCE_CAP,
    OPEN_DOMAIN_CAP,
)
from .selection_plan_v056 import SelectionReservePlan

RESERVE_STAGE_SLOTS = 8


@dataclass(slots=True)
class StagedReserveDecision:
    first_stage: list[DiscoveredURL]
    second_stage: list[DiscoveredURL]
    promoted_reserves: list[DiscoveredURL]
    deferred_not_extracted: list[DiscoveredURL]
    failed_first_stage: list[DiscoveredURL]


def _selection(item: DiscoveredURL) -> dict[str, Any]:
    return item.metadata.setdefault("selection", {})


def _bucket(item: DiscoveredURL) -> str:
    return str(_selection(item).get("selection_bucket", "open"))


def _group(item: DiscoveredURL) -> str:
    return str(_selection(item).get("selection_group", ""))


def _group_cap(item: DiscoveredURL) -> int:
    return NATIVE_SOURCE_CAP if _bucket(item) == "native" else OPEN_DOMAIN_CAP


def _score(item: DiscoveredURL) -> tuple[int, ...]:
    selection = _selection(item)
    components = selection.get("score_components", {})
    return (
        1 if _bucket(item) == "native" else 0,
        int(components.get("quality", 0)),
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        int(components.get("freshness_ordinal", 0)),
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        int(components.get("rank_score", 0)),
    )


def article_is_usable(article: ExtractedArticle) -> bool:
    return (
        article.extraction_status == "success"
        and article.candidate_disposition != "reject"
    )


def split_first_stage(
    selected: list[DiscoveredURL],
    *,
    max_attempts: int,
    reserve_slots: int = RESERVE_STAGE_SLOTS,
) -> tuple[list[DiscoveredURL], list[DiscoveredURL]]:
    """Defer the lowest-ranked open items while preserving native first-pass recall."""
    bounded = list(selected[: max(0, max_attempts)])
    defer_count = min(max(0, reserve_slots), len(bounded))
    if defer_count == 0:
        return bounded, []

    # Prefer deferring low-ranked open-search candidates. If there are fewer
    # than reserve_slots open items, defer the lowest-ranked remaining items.
    defer_order = sorted(
        bounded,
        key=lambda item: (
            0 if _bucket(item) == "open" else 1,
            _score(item),
            int(_selection(item).get("selected_order", 0)),
        ),
    )
    deferred_urls = {
        canonicalize_url(item.url) for item in defer_order[:defer_count]
    }
    first = [
        item for item in bounded if canonicalize_url(item.url) not in deferred_urls
    ]
    deferred = [
        item for item in bounded if canonicalize_url(item.url) in deferred_urls
    ]
    deferred.sort(
        key=lambda item: int(_selection(item).get("selected_order", 0))
    )
    return first, deferred


def _successful_counts(
    items: list[DiscoveredURL],
    articles: list[ExtractedArticle],
) -> tuple[Counter[str], Counter[str]]:
    groups: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    for item, article in zip(items, articles, strict=True):
        if not article_is_usable(article):
            continue
        groups[_group(item)] += 1
        hosts[domain_from_url(item.url)] += 1
    return groups, hosts


def _can_schedule(
    item: DiscoveredURL,
    *,
    group_counts: Counter[str],
    host_counts: Counter[str],
) -> bool:
    return (
        group_counts[_group(item)] < _group_cap(item)
        and host_counts[domain_from_url(item.url)] < ABSOLUTE_HOST_CAP
    )


def _schedule(
    item: DiscoveredURL,
    *,
    second_stage: list[DiscoveredURL],
    group_counts: Counter[str],
    host_counts: Counter[str],
    attempted: set[str],
) -> bool:
    canonical = canonicalize_url(item.url)
    if canonical in attempted or not _can_schedule(
        item, group_counts=group_counts, host_counts=host_counts
    ):
        return False
    attempted.add(canonical)
    second_stage.append(item)
    # Reserve capacity pessimistically: a successful extraction must remain
    # within source/domain and absolute host caps.
    group_counts[_group(item)] += 1
    host_counts[domain_from_url(item.url)] += 1
    return True


def build_second_stage(
    *,
    plan: SelectionReservePlan,
    first_stage: list[DiscoveredURL],
    deferred: list[DiscoveredURL],
    first_articles: list[ExtractedArticle],
    max_attempts: int,
) -> StagedReserveDecision:
    remaining_slots = max(0, max_attempts - len(first_stage))
    second_stage: list[DiscoveredURL] = []
    promoted: list[DiscoveredURL] = []
    attempted = {canonicalize_url(item.url) for item in first_stage}
    group_counts, host_counts = _successful_counts(first_stage, first_articles)
    failures = [
        item
        for item, article in zip(first_stage, first_articles, strict=True)
        if not article_is_usable(article)
    ]
    reserves = list(plan.reserves)

    # First use same-source/domain reserve for failed or rejected first-stage
    # items. This turns source cap overflow into a genuine replacement pool.
    for failed in failures:
        if len(second_stage) >= remaining_slots:
            break
        replacement = next(
            (
                item
                for item in reserves
                if _group(item) == _group(failed)
                and _can_schedule(
                    item, group_counts=group_counts, host_counts=host_counts
                )
                and canonicalize_url(item.url) not in attempted
            ),
            None,
        )
        if replacement is None:
            continue
        if _schedule(
            replacement,
            second_stage=second_stage,
            group_counts=group_counts,
            host_counts=host_counts,
            attempted=attempted,
        ):
            reserves.remove(replacement)
            promoted.append(replacement)
            selection = _selection(replacement)
            selection["selection_status"] = "reserve_promoted"
            selection["reserve_promoted"] = True
            selection["reserve_replacement_for"] = canonicalize_url(failed.url)
            selection["selection_phase"] = "same_group_failure_replacement"
            selection["capacity_backfill"] = True

    # Preserve the original Top-32 decision for all remaining slots.
    for item in deferred:
        if len(second_stage) >= remaining_slots:
            break
        _schedule(
            item,
            second_stage=second_stage,
            group_counts=group_counts,
            host_counts=host_counts,
            attempted=attempted,
        )

    # If cap changes caused a deferred item to be displaced, use the best
    # remaining reserve while preserving final source/domain diversity.
    for item in reserves:
        if len(second_stage) >= remaining_slots:
            break
        if _schedule(
            item,
            second_stage=second_stage,
            group_counts=group_counts,
            host_counts=host_counts,
            attempted=attempted,
        ):
            promoted.append(item)
            selection = _selection(item)
            selection["selection_status"] = "reserve_promoted"
            selection["reserve_promoted"] = True
            selection["selection_phase"] = "unused_slot_reserve_backfill"
            selection["capacity_backfill"] = True

    actual_urls = {
        canonicalize_url(item.url) for item in first_stage + second_stage
    }
    deferred_not_extracted = [
        item
        for item in deferred
        if canonicalize_url(item.url) not in actual_urls
    ]
    for item in deferred_not_extracted:
        selection = _selection(item)
        selection.pop("selected_order", None)
        selection["selection_status"] = "deferred_not_extracted"
        selection["reserve_reason"] = "replaced_within_body_cap"

    for order, item in enumerate(first_stage + second_stage, start=1):
        selection = _selection(item)
        selection["selected_order"] = order
        selection["actual_extraction_order"] = order

    return StagedReserveDecision(
        first_stage=first_stage,
        second_stage=second_stage,
        promoted_reserves=promoted,
        deferred_not_extracted=deferred_not_extracted,
        failed_first_stage=failures,
    )


__all__ = [
    "RESERVE_STAGE_SLOTS",
    "StagedReserveDecision",
    "article_is_usable",
    "build_second_stage",
    "split_first_stage",
]
