"""Capacity-safe reserve allocation after the v0.5.6l zh-midday underfill."""

from __future__ import annotations

from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url
from .selection_plan_v056 import SelectionReservePlan
from .staged_reserve_v056 import (
    RESERVE_STAGE_SLOTS,
    SECOND_STAGE_MIN_EDITORIAL_PRIORITY,
    StagedReserveDecision,
    _can_schedule,
    _group,
    _late_stage_eligible,
    _priority,
    _promote,
    _schedule,
    _score,
    _selection,
    _successful_counts,
    article_is_usable,
    split_first_stage,
)

CAPACITY_RECOVERY_MIN_EDITORIAL_PRIORITY = 32
STAGED_RESERVE_VERSION = "staged-reserve-v0.5.6m"


def _capacity_recovery_eligible(item: DiscoveredURL) -> bool:
    selection = _selection(item)
    priority = _priority(item)
    page_gate = item.metadata.get("page_gate", {})
    status = str(selection.get("selection_status", ""))
    components = selection.get("score_components", {})
    title = str(item.title or "").strip()
    eligible = (
        priority >= CAPACITY_RECOVERY_MIN_EDITORIAL_PRIORITY
        and status != "evidence_reserve_only"
        and not str(page_gate.get("reject_reason", ""))
        and len(title) >= 8
        and int(components.get("article_confidence", 0)) >= 1
    )
    selection["capacity_recovery_version"] = STAGED_RESERVE_VERSION
    selection["capacity_recovery_min_priority"] = (
        CAPACITY_RECOVERY_MIN_EDITORIAL_PRIORITY
    )
    selection["capacity_recovery_eligible"] = eligible
    if not eligible:
        selection.setdefault(
            "capacity_recovery_skip_reason",
            "unsafe_or_below_capacity_recovery_threshold",
        )
    return eligible


def build_second_stage_v056m(
    *,
    plan: SelectionReservePlan,
    first_stage: list[DiscoveredURL],
    deferred: list[DiscoveredURL],
    first_articles: list[ExtractedArticle],
    max_attempts: int,
) -> StagedReserveDecision:
    # When fewer than 24 items were selected initially, the unused first-stage
    # capacity remains available in addition to the normal eight reserve slots.
    remaining_slots = max(0, int(max_attempts) - len(first_stage))
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
    for item in deferred + reserves:
        _late_stage_eligible(item)

    # First replace failures from the same selection group when a strong reserve
    # exists. This preserves source diversity and avoids abandoning a temporarily
    # broken route after one failed page.
    for failed in failures:
        if len(second_stage) >= remaining_slots:
            break
        replacement = next(
            (
                item
                for item in reserves
                if _group(item) == _group(failed)
                and _late_stage_eligible(item)
                and _can_schedule(
                    item,
                    group_counts=group_counts,
                    host_counts=host_counts,
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
                phase="same_group_failure_replacement_v056m",
                promoted=promoted,
            )
            selection = _selection(replacement)
            selection["reserve_replacement_for"] = canonicalize_url(failed.url)
            selection["reserve_replacement_reason"] = "failed_first_stage"

    deferred_urls = {canonicalize_url(item.url) for item in deferred}
    reserve_urls = {canonicalize_url(item.url) for item in reserves}

    # Preserve the existing high-precision second-stage threshold first.
    candidate_pool = [
        item for item in list(deferred) + list(reserves) if _late_stage_eligible(item)
    ]
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
                phase="editorial_reserve_promotion_v056m",
                promoted=promoted,
            )
            selection["reserve_replacement_reason"] = (
                "higher_editorial_priority_than_deferred"
            )
        elif canonical in deferred_urls:
            selection["selection_status"] = "deferred_revalidated"
            selection["selection_phase"] = "deferred_top32_revalidated_v056m"
            selection["second_stage_editorial_priority"] = _priority(item)

    # If safe article-like reserves still exist, recover unused capacity instead
    # of stopping early. Deterministic page gates, evidence-only items and weak
    # titles remain excluded; the 32-attempt hard cap is unchanged.
    recovery_pool = [
        item
        for item in list(deferred) + list(reserves)
        if canonicalize_url(item.url) not in attempted
        and _capacity_recovery_eligible(item)
    ]
    recovery_pool.sort(key=_score, reverse=True)
    for item in recovery_pool:
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
                phase="capacity_recovery_promotion_v056m",
                promoted=promoted,
            )
        else:
            selection["selection_status"] = "deferred_capacity_recovery"
            selection["selection_phase"] = "capacity_recovery_v056m"
        selection["capacity_recovery"] = True
        selection["capacity_recovery_priority"] = _priority(item)

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
        selection["reserve_reason"] = "outscored_or_unsafe_in_second_stage"
        selection["displaced_editorial_priority"] = _priority(item)

    quality_promotions = [
        item
        for item in promoted
        if _selection(item).get("selection_phase")
        in {
            "editorial_reserve_promotion_v056m",
            "capacity_recovery_promotion_v056m",
        }
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
        selection["staged_reserve_version"] = STAGED_RESERVE_VERSION

    return StagedReserveDecision(
        first_stage=first_stage,
        second_stage=second_stage,
        promoted_reserves=promoted,
        deferred_not_extracted=deferred_not_extracted,
        failed_first_stage=failures,
    )


__all__ = [
    "CAPACITY_RECOVERY_MIN_EDITORIAL_PRIORITY",
    "RESERVE_STAGE_SLOTS",
    "SECOND_STAGE_MIN_EDITORIAL_PRIORITY",
    "STAGED_RESERVE_VERSION",
    "StagedReserveDecision",
    "article_is_usable",
    "build_second_stage_v056m",
    "split_first_stage",
]
