from __future__ import annotations

from .models import DiscoveredURL
from .prefilter_v055 import discovery_hard_gate_reason
from .ranked_selection_plan_v056 import (
    filter_discovered as _reserve_filter_discovered,
)

PREFILTER_VERSION = "deterministic-prefilter-v0.5.6"


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Apply deterministic page gates, then preserve capacity overflow as reserve."""
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
                "selection_status": "page_gate_reject",
                "capacity_bucket_reject_reason": reason,
            }
        )
        hard_rejected.append({"url": item.url, "reason": reason})

    accepted, ranked_rejected = _reserve_filter_discovered(
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
