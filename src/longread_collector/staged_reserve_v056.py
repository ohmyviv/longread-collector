"""Bounded two-stage reserve allocation for collector v0.5.6g."""

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
        int(components.get("editorial_priority", 0)),
        int(components.get("quality", 0)),
        int(components.get("freshness_ordinal", 0)),
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        1 if _bucket(item) == "native" else 0,
        int(components.get("rank_score", 0)),
    )


def _priority(item: DiscoveredURL) -> int:
    return int(
        _selection(item).get("score_components", {}).get(
            "editorial_priority", 0
        )
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
    """Run the highest-utility 24 first and expose the lower eight to competition."""
    bounded = list(selected[: max(0, max_attempts)])
    defer_count = min(max(0, reserve_slots), len(bounded))
    if defer_count == 0:
        return bounded, []

    ranked = sorted(
        bounded,
        key=lambda item: (
            _score(item),
            -int(_selection(item).get("selected_order", 0)),
        ),
        reverse=True,
    )
    first_count = len(bounded) - defer_count
    first = ranked[:first_count]
    deferred = ranked[first_count:]
    for order, item in enumerate(first, start=1):
        selection = _selection(item)
        selection["selection_phase"] = "first_stage_editorial_priority"
        selection["first_stage_priority_order"] = order
    for order, item in enumerate(deferred, start=1):
        selection = _selection(item)
        selection["selection_phase"] = "second_stage_competition"
        selection["deferred_priority_order"] = order
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


def _promote(
    item: DiscoveredURL,
    *,
    phase: str,
    promoted: list[DiscoveredURL],
) -> None:
    promoted.append(item)
    selection = _selection(item)
    selection["selection_status"] = "reserve_promoted"
    selection["reserve_promoted"] = True
    selection["selection_phase"] = phase
    selection["capacity_backfill"] = True
    selection["reserve_editorial_priority"] = _priority(item)


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

    # A failed high-quality article first receives the best same-source/domain
    # replacement, preserving editorial continuity without breaching caps.
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
            _promote(
                replacement,
                phase="same_group_failure_replacement",
                promoted=promoted,
            )
            selection = _selection(replacement)
            selection["reserve_replacement_for"] = canonicalize_url(failed.url)
            selection["reserve_replacement_reason"] = "failed_first_stage"

    # The remaining second-stage slots are a genuine editorial competition.
    # Deferred Top-32 items no longer have automatic precedence over stronger
    # cap-overflow or evidence-only reserves.
    deferred_urls = {canonicalize_url(item.url) for item in deferred}
    reserve_urls = {canonicalize_url(item.url) for item in reserves}
    candidate_pool = list(deferred) + list(reserves)
    candidate_pool.sort(key=_score, reverse=True)
    for item in candidate_pool:
        if len(second_stage) >= remaining_slots:
            break
        if not _schedule(
            item,
            second_stage=second_stage,
            group_counts=group_counts,
            host_counts=host_counts,
            attempted=attempted,
        ):
            continue
        canonical = canonicalize_url(item.url)
        selection = _selection(item)
        if canonical in reserve_urls:
            _promote(
                item,
                phase="editorial_reserve_promotion",
                promoted=promoted,
            )
            selection["reserve_replacement_reason"] = (
                "higher_editorial_priority_than_deferred"
            )
        elif canonical in deferred_urls:
            selection["selection_status"] = "deferred_revalidated"
            selection["selection_phase"] = "deferred_top32_revalidated"
            selection["second_stage_editorial_priority"] = _priority(item)

    actual_urls = {
        canonicalize_url(item.url) for item in first_stage + second_stage
    }
    deferred_not_extracted = [
        item
        for item in deferred
        if canonicalize_url(item.url) not in actual_urls
    ]
    deferred_not_extracted.sort(key=_score)
    for item in deferred_not_extracted:
        selection = _selection(item)
        selection.pop("selected_order", None)
        selection["selection_status"] = "deferred_not_extracted"
        selection["reserve_reason"] = "outscored_in_second_stage"
        selection["displaced_editorial_priority"] = _priority(item)

    quality_promotions = [
        item
        for item in promoted
        if _selection(item).get("selection_phase") == "editorial_reserve_promotion"
    ]
    for promoted_item, displaced in zip(
        sorted(quality_promotions, key=_score, reverse=True),
        deferred_not_extracted,
    ):
        promoted_selection = _selection(promoted_item)
        promoted_selection["reserve_replacement_for"] = canonicalize_url(
            displaced.url
        )
        promoted_selection["displaced_editorial_priority"] = _priority(displaced)
        promoted_selection["replacement_score_delta"] = (
            _priority(promoted_item) - _priority(displaced)
        )
        _selection(displaced)["replaced_by_reserve_url"] = canonicalize_url(
            promoted_item.url
        )

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
