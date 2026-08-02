"""Source-specific route contracts for v0.5.6 PR-A.

The base layer provides route auditing and multi-route discovery. This layer
activates bounded, source-specific route depth only while the v0.5.6 discovery
class is running, so v0.5.5 imports and regression tests remain untouched.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from . import effective_route_v056 as _base
from .native_discovery import parse_parser_config
from .normalization import canonicalize_url

_BASE_APPLY_EFFECTIVE_ROUTE_FIX = _base.apply_effective_route_fix
_BASE_ROUND_ROBIN_ITEMS = _base._round_robin_items

JIEMIAN_EFFECTIVE_ROUTES = [
    # The final-report market-infrastructure article is present on this page.
    "https://www.jiemian.com/lists/506.html",
    # The final-report JPY analysis carries the 财经速递 tag. The tag archive
    # exposes stable numbered pages, unlike the invalid list-page suffixes.
    *[f"https://www.jiemian.com/tags/712/{page}.html" for page in range(1, 9)],
    "https://www.jiemian.com/lists/174.html",
    "https://www.jiemian.com/lists/423.html",
]

BJNEWS_EFFECTIVE_ROUTES = [
    "https://www.bjnews.com.cn/depth",
    "https://www.bjnews.com.cn/news",
    "https://www.bjnews.com.cn/",
]

THEPAPER_CHANNEL_IDS = (25462, 25448)
THEPAPER_EFFECTIVE_ROUTES = [
    "https://www.thepaper.cn/list_25462",
    *[
        "https://www.thepaper.cn/load_index.jsp?"
        f"nodeids=25462&pageidx={page}&isList=true"
        for page in range(1, 9)
    ],
    "https://www.thepaper.cn/list_25448",
    *[
        "https://www.thepaper.cn/load_index.jsp?"
        f"nodeids=25448&pageidx={page}&isList=true"
        for page in range(1, 9)
    ],
]

_SOURCE_METADATA_LIMITS = {
    "jiemian-depth": 96,
    "bjnews-depth": 64,
    # Two high-volume subchannels, eight bounded archive pages each. This is
    # metadata-only discovery and does not increase the 32-body cap.
    "thepaper": 320,
}


def apply_effective_route_fix(source: dict[str, Any]) -> dict[str, Any]:
    item = _BASE_APPLY_EFFECTIVE_ROUTE_FIX(source)
    source_id = str(item.get("source_id", ""))
    config = parse_parser_config(item)

    if source_id == "jiemian-depth":
        config["section_urls"] = list(JIEMIAN_EFFECTIVE_ROUTES)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "investment|markets|macro|finance_tag|depth"
        config["aggregation_mode"] = "priority"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: validated investment list and numbered finance-tag archive"
        )
    elif source_id == "bjnews-depth":
        config["section_urls"] = list(BJNEWS_EFFECTIVE_ROUTES)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "depth|news|homepage"
        config["aggregation_mode"] = "priority"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: preserve the full depth page before general-news backfill"
        )
    elif source_id == "thepaper":
        config["section_urls"] = list(THEPAPER_EFFECTIVE_ROUTES)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "china_politics|culture_and_entertainment"
        config["aggregation_mode"] = "priority"
        config["archive_pages_per_channel"] = 8
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: official subchannels plus bounded load_index archive pages"
        )

    if source_id in _SOURCE_METADATA_LIMITS:
        config["metadata_limit"] = max(
            int(config.get("metadata_limit") or 0),
            _SOURCE_METADATA_LIMITS[source_id],
        )
    item["parser_config_json"] = config
    return item


def _source_id_from_groups(groups: list[list[Any]]) -> str:
    for group in groups:
        for item in group:
            return str(item.metadata.get("source_id", ""))
    return ""


def _priority_items(groups: list[list[Any]], *, limit: int) -> list[Any]:
    """Concatenate validated route groups in declared priority order."""
    result: list[Any] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            canonical = canonicalize_url(item.url)
            if canonical in seen:
                continue
            seen.add(canonical)
            item.rank = len(result) + 1
            result.append(item)
            if len(result) >= limit:
                return result
    return result


def merge_route_items(groups: list[list[Any]], *, limit: int) -> list[Any]:
    source_id = _source_id_from_groups(groups)
    if source_id in _SOURCE_METADATA_LIMITS:
        return _priority_items(groups, limit=limit)
    return _BASE_ROUND_ROBIN_ITEMS(groups, limit=limit)


@contextmanager
def _activated_route_contracts():
    previous_apply = _base.apply_effective_route_fix
    previous_merge = _base._round_robin_items
    _base.apply_effective_route_fix = apply_effective_route_fix
    _base._round_robin_items = merge_route_items
    try:
        yield
    finally:
        _base.apply_effective_route_fix = previous_apply
        _base._round_robin_items = previous_merge


class EffectiveRouteDiscovery(_base.EffectiveRouteDiscovery):
    """Base effective discovery with source-specific contracts scoped per call."""

    async def discover_source(self, *args, **kwargs):
        with _activated_route_contracts():
            return await super().discover_source(*args, **kwargs)

    async def discover(self, *args, **kwargs):
        with _activated_route_contracts():
            return await super().discover(*args, **kwargs)


EFFECTIVE_ROUTE_VERSION = _base.EFFECTIVE_ROUTE_VERSION
begin_effective_route_audit = _base.begin_effective_route_audit
current_effective_route_audit = _base.current_effective_route_audit
end_effective_route_audit = _base.end_effective_route_audit

__all__ = [
    "BJNEWS_EFFECTIVE_ROUTES",
    "EFFECTIVE_ROUTE_VERSION",
    "EffectiveRouteDiscovery",
    "JIEMIAN_EFFECTIVE_ROUTES",
    "THEPAPER_CHANNEL_IDS",
    "THEPAPER_EFFECTIVE_ROUTES",
    "apply_effective_route_fix",
    "begin_effective_route_audit",
    "current_effective_route_audit",
    "end_effective_route_audit",
    "merge_route_items",
]
