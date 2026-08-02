"""PR-C prefilter: page-role and freshness gates before reserve allocation."""

from __future__ import annotations

from .freshness_policy_v056f import (
    FRESHNESS_POLICY_VERSION,
    evaluate_freshness_policy,
)
from .models import DiscoveredURL
from .page_gate_policy_v056 import (
    PAGE_GATE_POLICY_VERSION,
    evaluate_page_gate_policy,
)
from .ranked_freshness_v056 import RANKING_FRESHNESS_VERSION
from .ranked_selection_plan_v056 import (
    filter_discovered as _reserve_filter_discovered,
)

PREFILTER_VERSION = "page-freshness-prefilter-v0.5.6f"


def _reject(
    item: DiscoveredURL,
    *,
    reason: str,
    gate: str,
) -> dict[str, str]:
    freshness = item.metadata.get("freshness", {})
    page_gate = item.metadata.get("page_gate", {})
    item.metadata.setdefault("selection", {}).update(
        {
            "prefilter_version": PREFILTER_VERSION,
            "page_gate_policy_version": PAGE_GATE_POLICY_VERSION,
            "freshness_policy_version": FRESHNESS_POLICY_VERSION,
            "ranking_freshness_version": RANKING_FRESHNESS_VERSION,
            "selection_status": (
                "page_gate_reject" if gate == "page" else "freshness_gate_reject"
            ),
            "capacity_bucket_reject_reason": reason,
            "deterministic_page_gate": reason if gate == "page" else "",
            "freshness_gate": reason if gate == "freshness" else "",
            "page_type": page_gate.get("page_type", ""),
            "published_at_resolved": freshness.get("published_at_resolved", ""),
            "published_at_source": freshness.get("published_at_source", "unknown"),
            "published_at_confidence": freshness.get(
                "published_at_confidence", "unknown"
            ),
            "freshness_track": freshness.get("freshness_track", ""),
            "freshness_age_days": freshness.get("freshness_age_days"),
            "date_conflict_reason": freshness.get("date_conflict_reason", ""),
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
        evidence = item.metadata.get("freshness", {})
        item.metadata.setdefault("selection", {}).update(
            {
                "prefilter_version": PREFILTER_VERSION,
                "page_gate_policy_version": PAGE_GATE_POLICY_VERSION,
                "freshness_policy_version": FRESHNESS_POLICY_VERSION,
                "ranking_freshness_version": RANKING_FRESHNESS_VERSION,
                "page_type": item.metadata.get("page_gate", {}).get(
                    "page_type", "article_or_document"
                ),
                "published_at_resolved": evidence.get("published_at_resolved", ""),
                "published_at_source": evidence.get("published_at_source", "unknown"),
                "published_at_confidence": evidence.get(
                    "published_at_confidence", "unknown"
                ),
                "freshness_track": freshness.track,
                "freshness_age_days": freshness.age_days,
                "freshness_unknown": freshness.unknown,
                "freshness_exception_reason": freshness.exception_reason,
                "date_conflict_reason": evidence.get("date_conflict_reason", ""),
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
