"""Effective native-source routes for collector v0.5.6 shadow.

This layer expands lightweight metadata discovery only. It does not change the
32-URL extraction ceiling, Firecrawl scrape budget, or downstream editor gate.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .known_source_fixes import (
    KnownFallbackAwareDiscovery,
    apply_known_source_fix,
    parse_reader_section,
    select_sources_for_run as _select_sources_for_run_v051,
)
from .models import DiscoveredURL
from .native_discovery import (
    DEFAULT_USER_AGENT,
    NativeDiscoveryBatch,
    NativeDiscoveryLog,
    _clean_text,
    _make_item,
    _method_endpoints,
    _parse_date,
    parse_feed,
    parse_parser_config,
    parse_sitemap,
)
from .normalization import canonicalize_url

NATIVE_ROUTE_VERSION = "effective-native-routes-v0.5.6"
TARGET_LOOKBACK_DAYS = 7
METADATA_LIMIT_PER_SOURCE = 30
MIN_BREADTH_PROXY_ITEMS = 12

_ROUTE_AUDIT: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "native_route_audit_v056", default=()
)

SOURCE_SECTION_ROUTES: dict[str, tuple[str, ...]] = {
    "propublica": (
        "https://www.propublica.org/archive/",
        "https://www.propublica.org/archive/page/2",
        "https://www.propublica.org/archive/page/3",
    ),
    "quanta": ("https://www.quantamagazine.org/archive/",),
    "jiemian-depth": (
        "https://www.jiemian.com/lists/423.html",
        "https://www.jiemian.com/lists/9.html",
        "https://www.jiemian.com/lists/112.html",
        "https://www.jiemian.com/lists/800.html",
        "https://www.jiemian.com/lists/174.html",
        "https://www.jiemian.com/lists/418.html",
        "https://www.jiemian.com/lists/71.html",
    ),
    "bjnews-depth": (
        "https://www.bjnews.com.cn/depth",
        "https://m.bjnews.com.cn/depth",
        "https://www.bjnews.com.cn/news/",
        "https://www.bjnews.com.cn/subject",
    ),
    "thepaper": (
        "https://m.thepaper.cn/",
        "https://www.thepaper.cn/channel_25950?isBindMobile=0",
        "https://www.thepaper.cn/list_25448",
    ),
}

_SOURCE_ARTICLE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "propublica": (re.compile(r"^/article/[^/]+/?$", re.I),),
    "quanta": (re.compile(r"^/[^/]+-20\d{6}/?$", re.I),),
    "jiemian-depth": (re.compile(r"^/article/\d+\.html$", re.I),),
    "bjnews-depth": (re.compile(r"^/detail/\d+\.html$", re.I),),
    "thepaper": (re.compile(r"^/newsDetail_forward_\d+$", re.I),),
}

_QUANTA_DATE_RE = re.compile(r"-(20\d{6})(?:/)?$")
_BJNEWS_TIMESTAMP_RE = re.compile(r"/detail/(\d{10})\d*\.html$")


def reset_native_route_audit() -> None:
    _ROUTE_AUDIT.set(())


def current_native_route_audit() -> list[dict[str, Any]]:
    return [dict(row) for row in _ROUTE_AUDIT.get()]


def _normalise_declared_methods(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split("|") if item.strip()]


def _site_key(host: str) -> str:
    value = host.lower().split(":", 1)[0]
    for prefix in ("www.", "m.", "amp."):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value


def apply_v056_source_route(source: dict[str, Any]) -> dict[str, Any]:
    """Add audited route breadth without mutating the registry row."""
    item = apply_known_source_fix(source)
    item = deepcopy(item)
    source_id = str(item.get("source_id", ""))
    config = parse_parser_config(item)

    section_urls = [str(value).strip() for value in config.get("section_urls", [])]
    for endpoint in SOURCE_SECTION_ROUTES.get(source_id, ()):
        if endpoint not in section_urls:
            section_urls.append(endpoint)
    config["section_urls"] = section_urls
    config["route_version"] = NATIVE_ROUTE_VERSION
    config["target_lookback_days"] = TARGET_LOOKBACK_DAYS
    config["metadata_limit_per_source"] = METADATA_LIMIT_PER_SOURCE

    declared = _normalise_declared_methods(item.get("discovery_method"))
    if section_urls and "section_scan" not in declared:
        declared.insert(0, "section_scan")
    item["discovery_method"] = declared

    fallback_order = [str(value) for value in config.get("fallback_order", [])]
    if section_urls and "section_scan" not in fallback_order:
        insert_at = fallback_order.index("firecrawl_search") if "firecrawl_search" in fallback_order else len(fallback_order)
        fallback_order.insert(insert_at, "section_scan")
    config["fallback_order"] = fallback_order
    item["parser_config_json"] = config
    return item


def select_sources_for_run_v056(
    sources: list[dict[str, Any]],
    *,
    started: datetime,
    max_sources: int,
    rotate_share: float = 0.75,
) -> list[dict[str, Any]]:
    selected = _select_sources_for_run_v051(
        sources,
        started=started,
        max_sources=max_sources,
        rotate_share=rotate_share,
    )
    return [apply_v056_source_route(source) for source in selected]


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        self._href = values.get("href", "")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, _clean_text(" ".join(self._text))))
            self._href = ""
            self._text = []


def _published_from_url(source_id: str, url: str) -> str:
    if source_id == "quanta":
        match = _QUANTA_DATE_RE.search(urlsplit(url).path)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y%m%d").isoformat()
            except ValueError:
                return ""
    if source_id == "bjnews-depth":
        match = _BJNEWS_TIMESTAMP_RE.search(urlsplit(url).path)
        if match:
            try:
                return datetime.fromtimestamp(
                    int(match.group(1)), tz=timezone.utc
                ).replace(tzinfo=None).isoformat()
            except (OverflowError, OSError, ValueError):
                return ""
    return ""


def parse_effective_section_html(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
) -> list[DiscoveredURL]:
    """Parse section/archive pages with source-specific article URL contracts."""
    parser = _AnchorParser()
    parser.feed(body)
    source_id = str(source.get("source_id", ""))
    source_site = _site_key(urlsplit(str(source.get("homepage_url", ""))).netloc)
    patterns = _SOURCE_ARTICLE_PATTERNS.get(source_id, ())
    items: list[DiscoveredURL] = []
    seen: set[str] = set()

    for href, title in parser.links:
        url = urljoin(endpoint, href)
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            continue
        if _site_key(parts.netloc) != source_site:
            continue
        if patterns and not any(pattern.search(parts.path) for pattern in patterns):
            continue
        if not patterns and len([part for part in parts.path.split("/") if part]) < 2:
            continue
        if len(title) < 6:
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        items.append(
            _make_item(
                source=source,
                method="section_scan_v056",
                endpoint=endpoint,
                url=url,
                title=title,
                published_at=_published_from_url(source_id, url),
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items


def _round_robin_unique(
    route_items: list[list[DiscoveredURL]],
    *,
    limit: int,
) -> tuple[list[DiscoveredURL], int]:
    all_unique: dict[str, DiscoveredURL] = {}
    for batch in route_items:
        for item in batch:
            all_unique.setdefault(canonicalize_url(item.url), item)

    selected: list[DiscoveredURL] = []
    seen: set[str] = set()
    max_depth = max((len(batch) for batch in route_items), default=0)
    for index in range(max_depth):
        for batch in route_items:
            if index >= len(batch):
                continue
            item = batch[index]
            canonical = canonicalize_url(item.url)
            if canonical in seen:
                continue
            seen.add(canonical)
            selected.append(item)
            if len(selected) >= limit:
                return selected, len(all_unique)
    return selected, len(all_unique)


def _route_metrics(
    *,
    source_id: str,
    selected: list[DiscoveredURL],
    items_seen: int,
    sections_covered: list[str],
    started: datetime,
    fallback_needed: bool,
) -> dict[str, Any]:
    dates = [_parse_date(item.published_at) for item in selected]
    parsed_dates = [value for value in dates if value is not None]
    oldest = min(parsed_dates) if parsed_dates else None
    lookback_hours: float | None = None
    if oldest is not None:
        lookback_hours = round(
            max(0.0, (started.replace(tzinfo=None) - oldest).total_seconds() / 3600),
            2,
        )

    if not selected:
        status = "fallback_only" if fallback_needed else "no_native_results"
        basis = "none"
    elif lookback_hours is not None and lookback_hours >= TARGET_LOOKBACK_DAYS * 24 - 6:
        status = "effective_native"
        basis = "dated_window"
    elif items_seen >= MIN_BREADTH_PROXY_ITEMS and len(sections_covered) >= 2:
        status = "effective_native"
        basis = "breadth_proxy"
    else:
        status = "partial_native"
        basis = "insufficient_dated_or_breadth_evidence"

    return {
        "route_version": NATIVE_ROUTE_VERSION,
        "source_id": source_id,
        "route_type": "multi_route" if len(sections_covered) > 1 else "single_route",
        "items_seen": items_seen,
        "items_returned": len(selected),
        "oldest_item_at": oldest.isoformat() if oldest else "",
        "effective_lookback_hours": lookback_hours,
        "sections_covered": sections_covered,
        "native_route_status": status,
        "coverage_basis": basis,
        "fallback_needed": fallback_needed,
        "fallback_used": False,
    }


class EffectiveNativeRouteDiscovery(KnownFallbackAwareDiscovery):
    """Aggregate RSS, sitemap and section routes before bounded extraction."""

    async def discover_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
        *,
        limit: int,
        started: datetime,
        freshness_days: int,
    ) -> tuple[list[DiscoveredURL], NativeDiscoveryLog]:
        source = apply_v056_source_route(source)
        source_id = str(source.get("source_id", ""))
        source_name = str(source.get("source_name", ""))
        target_limit = max(limit, METADATA_LIMIT_PER_SOURCE)
        target_days = max(freshness_days, TARGET_LOOKBACK_DAYS)
        declared = _normalise_declared_methods(source.get("discovery_method"))
        config = parse_parser_config(source)
        methods = [str(value) for value in config.get("fallback_order", [])]

        if source_id == "inside-climate-news":
            items, log = await super().discover_source(
                client,
                source,
                limit=target_limit,
                started=started,
                freshness_days=target_days,
            )
            metrics = _route_metrics(
                source_id=source_id,
                selected=items,
                items_seen=len(items),
                sections_covered=[],
                started=started,
                fallback_needed=log.fallback_needed,
            )
            log.attempts.append({"method": "route_summary", **metrics})
            return items, log

        attempts: list[dict[str, Any]] = []
        route_batches: list[list[DiscoveredURL]] = []
        sections_covered: list[str] = []
        last_error: Exception | None = None

        for method in methods:
            if method == "firecrawl_search":
                continue
            if method not in declared and method not in {
                "news_sitemap",
                "sitemap",
                "section_scan",
                "homepage",
            }:
                continue
            for endpoint in _method_endpoints(source, method):
                attempt: dict[str, Any] = {"method": method, "endpoint": endpoint}
                try:
                    response = await self._get(client, endpoint)
                    attempt["http_status"] = response.status_code
                    attempt["content_type"] = response.headers.get("content-type", "")
                    if method in {"rss", "atom"}:
                        batch = parse_feed(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=target_limit,
                            started=started,
                            freshness_days=target_days,
                        )
                    elif method in {"news_sitemap", "sitemap"}:
                        batch, children = parse_sitemap(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=target_limit,
                            started=started,
                            freshness_days=target_days,
                            method=method,
                        )
                        for child_url in children[:8]:
                            child_response = await self._get(client, child_url)
                            child_items, _ = parse_sitemap(
                                child_response.text,
                                source=source,
                                endpoint=child_url,
                                limit=target_limit,
                                started=started,
                                freshness_days=target_days,
                                method=method,
                            )
                            batch.extend(child_items)
                    elif method in {"section_scan", "homepage"}:
                        batch = parse_effective_section_html(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=target_limit,
                        )
                    else:
                        batch = []
                    attempt["results_count"] = len(batch)
                    attempts.append(attempt)
                    if batch:
                        route_batches.append(batch)
                        sections_covered.append(endpoint)
                except Exception as exc:  # route failures remain isolated
                    last_error = exc
                    attempt["error_type"] = type(exc).__name__
                    attempt["error_message"] = str(exc)[:300]
                    attempts.append(attempt)

        if source_id == "deeptech" and not route_batches:
            endpoint = "https://r.jina.ai/http://www.mittrchina.com/news"
            attempt = {"method": "reader_section", "endpoint": endpoint}
            try:
                response = await self._get(client, endpoint)
                batch = parse_reader_section(
                    response.text,
                    source=source,
                    endpoint=endpoint,
                    limit=target_limit,
                )
                attempt["http_status"] = response.status_code
                attempt["results_count"] = len(batch)
                attempts.append(attempt)
                if batch:
                    route_batches.append(batch)
                    sections_covered.append(endpoint)
            except Exception as exc:
                last_error = exc
                attempt["error_type"] = type(exc).__name__
                attempt["error_message"] = str(exc)[:300]
                attempts.append(attempt)

        selected, items_seen = _round_robin_unique(
            route_batches,
            limit=target_limit,
        )
        fallback_needed = not selected and "firecrawl_search" in declared
        metrics = _route_metrics(
            source_id=source_id,
            selected=selected,
            items_seen=items_seen,
            sections_covered=sections_covered,
            started=started,
            fallback_needed=fallback_needed,
        )
        for item in selected:
            item.metadata.setdefault("native_route", {}).update(metrics)
        attempts.append({"method": "route_summary", **metrics})

        return selected, NativeDiscoveryLog(
            source_id=source_id,
            source_name=source_name,
            success=bool(selected),
            selected_method=metrics["route_type"] if selected else "",
            selected_endpoint="|".join(sections_covered[:8]),
            results_count=len(selected),
            fallback_needed=fallback_needed,
            attempts=attempts,
            error_type=(
                "" if selected else type(last_error).__name__ if last_error else "NoNativeResults"
            ),
            error_message=(
                "" if selected else str(last_error)[:300] if last_error else "No native route returned article URLs"
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
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
        limits = httpx.Limits(
            max_connections=self.concurrency,
            max_keepalive_connections=min(self.concurrency, 8),
        )
        semaphore = asyncio.Semaphore(self.concurrency)
        fixed_sources = [apply_v056_source_route(source) for source in sources]

        async with httpx.AsyncClient(headers=headers, limits=limits) as client:
            async def one(source: dict[str, Any]):
                async with semaphore:
                    return await self.discover_source(
                        client,
                        source,
                        limit=limit_per_source,
                        started=started,
                        freshness_days=freshness_days,
                    )

            output = await asyncio.gather(*(one(source) for source in fixed_sources))

        items: list[DiscoveredURL] = []
        logs: list[dict[str, Any]] = []
        fallback_sources: list[dict[str, Any]] = []
        source_by_id = {
            str(source.get("source_id", "")): source for source in fixed_sources
        }
        audit_rows: list[dict[str, Any]] = []

        for discovered, log in output:
            items.extend(discovered)
            summary = next(
                (
                    dict(attempt)
                    for attempt in reversed(log.attempts)
                    if attempt.get("method") == "route_summary"
                ),
                {},
            )
            summary.pop("method", None)
            row = {
                "success": log.success,
                "query_id": f"source:{log.source_id}",
                "source_id": log.source_id,
                "source_name": log.source_name,
                "purpose": log.purpose,
                "selected_method": log.selected_method,
                "selected_endpoint": log.selected_endpoint,
                "results_count": log.results_count,
                "fallback_needed": log.fallback_needed,
                "attempts": log.attempts,
                "error_type": log.error_type,
                "error_message": log.error_message,
                "credits_used": 0,
                **summary,
            }
            logs.append(row)
            audit_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if key
                    in {
                        "source_id",
                        "source_name",
                        "route_version",
                        "route_type",
                        "items_seen",
                        "items_returned",
                        "oldest_item_at",
                        "effective_lookback_hours",
                        "sections_covered",
                        "native_route_status",
                        "coverage_basis",
                        "fallback_needed",
                        "fallback_used",
                    }
                }
            )
            if log.fallback_needed and log.source_id in source_by_id:
                fallback_sources.append(source_by_id[log.source_id])

        _ROUTE_AUDIT.set(tuple(audit_rows))
        return NativeDiscoveryBatch(
            items=items,
            logs=logs,
            fallback_sources=fallback_sources,
        )


def route_contract_summary(source: dict[str, Any]) -> str:
    """Stable JSON summary used by tests and audit tooling."""
    fixed = apply_v056_source_route(source)
    config = parse_parser_config(fixed)
    return json.dumps(
        {
            "source_id": fixed.get("source_id", ""),
            "route_version": config.get("route_version", ""),
            "target_lookback_days": config.get("target_lookback_days"),
            "metadata_limit_per_source": config.get("metadata_limit_per_source"),
            "section_urls": config.get("section_urls", []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


__all__ = [
    "NATIVE_ROUTE_VERSION",
    "TARGET_LOOKBACK_DAYS",
    "METADATA_LIMIT_PER_SOURCE",
    "EffectiveNativeRouteDiscovery",
    "apply_v056_source_route",
    "current_native_route_audit",
    "parse_effective_section_html",
    "reset_native_route_audit",
    "route_contract_summary",
    "select_sources_for_run_v056",
]
