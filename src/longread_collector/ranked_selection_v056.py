from __future__ import annotations

from collections import OrderedDict, Counter
from dataclasses import dataclass
from typing import Any

from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url
from .quality import discovery_reject_reason
from .ranked_selection_v055 import (
    ABSOLUTE_HOST_CAP,
    NATIVE_BUCKET_TARGET,
    NATIVE_SOURCE_CAP,
    OPEN_BUCKET_TARGET,
    OPEN_DOMAIN_CAP,
    _score,
)

SELECTION_VERSION = "ranked-reserve-v0.5.6"

RESERVE_STATUSES = {
    "source_initial_cap_reserve",
    "domain_initial_cap_reserve",
    "bucket_capacity_reserve",
    "absolute_host_reserve",
    "final_not_selected",
}

# Only reasons that can be established from URL/title/description alone may
# reject a candidate before body extraction. Editorial-substance conclusions
# such as ``insufficient_editorial_evidence`` require the extracted body and
# are deliberately deferred to the post-extraction classifier.
DISCOVERY_HARD_REJECT_REASONS = {
    "spam_or_abused_upload",
    "job_page",
    "blocked_or_auth",
    "homepage",
    "social_promotion",
    "social_not_standalone",
    "listing_page",
    "service_landing",
    "reference_page",
}


@dataclass(slots=True)
class Candidate:
    item: DiscoveredURL
    original_index: int
    canonical_url: str
    domain: str
    group_key: str
    bucket: str
    group_cap: int
    score: tuple[int, ...]
    score_components: dict[str, int]
    group_rank: int = 0


def _is_native(item: DiscoveredURL) -> bool:
    return str(item.metadata.get("purpose", "")) == "native_source_scan"


def _selection(item: DiscoveredURL) -> dict[str, Any]:
    return item.metadata.setdefault("selection", {})


def _discovery_hard_reject_reason(item: DiscoveredURL) -> str:
    reason = discovery_reject_reason(item.url, item.title, item.description)
    if not reason:
        return ""
    if reason in DISCOVERY_HARD_REJECT_REASONS:
        return reason
    _selection(item)["discovery_quality_deferred_reason"] = reason
    _selection(item)["discovery_quality_decision"] = "defer_until_body_extraction"
    return ""


def _annotate(candidate: Candidate) -> None:
    _selection(candidate.item).update(
        {
            "version": SELECTION_VERSION,
            "selection_bucket": candidate.bucket,
            "selection_group": candidate.group_key,
            "ranking_score_total": sum(candidate.score_components.values()),
            "page_type_score": (
                candidate.score_components["quality"]
                + candidate.score_components["article_confidence"]
            ),
            "freshness_score": candidate.score_components["freshness_ordinal"],
            "depth_score": candidate.score_components["depth"],
            "source_quality_score": 2 if candidate.bucket == "native" else 0,
            "score_components": candidate.score_components,
        }
    )


def _mark_reserve(candidate: Candidate, status: str, *, rank: int | None = None) -> None:
    selection = _selection(candidate.item)
    if selection.get("selected_order"):
        return
    selection["selection_status"] = status
    selection["reserve_reason"] = status
    if rank is not None:
        selection["reserve_rank"] = rank


def _mark_selected(
    candidate: Candidate,
    *,
    accepted: list[Candidate],
    host_counts: Counter[str],
    phase: str,
    backfill: bool = False,
) -> bool:
    selection = _selection(candidate.item)
    if selection.get("selected_order"):
        return False
    if host_counts[candidate.domain] >= ABSOLUTE_HOST_CAP:
        _mark_reserve(candidate, "absolute_host_reserve", rank=candidate.group_rank)
        return False
    accepted.append(candidate)
    host_counts[candidate.domain] += 1
    selection.pop("reserve_reason", None)
    selection.pop("reserve_rank", None)
    selection["selection_status"] = "selected"
    selection["selected_order"] = len(accepted)
    selection["selection_phase"] = phase
    selection["source_or_domain_rank"] = candidate.group_rank
    if backfill:
        selection["capacity_backfill"] = True
    return True


def _prepare_groups(
    groups: OrderedDict[str, list[Candidate]],
) -> list[tuple[str, list[Candidate], list[Candidate]]]:
    """Return (group, initially eligible, overflow reserve) in score order."""
    prepared: list[tuple[str, list[Candidate], list[Candidate]]] = []
    for group_key, candidates in groups.items():
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        for index, candidate in enumerate(candidates, start=1):
            candidate.group_rank = index
            _selection(candidate.item)["source_or_domain_rank"] = index
        cap = candidates[0].group_cap
        eligible = candidates[:cap]
        overflow = candidates[cap:]
        overflow_status = (
            "source_initial_cap_reserve"
            if candidates[0].bucket == "native"
            else "domain_initial_cap_reserve"
        )
        for reserve_rank, candidate in enumerate(overflow, start=1):
            _mark_reserve(candidate, overflow_status, rank=reserve_rank)
        prepared.append((group_key, eligible, overflow))
    prepared.sort(
        key=lambda entry: entry[1][0].score if entry[1] else tuple(),
        reverse=True,
    )
    return prepared


def _round_robin_select(
    groups: list[tuple[str, list[Candidate], list[Candidate]]],
    *,
    accepted: list[Candidate],
    host_counts: Counter[str],
    target_total: int,
    max_rounds: int,
    phase_prefix: str,
    backfill_after_round: int | None = None,
) -> None:
    for round_index in range(max_rounds):
        if len(accepted) >= target_total:
            break
        for _, eligible, _ in groups:
            if len(accepted) >= target_total:
                break
            if round_index >= len(eligible):
                continue
            candidate = eligible[round_index]
            _mark_selected(
                candidate,
                accepted=accepted,
                host_counts=host_counts,
                phase=f"{phase_prefix}_{round_index + 1}",
                backfill=(
                    backfill_after_round is not None
                    and round_index + 1 > backfill_after_round
                ),
            )


def _remaining_eligible(
    groups: list[tuple[str, list[Candidate], list[Candidate]]],
) -> list[Candidate]:
    remaining = [
        candidate
        for _, eligible, _ in groups
        for candidate in eligible
        if not _selection(candidate.item).get("selected_order")
    ]
    remaining.sort(key=lambda candidate: candidate.score, reverse=True)
    return remaining


def _score_backfill(
    candidates: list[Candidate],
    *,
    accepted: list[Candidate],
    host_counts: Counter[str],
    target_total: int,
    phase: str,
) -> None:
    for candidate in candidates:
        if len(accepted) >= target_total:
            break
        _mark_selected(
            candidate,
            accepted=accepted,
            host_counts=host_counts,
            phase=phase,
            backfill=True,
        )


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Build a native-first 16/16 portfolio and preserve overflow as reserve.

    The function never selects more than ``max_urls`` and never treats a source
    or bucket capacity decision as a deterministic page rejection.
    """
    max_urls = max(0, int(max_urls))
    open_cap = max(1, int(max_per_domain))
    rejected: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    native_groups: OrderedDict[str, list[Candidate]] = OrderedDict()
    open_groups: OrderedDict[str, list[Candidate]] = OrderedDict()

    for original_index, item in enumerate(discovered):
        canonical = canonicalize_url(item.url)
        if canonical in seen_urls:
            _selection(item).update(
                {
                    "version": SELECTION_VERSION,
                    "selection_status": "page_gate_reject",
                    "capacity_bucket_reject_reason": "duplicate_url",
                }
            )
            rejected.append({"url": item.url, "reason": "duplicate_url"})
            continue
        seen_urls.add(canonical)

        reason = _discovery_hard_reject_reason(item)
        if reason:
            _selection(item).update(
                {
                    "version": SELECTION_VERSION,
                    "selection_status": "page_gate_reject",
                    "capacity_bucket_reject_reason": reason,
                }
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
        candidate = Candidate(
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
        target = native_groups if native else open_groups
        target.setdefault(group_key, []).append(candidate)

    native_prepared = _prepare_groups(native_groups)
    open_prepared = _prepare_groups(open_groups)
    accepted: list[Candidate] = []
    host_counts: Counter[str] = Counter()

    # Native gets its full soft target first: rounds 1–2 ensure diversity, then
    # rounds 3–4 use source reserve before any open-search overflow.
    native_target = min(max_urls, NATIVE_BUCKET_TARGET)
    _round_robin_select(
        native_prepared,
        accepted=accepted,
        host_counts=host_counts,
        target_total=native_target,
        max_rounds=NATIVE_SOURCE_CAP,
        phase_prefix="native_round",
        backfill_after_round=2,
    )

    # Open search receives its own soft target with a two-per-domain ceiling.
    open_target_total = min(max_urls, len(accepted) + OPEN_BUCKET_TARGET)
    _round_robin_select(
        open_prepared,
        accepted=accepted,
        host_counts=host_counts,
        target_total=open_target_total,
        max_rounds=open_cap,
        phase_prefix="open_round",
    )

    # Return unused bucket capacity, preferring remaining native metadata before
    # allowing open search to overflow its 16-item target.
    if len(accepted) < max_urls:
        _score_backfill(
            _remaining_eligible(native_prepared),
            accepted=accepted,
            host_counts=host_counts,
            target_total=max_urls,
            phase="native_cross_bucket_backfill",
        )
    if len(accepted) < max_urls:
        _score_backfill(
            _remaining_eligible(open_prepared),
            accepted=accepted,
            host_counts=host_counts,
            target_total=max_urls,
            phase="open_cross_bucket_backfill",
        )

    selected_urls = {candidate.canonical_url for candidate in accepted}
    for prepared in (native_prepared, open_prepared):
        for _, eligible, overflow in prepared:
            for reserve_rank, candidate in enumerate(eligible, start=1):
                if candidate.canonical_url in selected_urls:
                    continue
                selection = _selection(candidate.item)
                if selection.get("selection_status") == "absolute_host_reserve":
                    continue
                _mark_reserve(
                    candidate,
                    "bucket_capacity_reserve",
                    rank=reserve_rank,
                )
            for candidate in overflow:
                # Source/domain overflow status was assigned by _prepare_groups.
                if candidate.canonical_url not in selected_urls:
                    _selection(candidate.item).setdefault(
                        "selection_status", "final_not_selected"
                    )

    # Audit invariant: selected order is contiguous and extraction attempts stay
    # bounded by max_urls. Reserve items are not returned as rejected pages.
    for order, candidate in enumerate(accepted, start=1):
        _selection(candidate.item)["selected_order"] = order
    return [candidate.item for candidate in accepted], rejected


__all__ = [
    "ABSOLUTE_HOST_CAP",
    "DISCOVERY_HARD_REJECT_REASONS",
    "NATIVE_BUCKET_TARGET",
    "NATIVE_SOURCE_CAP",
    "OPEN_BUCKET_TARGET",
    "OPEN_DOMAIN_CAP",
    "RESERVE_STATUSES",
    "SELECTION_VERSION",
    "filter_discovered",
]
