from __future__ import annotations

from .freshness_v056 import FRESHNESS_VERSION, evaluate_freshness
from .models import DiscoveredURL
from .page_gates_v056 import (
    PAGE_GATE_VERSION,
    annotate_page_gate,
    evaluate_page_gate,
)
from .ranked_selection_plan_v056 import (
    filter_discovered as _reserve_filter_discovered,
)

PREFILTER_VERSION = "deterministic-prefilter-v0.5.6c"


def discovery_hard_gate_reason(item: DiscoveredURL) -> str:
    """Compatibility helper for deterministic page-type gates only."""
    return evaluate_page_gate(item).reject_reason


def _reject(
    item: DiscoveredURL,
    *,
    reason: str,
    page_type: str,
) -> dict[str, str]:
    freshness = item.metadata.get("freshness", {})
    item.metadata.setdefault("selection", {}).update(
        {
            "prefilter_version": PREFILTER_VERSION,
            "page_gate_version": PAGE_GATE_VERSION,
            "freshness_version": FRESHNESS_VERSION,
            "deterministic_page_gate": reason,
            "page_type": page_type,
            "selection_status": "page_gate_reject",
            "capacity_bucket_reject_reason": reason,
            "freshness_track": freshness.get("freshness_track", ""),
            "freshness_age_days": freshness.get("freshness_age_days"),
            "published_at_source": freshness.get("published_at_source", "unknown"),
        }
    )
    return {"url": item.url, "reason": reason}


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Apply general page gates and freshness policy before reserve selection."""
    candidates: list[DiscoveredURL] = []
    hard_rejected: list[dict[str, str]] = []
    for item in discovered:
        page_decision = evaluate_page_gate(item)
        annotate_page_gate(item, page_decision)
        if page_decision.rejected:
            hard_rejected.append(
                _reject(
                    item,
                    reason=page_decision.reject_reason,
                    page_type=page_decision.page_type,
                )
            )
            continue

        freshness_decision = evaluate_freshness(item)
        freshness = item.metadata.get("freshness", {})
        item.metadata.setdefault("selection", {}).update(
            {
                "prefilter_version": PREFILTER_VERSION,
                "page_gate_version": PAGE_GATE_VERSION,
                "freshness_version": FRESHNESS_VERSION,
                "page_type": page_decision.page_type,
                "freshness_track": freshness_decision.track,
                "freshness_age_days": freshness_decision.age_days,
                "freshness_unknown": freshness_decision.unknown,
                "freshness_exception_reason": freshness_decision.exception_reason,
                "published_at_resolved": freshness.get("published_at_resolved", ""),
                "published_at_source": freshness.get("published_at_source", "unknown"),
                "published_at_confidence": freshness.get(
                    "published_at_confidence", "unknown"
                ),
                "date_conflict_reason": freshness.get("date_conflict_reason", ""),
            }
        )
        if not freshness_decision.allowed:
            hard_rejected.append(
                _reject(
                    item,
                    reason=freshness_decision.reject_reason,
                    page_type=page_decision.page_type,
                )
            )
            continue
        candidates.append(item)

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
