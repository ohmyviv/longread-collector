"""Source-specific route contracts for v0.5.6 PR-A.

The base layer provides route auditing and multi-route discovery. This layer
activates bounded, source-specific route depth only while the v0.5.6 discovery
class is running, so v0.5.5 imports and regression tests remain untouched.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from . import effective_route_v056 as _base
from .native_discovery import NativeDiscoveryLog, parse_parser_config
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
BJNEWS_NEWS_PAGES = [
    "https://www.bjnews.com.cn/news",
    *[f"https://www.bjnews.com.cn/news/{page}.html" for page in range(2, 65)],
]
BJNEWS_DETAIL_TIMESTAMP_RE = re.compile(r"detail[-/](\d{13})\d*")
BJNEWS_DEPTH_TITLE_RE = re.compile(
    r"调查|暗访|起底|专访|深度|追踪|复盘|观察|人物|故事|逝者|剥洋葱|"
    r"重建现场|报告|何以|为什么|真相|困境|争议|内幕|生死|十年|多年"
)

# The old load_index.jsp endpoint was verified as 404 during the PR smoke. Keep
# only currently valid official list pages until a reproducible modern paging
# contract is identified.
THEPAPER_CHANNEL_IDS = (25462, 25448)
THEPAPER_EFFECTIVE_ROUTES = [
    "https://www.thepaper.cn/list_25462",
    "https://www.thepaper.cn/list_25448",
]

_SOURCE_METADATA_LIMITS = {
    "jiemian-depth": 96,
    "bjnews-depth": 64,
    "thepaper": 48,
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
        config["route_scope"] = "depth|news_paginated|homepage"
        config["aggregation_mode"] = "priority"
        config["news_pages_scanned"] = len(BJNEWS_NEWS_PAGES)
        config["depth_title_filter"] = BJNEWS_DEPTH_TITLE_RE.pattern
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: bounded official news pagination with URL-timestamp lookback"
        )
    elif source_id == "thepaper":
        config["section_urls"] = list(THEPAPER_EFFECTIVE_ROUTES)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "china_politics|culture_and_entertainment"
        config["aggregation_mode"] = "priority"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: current official subchannels; obsolete load_index removed"
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


def _bjnews_published_at(url: str) -> datetime | None:
    match = BJNEWS_DETAIL_TIMESTAMP_RE.search(url)
    if not match:
        return None
    try:
        timestamp = int(match.group(1)) / 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            ZoneInfo("Asia/Shanghai")
        )
    except (OverflowError, OSError, ValueError):
        return None


async def _discover_bjnews(
    discovery: "EffectiveRouteDiscovery",
    client: httpx.AsyncClient,
    source: dict[str, Any],
    *,
    limit: int,
    started: datetime,
    freshness_days: int,
) -> tuple[list[Any], NativeDiscoveryLog]:
    """Scan official pagination, then retain only seven-day deep-read metadata."""
    source = apply_effective_route_fix(source)
    attempts: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(discovery.concurrency)

    async def fetch(endpoint: str):
        attempt: dict[str, Any] = {"method": "section_scan", "endpoint": endpoint}
        try:
            async with semaphore:
                response = await discovery._get(client, endpoint)
            parsed = _base.parse_section_html_v056(
                response.text,
                source=source,
                endpoint=endpoint,
                limit=40,
            )
            attempt.update(
                {
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "results_count": len(parsed),
                }
            )
            return endpoint, parsed, attempt
        except Exception as exc:
            attempt.update(
                {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                }
            )
            return endpoint, [], attempt

    endpoints = ["https://www.bjnews.com.cn/depth", *BJNEWS_NEWS_PAGES]
    results = await asyncio.gather(*(fetch(endpoint) for endpoint in endpoints))
    groups: list[list[Any]] = []
    successful_endpoints: list[str] = []
    started_bj = started.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    cutoff_timestamp = started_bj.timestamp() - max(freshness_days, 7) * 86400

    for endpoint, parsed, attempt in results:
        attempts.append(attempt)
        filtered: list[Any] = []
        for item in parsed:
            published = _bjnews_published_at(item.url)
            if published is None or published.timestamp() < cutoff_timestamp:
                continue
            # The dedicated depth page is already curated. General news pages
            # retain only titles with long-read/editorial-depth evidence.
            if endpoint != "https://www.bjnews.com.cn/depth" and not BJNEWS_DEPTH_TITLE_RE.search(
                item.title
            ):
                continue
            item.published_at = published.isoformat(sep=" ")
            item.metadata.update(
                {
                    "published_at_source": "bjnews_url_epoch_ms",
                    "published_at_confidence": "high",
                    "source_page": endpoint,
                }
            )
            filtered.append(item)
        if filtered:
            groups.append(filtered)
            successful_endpoints.append(endpoint)

    metadata_limit = max(limit, _SOURCE_METADATA_LIMITS["bjnews-depth"])
    items = _priority_items(groups, limit=metadata_limit)
    metrics = _base._route_metrics(items, started=started, method="section_scan_paginated")
    for item in items:
        item.metadata.update(
            {
                "effective_route_version": _base.EFFECTIVE_ROUTE_VERSION,
                "route_type": "section_scan_paginated",
                "items_seen": len(items),
                "oldest_item_at": metrics["oldest_item_at"],
                "effective_lookback_hours": metrics["effective_lookback_hours"],
                "sections_covered": successful_endpoints,
                "route_scope": "depth|news_paginated",
                "native_route_status": metrics["native_route_status"],
                "effective_native_success": metrics["effective_native_success"],
                "fallback_used": False,
                "configured_lookback_days": max(freshness_days, 7),
                "metadata_limit": metadata_limit,
            }
        )

    return items, NativeDiscoveryLog(
        source_id="bjnews-depth",
        source_name=str(source.get("source_name", "新京报·深度")),
        success=bool(items),
        selected_method="section_scan_paginated" if items else "",
        selected_endpoint="|".join(successful_endpoints),
        results_count=len(items),
        fallback_needed=not bool(items),
        attempts=attempts,
        error_type="" if items else "NoNativeResults",
        error_message="" if items else "No seven-day deep-read items found",
    )


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

    async def discover_source(self, client, source, **kwargs):
        if str(source.get("source_id", "")) == "bjnews-depth":
            return await _discover_bjnews(self, client, source, **kwargs)
        with _activated_route_contracts():
            return await super().discover_source(client, source, **kwargs)

    async def discover(self, sources, **kwargs):
        with _activated_route_contracts():
            batch = await super().discover(sources, **kwargs)

        # Preserve per-source route limits instead of overwriting every log with
        # the global call's 24-item minimum.
        config_by_id = {
            str(source.get("source_id", "")): parse_parser_config(
                apply_effective_route_fix(source)
            )
            for source in sources
        }
        for log in batch.logs:
            source_id = str(log.get("source_id", ""))
            config = config_by_id.get(source_id, {})
            log["metadata_limit"] = max(
                int(log.get("metadata_limit") or 0),
                int(config.get("metadata_limit") or 0),
                int(kwargs.get("limit_per_source") or 0),
            )
            log["configured_lookback_days"] = max(
                int(log.get("configured_lookback_days") or 0),
                int(config.get("lookback_days") or 0),
                int(kwargs.get("freshness_days") or 0),
            )
        return batch


EFFECTIVE_ROUTE_VERSION = _base.EFFECTIVE_ROUTE_VERSION
begin_effective_route_audit = _base.begin_effective_route_audit
current_effective_route_audit = _base.current_effective_route_audit
end_effective_route_audit = _base.end_effective_route_audit

__all__ = [
    "BJNEWS_DEPTH_TITLE_RE",
    "BJNEWS_EFFECTIVE_ROUTES",
    "BJNEWS_NEWS_PAGES",
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
