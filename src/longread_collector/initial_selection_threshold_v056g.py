"""Apply a soft editorial-confidence threshold to the initial Top 32.

Candidates below the threshold remain fully auditable reserves.  Vacated slots
are backfilled from higher-scoring capacity reserves while preserving the
existing source/domain/host caps.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url
from .ranked_selection_v056 import (
    ABSOLUTE_HOST_CAP,
    NATIVE_SOURCE_CAP,
    OPEN_DOMAIN_CAP,
)

INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY = 46
_BACKFILL_STATUSES = {
    "bucket_capacity_reserve",
    "source_initial_cap_reserve",
    "domain_initial_cap_reserve",
    "final_not_selected",
    "editorial_priority_reserve",
}


def _selection(item: DiscoveredURL) -> dict[str, Any]:
    return item.metadata.setdefault("selection", {})


def _priority(item: DiscoveredURL) -> int:
    return int(
        _selection(item).get("score_components", {}).get(
            "editorial_priority", 0
        )
    )


def _score(item: DiscoveredURL) -> tuple[int, ...]:
    components = _selection(item).get("score_components", {})
    return (
        int(components.get("editorial_priority", 0)),
        int(components.get("quality", 0)),
        int(components.get("freshness_ordinal", 0)),
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        int(components.get("rank_score", 0)),
    )


def _group(item: DiscoveredURL) -> str:
    return str(_selection(item).get("selection_group", ""))


def _group_cap(item: DiscoveredURL) -> int:
    return (
        NATIVE_SOURCE_CAP
        if _selection(item).get("selection_bucket") == "native"
        else OPEN_DOMAIN_CAP
    )


def apply_initial_selection_threshold(
    *,
    discovered: list[DiscoveredURL],
    selected: list[DiscoveredURL],
    max_urls: int,
) -> list[DiscoveredURL]:
    retained: list[DiscoveredURL] = []
    for item in selected:
        selection = _selection(item)
        selection["initial_selection_min_editorial_priority"] = (
            INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY
        )
        if _priority(item) >= INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY:
            retained.append(item)
            continue
        selection.pop("selected_order", None)
        selection["selection_status"] = "editorial_priority_reserve"
        selection["reserve_reason"] = "below_initial_editorial_priority"
        selection["initial_selection_threshold_delta"] = (
            _priority(item) - INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY
        )

    retained_urls = {canonicalize_url(item.url) for item in retained}
    group_counts: Counter[str] = Counter(_group(item) for item in retained)
    host_counts: Counter[str] = Counter(domain_from_url(item.url) for item in retained)
    backfill = [
        item
        for item in discovered
        if canonicalize_url(item.url) not in retained_urls
        and not bool(_selection(item).get("selection_force_reserve_only"))
        and str(_selection(item).get("selection_status", "")) in _BACKFILL_STATUSES
        and _priority(item) >= INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY
    ]
    backfill.sort(key=_score, reverse=True)

    for item in backfill:
        if len(retained) >= max(0, int(max_urls)):
            break
        group = _group(item)
        host = domain_from_url(item.url)
        if group_counts[group] >= _group_cap(item):
            continue
        if host_counts[host] >= ABSOLUTE_HOST_CAP:
            continue
        retained.append(item)
        retained_urls.add(canonicalize_url(item.url))
        group_counts[group] += 1
        host_counts[host] += 1
        selection = _selection(item)
        selection.pop("reserve_reason", None)
        selection.pop("reserve_rank", None)
        selection["selection_status"] = "selected"
        selection["selection_phase"] = "editorial_threshold_backfill"
        selection["capacity_backfill"] = True
        selection["initial_selection_min_editorial_priority"] = (
            INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY
        )

    retained.sort(key=_score, reverse=True)
    for order, item in enumerate(retained, start=1):
        _selection(item)["selected_order"] = order
    return retained


__all__ = [
    "INITIAL_SELECTION_MIN_EDITORIAL_PRIORITY",
    "apply_initial_selection_threshold",
]
