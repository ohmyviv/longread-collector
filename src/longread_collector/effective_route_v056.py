from __future__ import annotations

import asyncio
import re
from collections import Counter
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET
from urllib.parse import urljoin, urlsplit

import httpx

from .known_source_fixes import apply_known_source_fix, parse_reader_section
from .native_discovery import (
    ARTICLE_PATH_RE,
    NON_ARTICLE_PATH_RE,
    NativeDiscoveryBatch,
    NativeDiscoveryLog,
    NativeSourceDiscovery,
    _AnchorParser,
    _clean_text,
    _make_item,
    _method_endpoints,
    _parse_date,
    parse_feed,
    parse_parser_config,
    parse_sitemap,
)
from .normalization import canonicalize_url

EFFECTIVE_ROUTE_VERSION = "effective-native-route-v0.5.6"
MIN_NATIVE_LOOKBACK_DAYS = 7
MIN_METADATA_ITEMS_PER_SOURCE = 24
MIN_EFFECTIVE_ITEMS = 6
MIN_EFFECTIVE_LOOKBACK_HOURS = 72.0

_ROUTE_AUDIT: ContextVar[dict[str, Any] | None] = ContextVar(
    "effective_native_route_audit", default=None
)

DATE_SLUG_RE = re.compile(r"-20\d{6}/?$")

KNOWN_ARTICLE_PATH_PATTERNS = (
    "/newsdetail_forward_",
    "/article/",
    "/detail/",
    "/story/",
    "/stories/",
)

JIEMIAN_SECTION_URLS = [
    # Broad finance and securities pages include bounded pagination so a
    # high-volume news day does not collapse a seven-day route to one day.
    "https://www.jiemian.com/lists/800.html",
    "https://www.jiemian.com/lists/800_2.html",
    "https://www.jiemian.com/lists/800_3.html",
    "https://www.jiemian.com/lists/800_4.html",
    "https://www.jiemian.com/lists/112.html",
    "https://www.jiemian.com/lists/112_2.html",
    "https://www.jiemian.com/lists/112_3.html",
    "https://www.jiemian.com/lists/112_4.html",
    "https://www.jiemian.com/lists/9.html",
    "https://www.jiemian.com/lists/174.html",
    "https://www.jiemian.com/lists/418.html",
    "https://www.jiemian.com/lists/423.html",
]
THEPAPER_SECTION_URLS = [
    "https://www.thepaper.cn/channel_25950",  # 时事
    "https://www.thepaper.cn/channel_25951",  # 财经
    "https://www.thepaper.cn/channel_25952",  # 思想
    "https://www.thepaper.cn/channel_25953",  # 生活
    "https://www.thepaper.cn/channel_143064",  # 深度
    "https://www.thepaper.cn/channel_119489",  # 智库
]
BJNEWS_SECTION_URLS = [
    "https://www.bjnews.com.cn/depth",
    "https://www.bjnews.com.cn/news",
    "https://www.bjnews.com.cn/",
]
PROPUBLICA_SECTION_URLS = ["https://www.propublica.org/archive/"]
QUANTA_SECTION_URLS = [
    "https://www.quantamagazine.org/archive/",
    "https://www.quantamagazine.org/biology/",
]


def begin_effective_route_audit() -> Token:
    return _ROUTE_AUDIT.set(None)


def current_effective_route_audit() -> dict[str, Any] | None:
    value = _ROUTE_AUDIT.get()
    return dict(value) if value else None


def end_effective_route_audit(token: Token) -> None:
    _ROUTE_AUDIT.reset(token)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split("|") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def apply_effective_route_fix(source: dict[str, Any]) -> dict[str, Any]:
    """Extend validated source fixes with broader, auditable route coverage."""
    item = apply_known_source_fix(source)
    source_id = str(item.get("source_id", ""))
    config = parse_parser_config(item)

    if source_id == "jiemian-depth":
        config["section_urls"] = list(JIEMIAN_SECTION_URLS)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "finance|financial|securities|macro|markets|depth"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: expand Jiemian from one depth page to finance/depth routes"
        )
    elif source_id == "thepaper":
        config["section_urls"] = list(THEPAPER_SECTION_URLS)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "current_affairs|finance|ideas|life|depth|think_tank"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.6: replace directed-search-only behavior with six native channels"
        )
    elif source_id == "bjnews-depth":
        config["section_urls"] = list(BJNEWS_SECTION_URLS)
        config["fallback_order"] = ["section_scan", "firecrawl_search"]
        config["route_scope"] = "depth|news|homepage"
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = "v0.5.6: retain enough metadata for seven-day recall"
    elif source_id == "propublica":
        config["section_urls"] = list(PROPUBLICA_SECTION_URLS)
        config["fallback_order"] = ["rss", "section_scan", "firecrawl_search"]
        config["route_scope"] = "main_feed|archive"
        item["discovery_method"] = ["rss", "section_scan", "firecrawl_search"]
        item["notes"] = "v0.5.6: supplement shallow RSS with the official archive"
    elif source_id == "quanta":
        config["section_urls"] = list(QUANTA_SECTION_URLS)
        config["fallback_order"] = ["rss", "section_scan", "firecrawl_search"]
        config["route_scope"] = "main_feed|archive|biology"
        item["discovery_method"] = ["rss", "section_scan", "firecrawl_search"]
        item["notes"] = "v0.5.6: supplement shallow RSS with official archives"

    config["metadata_limit"] = max(
        int(config.get("metadata_limit") or 0), MIN_METADATA_ITEMS_PER_SOURCE
    )
    config["lookback_days"] = max(
        int(config.get("lookback_days") or 0), MIN_NATIVE_LOOKBACK_DAYS
    )
    config.setdefault("route_scope", str(item.get("subject_groups", "") or ""))
    item["parser_config_json"] = config
    return item


def _base_domain(value: str) -> str:
    host = urlsplit(value).netloc.lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _is_article_path(path: str) -> bool:
    lower = path.lower()
    return (
        bool(ARTICLE_PATH_RE.search(path))
        or bool(DATE_SLUG_RE.search(path))
        or any(marker in lower for marker in KNOWN_ARTICLE_PATH_PATTERNS)
    )


def parse_sitemap_v056(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
    started: datetime,
    freshness_days: int,
    method: str,
) -> tuple[list[Any], list[str]]:
    """Parse up to ten sitemap-index children instead of the legacy five."""
    root = ET.fromstring(body)
    if root.tag.rsplit("}", 1)[-1].lower() == "sitemapindex":
        child_urls: list[str] = []
        for element in root:
            for child in element.iter():
                if child.tag.rsplit("}", 1)[-1].lower() != "loc":
                    continue
                value = _clean_text("".join(child.itertext()))
                if value and value not in child_urls:
                    child_urls.append(value)
                    break
        return [], child_urls[:10]
    return parse_sitemap(
        body,
        source=source,
        endpoint=endpoint,
        limit=limit,
        started=started,
        freshness_days=freshness_days,
        method=method,
    )


def parse_section_html_v056(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
) -> list[Any]:
    """Parse section pages while supporting known one-segment article URL patterns."""
    parser = _AnchorParser()
    parser.feed(body)
    source_domain = _base_domain(str(source.get("homepage_url", "")))
    items: list[Any] = []
    seen: set[str] = set()

    for href, title in parser.links:
        url = urljoin(endpoint, href)
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            continue
        if _base_domain(url) != source_domain:
            continue
        path = parts.path or "/"
        if NON_ARTICLE_PATH_RE.search(path) or not _is_article_path(path):
            continue
        title = _clean_text(title)
        if len(title) < 6:
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        items.append(
            _make_item(
                source=source,
                method="section_scan",
                endpoint=endpoint,
                url=url,
                title=title,
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items


def _merge_items(target: list[Any], incoming: list[Any], *, limit: int) -> None:
    seen = {canonicalize_url(item.url) for item in target}
    for item in incoming:
        canonical = canonicalize_url(item.url)
        if canonical in seen:
            continue
        seen.add(canonical)
        item.rank = len(target) + 1
        target.append(item)
        if len(target) >= limit:
            break


def _round_robin_items(groups: list[list[Any]], *, limit: int) -> list[Any]:
    """Interleave endpoints so one busy section cannot monopolize metadata."""
    result: list[Any] = []
    seen: set[str] = set()
    index = 0
    while len(result) < limit:
        added = False
        for group in groups:
            if index >= len(group):
                continue
            item = group[index]
            canonical = canonicalize_url(item.url)
            if canonical in seen:
                continue
            seen.add(canonical)
            item.rank = len(result) + 1
            result.append(item)
            added = True
            if len(result) >= limit:
                break
        if not added and all(index >= len(group) - 1 for group in groups):
            break
        index += 1
    return result


def _route_metrics(items: list[Any], *, started: datetime, method: str) -> dict[str, Any]:
    dated: list[datetime] = []
    for item in items:
        parsed = _parse_date(str(getattr(item, "published_at", "") or ""))
        if parsed is not None:
            dated.append(parsed)

    oldest = min(dated) if dated else None
    lookback_hours = None
    if oldest is not None:
        lookback_hours = max(
            0.0,
            (started.replace(tzinfo=None) - oldest.replace(tzinfo=None)).total_seconds()
            / 3600.0,
        )

    if not items:
        status = "no_native_results"
    elif any(
        part in {"rss", "atom", "news_sitemap", "sitemap"}
        for part in method.split("+")
    ):
        status = (
            "effective_native"
            if len(items) >= MIN_EFFECTIVE_ITEMS
            and (
                lookback_hours >= MIN_EFFECTIVE_LOOKBACK_HOURS
                if lookback_hours is not None
                else len(items) >= 12
            )
            else "partial_native"
        )
    else:
        status = "effective_native" if len(items) >= MIN_EFFECTIVE_ITEMS else "partial_native"

    return {
        "items_seen": len(items),
        "oldest_item_at": oldest.isoformat(sep=" ") if oldest else "",
        "effective_lookback_hours": (
            round(lookback_hours, 2) if lookback_hours is not None else ""
        ),
        "native_route_status": status,
        "effective_native_success": status == "effective_native",
    }


class EffectiveRouteDiscovery(NativeSourceDiscovery):
    """Native discovery with seven-day metadata depth and route-level evidence."""

    async def discover_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
        *,
        limit: int,
        started: datetime,
        freshness_days: int,
    ) -> tuple[list[Any], NativeDiscoveryLog]:
        source = apply_effective_route_fix(source)
        source_id = str(source.get("source_id", ""))
        source_name = str(source.get("source_name", ""))
        config = parse_parser_config(source)
        effective_limit = max(
            limit,
            int(config.get("metadata_limit") or 0),
            MIN_METADATA_ITEMS_PER_SOURCE,
        )
        effective_freshness = max(
            freshness_days,
            int(config.get("lookback_days") or 0),
            MIN_NATIVE_LOOKBACK_DAYS,
        )
        methods = [str(value) for value in config.get("fallback_order", [])]
        declared = _as_list(source.get("discovery_method"))
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None

        if source_id == "inside-climate-news":
            return [], NativeDiscoveryLog(
                source_id=source_id,
                source_name=source_name,
                success=False,
                fallback_needed=True,
                attempts=[
                    {
                        "method": "firecrawl_search",
                        "endpoint": str(source.get("homepage_url", "")),
                        "reason": "official native endpoints blocked for GitHub runners",
                    }
                ],
                error_type="NativeAccessBlocked",
                error_message=(
                    "Official feed, archive, API and reader endpoints remain blocked; "
                    "use bounded Firecrawl fallback"
                ),
            )

        all_items: list[Any] = []
        successful_methods: list[str] = []
        successful_endpoints: list[str] = []

        for method in methods:
            if method == "firecrawl_search":
                break
            if method not in declared and method not in {
                "news_sitemap",
                "sitemap",
                "section_scan",
            }:
                continue

            endpoints = _method_endpoints(source, method)

            async def fetch_endpoint(endpoint: str):
                attempt: dict[str, Any] = {"method": method, "endpoint": endpoint}
                try:
                    response = await self._get(client, endpoint)
                    attempt["http_status"] = response.status_code
                    attempt["content_type"] = response.headers.get("content-type", "")
                    if method in {"rss", "atom"}:
                        parsed_items = parse_feed(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=effective_limit,
                            started=started,
                            freshness_days=effective_freshness,
                        )
                    elif method in {"news_sitemap", "sitemap"}:
                        parsed_items, child_sitemaps = parse_sitemap_v056(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=effective_limit,
                            started=started,
                            freshness_days=effective_freshness,
                            method=method,
                        )
                        for child_url in child_sitemaps:
                            if len(parsed_items) >= effective_limit:
                                break
                            child_response = await self._get(client, child_url)
                            child_items, _ = parse_sitemap_v056(
                                child_response.text,
                                source=source,
                                endpoint=child_url,
                                limit=effective_limit - len(parsed_items),
                                started=started,
                                freshness_days=effective_freshness,
                                method=method,
                            )
                            _merge_items(parsed_items, child_items, limit=effective_limit)
                    elif method in {"section_scan", "homepage"}:
                        parsed_items = parse_section_html_v056(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=effective_limit,
                        )
                    else:
                        parsed_items = []
                    attempt["results_count"] = len(parsed_items)
                    return endpoint, parsed_items, attempt, None
                except Exception as exc:
                    attempt["error_type"] = type(exc).__name__
                    attempt["error_message"] = str(exc)[:300]
                    return endpoint, [], attempt, exc

            endpoint_results = (
                await asyncio.gather(*(fetch_endpoint(endpoint) for endpoint in endpoints))
                if endpoints
                else []
            )
            endpoint_groups: list[list[Any]] = []
            method_endpoints: list[str] = []
            for endpoint, parsed_items, attempt, error in endpoint_results:
                attempts.append(attempt)
                if error is not None:
                    last_error = error
                if parsed_items:
                    method_endpoints.append(endpoint)
                    endpoint_groups.append(parsed_items)

            method_items = _round_robin_items(endpoint_groups, limit=effective_limit)
            _merge_items(all_items, method_items, limit=effective_limit)
            if method_items:
                successful_methods.append(method)
                successful_endpoints.extend(method_endpoints)
            if len(all_items) >= effective_limit:
                break

        if all_items:
            route_type = "+".join(successful_methods)
            metrics = _route_metrics(all_items, started=started, method=route_type)
            route_scope = str(config.get("route_scope", "") or "")
            sections_covered = list(dict.fromkeys(successful_endpoints))
            for item in all_items:
                item.metadata.update(
                    {
                        "effective_route_version": EFFECTIVE_ROUTE_VERSION,
                        "route_type": route_type,
                        "items_seen": metrics["items_seen"],
                        "oldest_item_at": metrics["oldest_item_at"],
                        "effective_lookback_hours": metrics["effective_lookback_hours"],
                        "sections_covered": sections_covered,
                        "route_scope": route_scope,
                        "native_route_status": metrics["native_route_status"],
                        "effective_native_success": metrics["effective_native_success"],
                        "fallback_used": False,
                        "configured_lookback_days": effective_freshness,
                        "metadata_limit": effective_limit,
                    }
                )
            return all_items, NativeDiscoveryLog(
                source_id=source_id,
                source_name=source_name,
                success=True,
                selected_method=route_type,
                selected_endpoint="|".join(sections_covered),
                results_count=len(all_items),
                fallback_needed=False,
                attempts=attempts,
            )

        if source_id == "deeptech":
            endpoint = "https://r.jina.ai/http://www.mittrchina.com/news"
            attempt = {"method": "reader_section", "endpoint": endpoint}
            try:
                response = await self._get(client, endpoint)
                reader_items = parse_reader_section(
                    response.text,
                    source=source,
                    endpoint=endpoint,
                    limit=effective_limit,
                )
                attempt.update(
                    {
                        "http_status": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "results_count": len(reader_items),
                    }
                )
                attempts.append(attempt)
                if reader_items:
                    metrics = _route_metrics(
                        reader_items, started=started, method="reader_section"
                    )
                    for item in reader_items:
                        item.metadata.update(
                            {
                                "effective_route_version": EFFECTIVE_ROUTE_VERSION,
                                "route_type": "reader_section",
                                "items_seen": metrics["items_seen"],
                                "oldest_item_at": metrics["oldest_item_at"],
                                "effective_lookback_hours": metrics[
                                    "effective_lookback_hours"
                                ],
                                "sections_covered": [endpoint],
                                "route_scope": str(config.get("route_scope", "")),
                                "native_route_status": metrics["native_route_status"],
                                "effective_native_success": metrics[
                                    "effective_native_success"
                                ],
                                "fallback_used": False,
                                "configured_lookback_days": effective_freshness,
                                "metadata_limit": effective_limit,
                            }
                        )
                    return reader_items, NativeDiscoveryLog(
                        source_id=source_id,
                        source_name=source_name,
                        success=True,
                        selected_method="reader_section",
                        selected_endpoint=endpoint,
                        results_count=len(reader_items),
                        attempts=attempts,
                    )
            except Exception as exc:
                last_error = exc
                attempt["error_type"] = type(exc).__name__
                attempt["error_message"] = str(exc)[:300]
                attempts.append(attempt)

        return [], NativeDiscoveryLog(
            source_id=source_id,
            source_name=source_name,
            success=False,
            fallback_needed="firecrawl_search" in declared,
            attempts=attempts,
            error_type=type(last_error).__name__ if last_error else "NoNativeResults",
            error_message=(
                str(last_error)[:300]
                if last_error
                else "No native route returned article URLs"
            ),
        )

    async def discover(
        self,
        sources: list[dict[str, Any]],
        *,
        limit_per_source: int,
        started: datetime,
        freshness_days: int,
    ) -> NativeDiscoveryBatch:
        fixed_sources = [apply_effective_route_fix(source) for source in sources]
        batch = await super().discover(
            fixed_sources,
            limit_per_source=max(limit_per_source, MIN_METADATA_ITEMS_PER_SOURCE),
            started=started,
            freshness_days=max(freshness_days, MIN_NATIVE_LOOKBACK_DAYS),
        )

        source_config_by_id = {
            str(source.get("source_id", "")): parse_parser_config(source)
            for source in fixed_sources
        }
        items_by_source: dict[str, list[Any]] = {}
        for item in batch.items:
            source_id = str(item.metadata.get("source_id", ""))
            items_by_source.setdefault(source_id, []).append(item)

        status_counts: Counter[str] = Counter()
        for log in batch.logs:
            source_id = str(log.get("source_id", ""))
            source_items = items_by_source.get(source_id, [])
            route_type = str(log.get("selected_method", "") or "")
            metrics = _route_metrics(source_items, started=started, method=route_type)
            successful_endpoints = [
                str(attempt.get("endpoint", ""))
                for attempt in log.get("attempts", [])
                if attempt.get("results_count")
            ]
            status = metrics["native_route_status"]
            status_counts[status] += 1
            route_config = source_config_by_id.get(source_id, {})
            log.update(
                {
                    "effective_route_version": EFFECTIVE_ROUTE_VERSION,
                    "route_type": route_type,
                    "items_seen": metrics["items_seen"],
                    "oldest_item_at": metrics["oldest_item_at"],
                    "effective_lookback_hours": metrics["effective_lookback_hours"],
                    "sections_covered": successful_endpoints,
                    "route_scope": str(route_config.get("route_scope", "") or ""),
                    "native_route_status": status,
                    "effective_native_success": metrics["effective_native_success"],
                    "fallback_used": bool(log.get("fallback_needed")),
                    "configured_lookback_days": max(
                        freshness_days, MIN_NATIVE_LOOKBACK_DAYS
                    ),
                    "metadata_limit": max(
                        limit_per_source, MIN_METADATA_ITEMS_PER_SOURCE
                    ),
                }
            )

        audit = {
            "version": EFFECTIVE_ROUTE_VERSION,
            "sources_attempted": len(batch.logs),
            "effective_native_successes": status_counts["effective_native"],
            "partial_native_routes": status_counts["partial_native"],
            "no_native_results": status_counts["no_native_results"],
            "status_counts": dict(status_counts),
            "items_discovered": len(batch.items),
            "configured_lookback_days": max(
                freshness_days, MIN_NATIVE_LOOKBACK_DAYS
            ),
            "metadata_limit_per_source": max(
                limit_per_source, MIN_METADATA_ITEMS_PER_SOURCE
            ),
        }
        _ROUTE_AUDIT.set(audit)
        return batch


__all__ = [
    "BJNEWS_SECTION_URLS",
    "EFFECTIVE_ROUTE_VERSION",
    "EffectiveRouteDiscovery",
    "JIEMIAN_SECTION_URLS",
    "MIN_METADATA_ITEMS_PER_SOURCE",
    "MIN_NATIVE_LOOKBACK_DAYS",
    "PROPUBLICA_SECTION_URLS",
    "QUANTA_SECTION_URLS",
    "THEPAPER_SECTION_URLS",
    "apply_effective_route_fix",
    "begin_effective_route_audit",
    "current_effective_route_audit",
    "end_effective_route_audit",
    "parse_section_html_v056",
    "parse_sitemap_v056",
]
