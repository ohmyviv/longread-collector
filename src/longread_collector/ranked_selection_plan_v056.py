"""Publish v0.5.6 ranked reserve metadata for bounded staged extraction."""

from __future__ import annotations

from .models import DiscoveredURL
from .ranked_selection_v056 import (
    OPEN_DOMAIN_CAP,
    filter_discovered as _ranked_filter_discovered,
)
from .selection_plan_v056 import publish_selection_plan


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    accepted, rejected = _ranked_filter_discovered(
        discovered,
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
