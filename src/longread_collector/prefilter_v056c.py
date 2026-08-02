"""PR-C prefilter: page-role and freshness gates before reserve allocation."""

from __future__ import annotations

from .freshness_policy_v056 import (
    FRESHNESS_POLICY_VERSION,
    evaluate_freshness_policy,
)
from .models import DiscoveredURL
from .page_gate_policy_v056 import (
    PAGE_GATE_POLICY_VERSION,
    evaluate_page_gate_policy,
)
from .ranked_selection_plan_v056 import (
    filter_discovered as _reserve_filter_discovered,
)
from .ranked_selection_v056c import SELECTION_VERSION as RANKING_FRESHNESS_VERSION

PREFILTER_VERSION = "page-freshness-prefilter-v0.5.6c"


def _reject(
    item: DiscoveredURL,
    *,
    reason: str,
    gate: str,
) -> dict[str, str]:
    item.metadata.setdefault("selection", {}).update(
        {
            "prefilter_version": PREFILTER_VERSION,
            "selection_status": (
                "page_gate_reject" if gate == "page" else "freshness_gate_reject"
            ),
            "capacity_bucket_reject_reason": reason,
            "deterministic_page_gate": reason if gate == "page" else "",
            "freshness_gate": reason if gate == "freshness" else "",
        }
    )
    return {"url": item.url, "reason": reason}


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    candidates: list[DiscoveredURL] = []
    rejected: list[dict[str, str]] = []

    for item in discovered:
        page = evaluate_page_gate_policy(item)
        if page.rejected:
            rejected.append(_reject(item, reason=page.reject_reason, gate="page"))
            continue

        freshness = evaluate_freshness_policy(item, phase="prefilter")
        if not freshness.allowed:
            rejected.append(
                _reject(item, reason=freshness.reject_reason, gate="freshness")
            )
            continue
        item.metadata.setdefault("selection", {}).update(
            {
                "prefilter_version": PREFILTER_VERSION,
                "page_gate_policy_version": PAGE_GATE_POLICY_VERSION,
                "freshness_policy_version": FRESHNESS_POLICY_VERSION,
                "ranking_freshness_version": RANKING_FRESHNESS_VERSION,
            }
        )
        candidates.append(item)

    accepted, ranked_rejected = _reserve_filter_discovered(
        candidates,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )
    return accepted, rejected + ranked_rejected


__all__ = ["PREFILTER_VERSION", "filter_discovered"]
