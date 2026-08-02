"""Publish v0.5.6 ranked reserve metadata for bounded staged extraction."""

from __future__ import annotations

from . import ranked_freshness_v056 as _ranked_freshness
from . import ranked_selection_v056 as _ranked
from .initial_selection_threshold_v056g import apply_initial_selection_threshold
from .models import DiscoveredURL
from .normalization import domain_from_url
from .ranked_selection_v056 import (
    OPEN_DOMAIN_CAP,
    SELECTION_VERSION,
    filter_discovered as _ranked_filter_discovered,
)
from .selection_plan_v056 import publish_selection_plan

# Install the resolved-publication and editorial score adapter while preserving
# the reserve allocator's hard source/domain/host caps.
_ranked_freshness.install_ranked_freshness()


def _unknown_native_search_fallback(item: DiscoveredURL) -> bool:
    if str(item.metadata.get("purpose", "")) != "native_source_scan":
        return False
    method = str(item.discovery_method or "").strip().lower()
    native_method = str(item.metadata.get("native_method", "")).strip().lower()
    if method != "firecrawl_search" and native_method != "firecrawl_search":
        return False
    if str(item.published_at or "").strip():
        return False
    freshness = item.metadata.get("freshness", {})
    if freshness.get("published_at_resolved"):
        return False
    return bool(
        freshness.get("native_search_fallback")
        or freshness.get("freshness_unknown")
        or freshness.get("unknown_date_policy")
    )


def _force_low_trust_fallback_reserve(item: DiscoveredURL) -> None:
    if not _unknown_native_search_fallback(item):
        return
    selection = item.metadata.setdefault("selection", {})
    selection.update(
        {
            "selection_force_reserve_only": True,
            "reserve_only_reason": "unknown_native_search_fallback",
            "initial_trust_boundary": "reserve_pending_body_date_and_quality",
        }
    )


def _annotate_forced_reserve(item: DiscoveredURL, original_index: int) -> None:
    score, components = _ranked._score(item, original_index)
    native = str(item.metadata.get("purpose", "")) == "native_source_scan"
    source_id = str(item.metadata.get("source_id", "")).strip()
    domain = domain_from_url(item.url)
    selection = item.metadata.setdefault("selection", {})
    selection.update(
        {
            "version": SELECTION_VERSION,
            "selection_status": "evidence_reserve_only",
            "reserve_reason": str(
                selection.get("reserve_only_reason")
                or "evidence_requires_post_extraction_verification"
            ),
            "selection_bucket": "native" if native else "open",
            "selection_group": (
                f"source:{source_id or domain}" if native else f"domain:{domain}"
            ),
            "ranking_score_total": int(
                components.get("editorial_priority", sum(components.values()))
            ),
            "editorial_priority_score": int(
                components.get("editorial_priority", 0)
            ),
            "score_components": components,
            "page_type_score": (
                components.get("quality", 0)
                + components.get("article_confidence", 0)
            ),
            "freshness_score": components.get("freshness_ordinal", 0),
            "depth_score": components.get("depth", 0),
            "source_quality_score": components.get(
                "native_signal", 2 if native else 0
            ),
            "selection_force_reserve_only": True,
            "forced_reserve_score": list(score),
        }
    )


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    selectable: list[DiscoveredURL] = []
    for original_index, item in enumerate(discovered):
        _force_low_trust_fallback_reserve(item)
        if bool(
            item.metadata.get("selection", {}).get("selection_force_reserve_only")
        ):
            _annotate_forced_reserve(item, original_index)
        else:
            selectable.append(item)

    accepted, rejected = _ranked_filter_discovered(
        selectable,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )
    accepted = apply_initial_selection_threshold(
        discovered=discovered,
        selected=accepted,
        max_urls=max_urls,
    )
    publish_selection_plan(
        max_urls=max_urls,
        selected=accepted,
        discovered=discovered,
    )
    return accepted, rejected


__all__ = ["filter_discovered"]
