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
_BASE_ROUTE_METRICS = _base._route_metrics

JIEMIAN_EFFECTIVE_ROUTES = [
    # The final-report market-infrastructure article is present on this page.
    "https://www.jiemian.com/lists/506.html",
    # The final-report JPY analysis carries the 财经速递 tag. The tag archive
    # exposes stable numbered pages, unlike invalid list-page suffixes.
    *[f"https://www.jiemian.com/tags/712/{page}.html" for page in range(1, 9)],
    "https://www.jiemian.com/lists/174.html",
    "https://www.jiemian.com/lists/423.html",
]

BJNEWS_EFFECTIVE_ROUTES = [
    "https://www.bjnews.com.cn/depth",
    "https://www.bjnews.com.cn/news",
    "https://www.bjnews.com.cn/",
]
# Live GitHub-runner validation found official pages 1-31 reachable; page 32+
# return 405. Keep the route bounded to the verified range.
BJNEWS_NEWS_PAGES = [
    "https://www.bjnews.com.cn/news",
    *[f"https://www.bjnews.com.cn/news/{page}.html" for page in range(2, 32)],
]
BJNEWS_DETAIL_TIMESTAMP_RE = re.compile(r"detail[-/](\d{13})\d*")
BJNEWS_DEPTH_TITLE_RE = re.compile(
    r"调查|暗访|起底|专访|深度|追踪|复盘|观察|人物|故事|逝者|剥洋葱|"
    r"重建现场|报告|何以|为什么|真相|困境|争议|内幕|生死|十年|多年"
)

THEPAPER_API_ENDPOINT = (
    "https://api.thepaper.cn/contentapi/nodeCont/getByNodeIdPortal"
)
THEPAPER_CHANNELS = {
    25462: "中国政库",
    25448: "有戏",
}
THEPAPER_EFFECTIVE_ROUTES = [
    "https://www.thepaper.cn/list_25462",
    "https://www.thepaper.cn/list_25448",
]
THEPAPER_MAX_CURSOR_PAGES = 12
THEPAPER_PAGE_SIZE = 20

_SOURCE_METADATA_LIMITS = {
    "jiemian-depth": 96,
    "bjnews-depth": 64,
    # China Politics needs ten cursor pages in the fixed validation window;
    # Culture needs two. This remains metadata-only and does not change the
    # 32-body extraction cap.
    "thepaper": 240,
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
        config["api_endpoint"] = THEPAPER_API_ENDPOINT
        config["api_node_ids"] = list(THEPAPER_CHANNELS)
        config["fallback_order"] = ["api_cursor", "firecrawl_search"]
        config["route_scope"] = "china_politics|culture_and_entertainment"
        config["cursor_page_limit"] = THEPAPER_MAX_CURSOR_PAGES
        item["discovery_method"] = ["api_cursor", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: official nodeCont cursor API with pubTimeLong evidence"
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


def truthful_route_metrics(
    items: list[Any], *, started: datetime, method: str
) -> dict[str, Any]:
    """Do not call an undated route effective merely because it returned links."""
    metrics = _BASE_ROUTE_METRICS(items, started=started, method=method)
    if items and not metrics.get("oldest_item_at"):
        metrics["native_route_status"] = "partial_native"
        metrics["effective_native_success"] = False
    return metrics


def _bjnews_published_at(url: str) -> datetime | None:
    """Recover an approximate article-record creation time from BJNews IDs.

    The 13-digit prefix is useful for bounded freshness filtering, but live
    article pages show that it can precede the displayed publication time. It
    remains medium-confidence evidence and is not presented as exact publish time.
    """
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


def _thepaper_published_at(value: Any) -> datetime | None:
    try:
        timestamp = int(value) / 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(
            ZoneInfo("Asia/Shanghai")
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _thepaper_item(
    raw: dict[str, Any],
    *,
    source: dict[str, Any],
    node_id: int,
    rank: int,
) -> Any | None:
    cont_id = str(raw.get("contId", "") or "").strip()
    title = str(raw.get("name", "") or "").strip()
    published = _thepaper_published_at(raw.get("pubTimeLong"))
    if not cont_id or not title or published is None:
        return None
    url = f"https://www.thepaper.cn/newsDetail_forward_{cont_id}"
    item = _base._make_item(
        source=source,
        method="api_cursor",
        endpoint=THEPAPER_API_ENDPOINT,
        url=url,
        title=title,
        description=str(raw.get("summary", "") or ""),
        published_at=published.isoformat(sep=" "),
        rank=rank,
    )
    item.metadata.update(
        {
            "node_id": node_id,
            "node_name": THEPAPER_CHANNELS.get(node_id, ""),
            "cont_id": cont_id,
            "published_at_source": "thepaper_api_pubTimeLong",
            "published_at_confidence": "high",
            "external_link": str(raw.get("link", "") or ""),
            "is_out_forward": str(
                raw.get("isOutForward", raw.get("isOutForword", "")) or ""
            ),
        }
    )
    return item


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
            observed = _bjnews_published_at(item.url)
            if observed is None or observed.timestamp() < cutoff_timestamp:
                continue
            if endpoint != "https://www.bjnews.com.cn/depth" and not BJNEWS_DEPTH_TITLE_RE.search(
                item.title
            ):
                continue
            item.published_at = observed.isoformat(sep=" ")
            item.metadata.update(
                {
                    "published_at_source": "bjnews_article_id_epoch_ms_approx",
                    "published_at_confidence": "medium",
                    "published_at_note": (
                        "article ID time can precede displayed publication; "
                        "use only for bounded freshness filtering"
                    ),
                    "source_page": endpoint,
                }
            )
            filtered.append(item)
        if filtered:
            groups.append(filtered)
            successful_endpoints.append(endpoint)

    metadata_limit = max(limit, _SOURCE_METADATA_LIMITS["bjnews-depth"])
    items = _priority_items(groups, limit=metadata_limit)
    metrics = truthful_route_metrics(
        items, started=started, method="section_scan_paginated"
    )
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


async def _discover_thepaper(
    discovery: "EffectiveRouteDiscovery",
    client: httpx.AsyncClient,
    source: dict[str, Any],
    *,
    limit: int,
    started: datetime,
    freshness_days: int,
) -> tuple[list[Any], NativeDiscoveryLog]:
    """Use The Paper's public startTime cursor API with exact time evidence."""
    source = apply_effective_route_fix(source)
    attempts: list[dict[str, Any]] = []
    groups: list[list[Any]] = []
    started_bj = started.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    cutoff_timestamp = started_bj.timestamp() - max(freshness_days, 7) * 86400
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.thepaper.cn",
        "Referer": "https://www.thepaper.cn/",
    }

    for node_id, node_name in THEPAPER_CHANNELS.items():
        cursor: int | None = None
        seen_cursors: set[int] = set()
        node_items: list[Any] = []

        for page in range(1, THEPAPER_MAX_CURSOR_PAGES + 1):
            payload: dict[str, Any] = {
                "nodeId": node_id,
                "pageSize": THEPAPER_PAGE_SIZE,
            }
            if cursor is not None:
                payload["startTime"] = cursor
            attempt: dict[str, Any] = {
                "method": "api_cursor",
                "endpoint": THEPAPER_API_ENDPOINT,
                "node_id": node_id,
                "node_name": node_name,
                "page": page,
                "start_time": cursor,
            }
            try:
                response = await client.post(
                    THEPAPER_API_ENDPOINT,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                parsed = response.json()
                data = parsed.get("data") if isinstance(parsed, dict) else None
                raw_items = data.get("list", []) if isinstance(data, dict) else []
                next_cursor = data.get("startTime") if isinstance(data, dict) else None
                attempt.update(
                    {
                        "http_status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "results_count": len(raw_items),
                        "next_start_time": next_cursor,
                        "has_next": bool(data.get("hasNext")) if data else False,
                    }
                )
            except Exception as exc:
                attempt.update(
                    {
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:300],
                    }
                )
                attempts.append(attempt)
                break

            attempts.append(attempt)
            page_times: list[datetime] = []
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                published = _thepaper_published_at(raw.get("pubTimeLong"))
                if published is None:
                    continue
                page_times.append(published)
                if published.timestamp() < cutoff_timestamp:
                    continue
                item = _thepaper_item(
                    raw,
                    source=source,
                    node_id=node_id,
                    rank=len(node_items) + 1,
                )
                if item is not None:
                    node_items.append(item)

            if page_times and min(page_times).timestamp() < cutoff_timestamp:
                attempt["stopped_reason"] = "lookback_complete"
                break
            if not data or not data.get("hasNext") or not next_cursor:
                attempt["stopped_reason"] = "no_next_page"
                break
            next_cursor = int(next_cursor)
            if next_cursor in seen_cursors or next_cursor == cursor:
                attempt["stopped_reason"] = "repeated_cursor"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
            await asyncio.sleep(0.2)

        if node_items:
            groups.append(node_items)

    metadata_limit = max(limit, _SOURCE_METADATA_LIMITS["thepaper"])
    items = _priority_items(groups, limit=metadata_limit)
    metrics = truthful_route_metrics(items, started=started, method="api_cursor")
    for item in items:
        item.metadata.update(
            {
                "effective_route_version": _base.EFFECTIVE_ROUTE_VERSION,
                "route_type": "api_cursor",
                "items_seen": len(items),
                "oldest_item_at": metrics["oldest_item_at"],
                "effective_lookback_hours": metrics["effective_lookback_hours"],
                "sections_covered": [
                    f"node:{node_id}:{node_name}"
                    for node_id, node_name in THEPAPER_CHANNELS.items()
                ],
                "route_scope": "china_politics|culture_and_entertainment",
                "native_route_status": metrics["native_route_status"],
                "effective_native_success": metrics["effective_native_success"],
                "fallback_used": False,
                "configured_lookback_days": max(freshness_days, 7),
                "metadata_limit": metadata_limit,
            }
        )

    return items, NativeDiscoveryLog(
        source_id="thepaper",
        source_name=str(source.get("source_name", "澎湃新闻")),
        success=bool(items),
        selected_method="api_cursor" if items else "",
        selected_endpoint=THEPAPER_API_ENDPOINT if items else "",
        results_count=len(items),
        fallback_needed=not bool(items),
        attempts=attempts,
        error_type="" if items else "NoNativeResults",
        error_message="" if items else "No seven-day API items found",
    )


@contextmanager
def _activated_route_contracts():
    previous_apply = _base.apply_effective_route_fix
    previous_merge = _base._round_robin_items
    previous_metrics = _base._route_metrics
    _base.apply_effective_route_fix = apply_effective_route_fix
    _base._round_robin_items = merge_route_items
    _base._route_metrics = truthful_route_metrics
    try:
        yield
    finally:
        _base.apply_effective_route_fix = previous_apply
        _base._round_robin_items = previous_merge
        _base._route_metrics = previous_metrics


class EffectiveRouteDiscovery(_base.EffectiveRouteDiscovery):
    """Base effective discovery with source-specific contracts scoped per call."""

    async def discover_source(self, client, source, **kwargs):
        source_id = str(source.get("source_id", ""))
        if source_id == "bjnews-depth":
            return await _discover_bjnews(self, client, source, **kwargs)
        if source_id == "thepaper":
            return await _discover_thepaper(self, client, source, **kwargs)
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
    "THEPAPER_API_ENDPOINT",
    "THEPAPER_CHANNELS",
    "THEPAPER_EFFECTIVE_ROUTES",
    "THEPAPER_MAX_CURSOR_PAGES",
    "apply_effective_route_fix",
    "begin_effective_route_audit",
    "current_effective_route_audit",
    "end_effective_route_audit",
    "merge_route_items",
    "truthful_route_metrics",
]
