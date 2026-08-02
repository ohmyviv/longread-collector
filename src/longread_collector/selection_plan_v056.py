"""Per-filter reserve plan shared by v0.5.6 selection and extraction stages."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from .models import DiscoveredURL
from .normalization import canonicalize_url

_RESERVE_STATUSES = {
    "source_initial_cap_reserve",
    "domain_initial_cap_reserve",
    "bucket_capacity_reserve",
    "absolute_host_reserve",
    "final_not_selected",
    "evidence_reserve_only",
}


@dataclass(slots=True)
class SelectionReservePlan:
    max_urls: int
    selected: list[DiscoveredURL]
    reserves: list[DiscoveredURL]


_PLAN: ContextVar[SelectionReservePlan | None] = ContextVar(
    "selection_reserve_plan_v056", default=None
)


def _score_key(item: DiscoveredURL) -> tuple[Any, ...]:
    """Order reserves by editorial utility; native provenance is only a tie-break."""
    selection = item.metadata.get("selection", {})
    components = selection.get("score_components", {})
    bucket = str(selection.get("selection_bucket", "open"))
    return (
        int(components.get("editorial_priority", 0)),
        int(components.get("quality", 0)),
        int(components.get("freshness_ordinal", 0)),
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        1 if bucket == "native" else 0,
        int(components.get("rank_score", 0)),
    )


def publish_selection_plan(
    *,
    max_urls: int,
    selected: list[DiscoveredURL],
    discovered: list[DiscoveredURL],
) -> SelectionReservePlan:
    selected_urls = {canonicalize_url(item.url) for item in selected}
    reserves = [
        item
        for item in discovered
        if canonicalize_url(item.url) not in selected_urls
        and str(item.metadata.get("selection", {}).get("selection_status", ""))
        in _RESERVE_STATUSES
    ]
    reserves.sort(key=_score_key, reverse=True)
    for index, item in enumerate(reserves, start=1):
        item.metadata.setdefault("selection", {})["global_reserve_rank"] = index
    plan = SelectionReservePlan(
        max_urls=max(0, int(max_urls)),
        selected=list(selected),
        reserves=reserves,
    )
    _PLAN.set(plan)
    return plan


def current_selection_plan() -> SelectionReservePlan | None:
    return _PLAN.get()


def clear_selection_plan() -> None:
    _PLAN.set(None)


__all__ = [
    "SelectionReservePlan",
    "clear_selection_plan",
    "current_selection_plan",
    "publish_selection_plan",
]
