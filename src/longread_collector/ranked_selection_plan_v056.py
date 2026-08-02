"""Publish v0.5.6 ranked reserve metadata for bounded staged extraction."""

from __future__ import annotations

from . import ranked_freshness_v056 as _ranked_freshness
from . import ranked_selection_v056 as _ranked
from .models import DiscoveredURL
from .normalization import domain_from_url
from .ranked_selection_v056 import (
    OPEN_DOMAIN_CAP,
    SELECTION_VERSION,
    filter_discovered as _ranked_filter_discovered,
)
from .selection_plan_v056 import publish_selection_plan

# Install the resolved-publication score adapter while preserving the validated
# PR-B reserve allocator.
_ranked_freshness.install_ranked_freshness()


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
            "ranking_score_total": sum(components.values()),
            "score_components": components,
            "page_type_score": (
                components.get("quality", 0)
                + components.get("article_confidence", 0)
            ),
            "freshness_score": components.get("freshness_ordinal", 0),
            "depth_score": components.get("depth", 0),
            "source_quality_score": 2 if native else 0,
            "selection_force_reserve_only": True,
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
    publish_selection_plan(
        max_urls=max_urls,
        selected=accepted,
        discovered=discovered,
    )
    return accepted, rejected


__all__ = ["filter_discovered"]
