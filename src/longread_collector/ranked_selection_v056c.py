"""Freshness-aware score adapter for the validated v0.5.6 reserve selector."""

from __future__ import annotations

from typing import Any

from . import ranked_selection_v056 as _base
from .models import DiscoveredURL
from .ranked_selection_v055 import _score as _legacy_score

SELECTION_VERSION = "ranked-reserve-freshness-v0.5.6c"

ABSOLUTE_HOST_CAP = _base.ABSOLUTE_HOST_CAP
NATIVE_BUCKET_TARGET = _base.NATIVE_BUCKET_TARGET
NATIVE_SOURCE_CAP = _base.NATIVE_SOURCE_CAP
OPEN_BUCKET_TARGET = _base.OPEN_BUCKET_TARGET
OPEN_DOMAIN_CAP = _base.OPEN_DOMAIN_CAP
RESERVE_STATUSES = _base.RESERVE_STATUSES


def _freshness_score(
    item: DiscoveredURL,
    original_index: int,
) -> tuple[tuple[int, ...], dict[str, int]]:
    _, components = _legacy_score(item, original_index)
    freshness = item.metadata.get("freshness", {})
    resolved_ordinal = int(freshness.get("freshness_score_ordinal", 0) or 0)
    penalty = int(freshness.get("freshness_score_penalty", 0) or 0)

    components["freshness_ordinal"] = resolved_ordinal
    components["freshness_penalty"] = penalty
    # Put the auditable freshness penalty next to quality so unknown-date open
    # pages cannot outrank equally strong candidates with verified dates.
    adjusted_quality = int(components.get("quality", 0)) + penalty
    components["quality"] = adjusted_quality
    return (
        adjusted_quality,
        int(components.get("article_confidence", 0)),
        int(components.get("depth", 0)),
        resolved_ordinal,
        int(components.get("title_richness", 0)),
        int(components.get("description_richness", 0)),
        int(components.get("rank_score", 0)),
    ), components


# The validated selector resolves its score function from module globals at
# runtime. Install only the score adapter; all reserve/cap logic remains in the
# PR-B implementation.
_base._score = _freshness_score
_base.SELECTION_VERSION = SELECTION_VERSION


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
):
    return _base.filter_discovered(
        discovered,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )


__all__ = [
    "ABSOLUTE_HOST_CAP",
    "NATIVE_BUCKET_TARGET",
    "NATIVE_SOURCE_CAP",
    "OPEN_BUCKET_TARGET",
    "OPEN_DOMAIN_CAP",
    "RESERVE_STATUSES",
    "SELECTION_VERSION",
    "filter_discovered",
]
