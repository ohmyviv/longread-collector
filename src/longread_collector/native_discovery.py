from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

import httpx
from dateutil import parser as date_parser

from .models import DiscoveredURL
from .normalization import canonicalize_url

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; LongreadCollector/0.5; "
    "+https://github.com/ohmyviv/longread-collector)"
)
ARTICLE_PATH_RE = re.compile(
    r"/(?:20\d{2}|article|articles|news|story|stories|detail|content|feature|features|"
    r"magazine|investigates|depth|opinion|essay|report|reports)/",
    re.IGNORECASE,
)
NON_ARTICLE_PATH_RE = re.compile(
    r"/(?:login|signin|subscribe|account|author|authors|tag|tags|category|categories|"
    r"search|about|contact|privacy|terms)(?:/|$)",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class NativeDiscoveryLog:
    source_id: str
    source_name: str
    success: bool
    selected_method: str = ""
    selected_endpoint: str = ""
    results_count: int = 0
    fallback_needed: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)
    error_type: str = ""
    error_message: str = ""
    credits_used: int = 0
    purpose: str = "native_source_scan"


@dataclass(slots=True)
class NativeDiscoveryBatch:
    items: list[DiscoveredURL]
    logs: list[dict[str, Any]]
    fallback_sources: list[dict[str, Any]]


def _bool(value: Any) -> bool:
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _source_domain(source: dict[str, Any]) -> str:
    return urlsplit(str(source.get("homepage_url", ""))).netloc.lower().removeprefix("www.")


def _parse_last_scanned(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed.replace(tzinfo=None)


def select_sources_for_run(
    sources: list[dict[str, Any]],
    *,
    started: datetime,
    max_sources: int,
    rotate_share: float = 0.75,
) -> list[dict[str, Any]]:
    """Select least-recently-scanned sources with tier quotas and same-day avoidance."""
    if max_sources <= 0:
        return []
    enabled = [
        source
        for source in sources
        if str(source.get("priority_tier", "")).strip() != "monitor"
        and source.get("enabled", True) is not False
        and str(source.get("enabled", "TRUE")).strip().upper() not in {"FALSE", "0", "NO", "N"}
    ]
    if not enabled:
        return []

    today = started.replace(tzinfo=None).date()

    def sort_key(source: dict[str, Any]) -> tuple[datetime, str]:
        scanned = _parse_last_scanned(source.get("last_scanned_at_bj"))
        return (scanned or datetime.min, str(source.get("source_id", "")))

    not_today = [
        source
        for source in enabled
        if (_parse_last_scanned(source.get("last_scanned_at_bj")) or datetime.min).date() != today
    ]
    pool = not_today if len(not_today) >= min(max_sources, len(enabled)) else enabled
    rotate = sorted(
        [source for source in pool if str(source.get("priority_tier", "")).strip() == "rotate"],
        key=sort_key,
    )
    explore = sorted(
        [source for source in pool if str(source.get("priority_tier", "")).strip() != "rotate"],
        key=sort_key,
    )

    rotate_quota = min(len(rotate), max(1, round(max_sources * rotate_share)))
    explore_quota = min(len(explore), max_sources - rotate_quota)
    selected = rotate[:rotate_quota] + explore[:explore_quota]
    selected_ids = {str(source.get("source_id", "")) for source in selected}
    remaining = sorted(
        [source for source in pool if str(source.get("source_id", "")) not in selected_ids],
        key=lambda source: (
            0 if str(source.get("priority_tier", "")).strip() == "rotate" else 1,
            *sort_key(source),
        ),
    )
    selected.extend(remaining[: max(0, max_sources - len(selected))])
    return selected[:max_sources]


def parse_parser_config(source: dict[str, Any]) -> dict[str, Any]:
    raw = source.get("parser_config_json")
    if isinstance(raw, dict):
        parsed = dict(raw)
    else:
        try:
            parsed = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
    parsed.setdefault(
        "fallback_order",
        ["rss", "news_sitemap", "sitemap", "section_scan", "firecrawl_search"],
    )
    parsed.setdefault("section_urls", [])
    parsed.setdefault("section_allowed_subdomains", [])
    return parsed


def _method_endpoints(source: dict[str, Any], method: str) -> list[str]:
    if method in {"rss", "atom"}:
        values = [str(source.get("rss_url", "")).strip()]
    elif method == "news_sitemap":
        values = [str(source.get("news_sitemap_url", "")).strip()]
    elif method == "sitemap":
        values = [str(source.get("sitemap_url", "")).strip()]
    elif method in {"section_scan", "homepage"}:
        config = parse_parser_config(source)
        values = [str(value).strip() for value in config.get("section_urls", [])]
        if method == "homepage" or not values:
            values.append(str(source.get("homepage_url", "")).strip())
    else:
        values = []
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return _clean_text("".join(element.itertext()))


def _find_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for child in element.iter():
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in names:
            text = _element_text(child)
            if text:
                return text
    return ""


def _parse_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = date_parser.parse(text)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _fresh_enough(value: str, *, started: datetime, freshness_days: int) -> bool:
    parsed = _parse_date(value)
    if parsed is None:
        return True
    return parsed >= started.replace(tzinfo=None) - timedelta(days=max(freshness_days, 1))


def _make_item(
    *,
    source: dict[str, Any],
    method: str,
    endpoint: str,
    url: str,
    title: str = "",
    description: str = "",
    published_at: str = "",
    rank: int = 0,
) -> DiscoveredURL:
    source_id = str(source.get("source_id", ""))
    source_name = str(source.get("source_name", ""))
    return DiscoveredURL(
        url=url,
        title=_clean_text(title),
        description=_clean_text(description),
        published_at=str(published_at or "").strip(),
        discovery_method=method,
        query_or_source=f"source:{source_id}",
        language=str(source.get("language", "")),
        rank=rank,
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_name,
            "native_method": method,
            "native_endpoint": endpoint,
            "priority_tier": str(source.get("priority_tier", "")),
        },
    )


def parse_feed(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
    started: datetime,
    freshness_days: int,
) -> list[DiscoveredURL]:
    root = ET.fromstring(body)
    entries = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1].lower() in {"item", "entry"}]
    items: list[DiscoveredURL] = []
    seen: set[str] = set()
    for entry in entries:
        link = ""
        for child in entry.iter():
            if child.tag.rsplit("}", 1)[-1].lower() != "link":
                continue
            candidate = str(child.attrib.get("href") or child.text or "").strip()
            rel = str(child.attrib.get("rel") or "alternate").lower()
            if candidate and rel in {"", "alternate"}:
                link = candidate
                break
        if not link:
            link = _find_text(entry, ("guid",))
        link = urljoin(endpoint, link)
        if not link.startswith(("http://", "https://")):
            continue
        canonical = canonicalize_url(link)
        if canonical in seen:
            continue
        published = _find_text(entry, ("pubdate", "published", "updated", "date"))
        if not _fresh_enough(published, started=started, freshness_days=freshness_days):
            continue
        seen.add(canonical)
        items.append(
            _make_item(
                source=source,
                method="rss",
                endpoint=endpoint,
                url=link,
                title=_find_text(entry, ("title",)),
                description=_find_text(entry, ("description", "summary", "content", "encoded")),
                published_at=published,
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items


def parse_sitemap(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
    started: datetime,
    freshness_days: int,
    method: str,
) -> tuple[list[DiscoveredURL], list[str]]:
    root = ET.fromstring(body)
    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name == "sitemapindex":
        child_urls = []
        for element in root:
            loc = _find_text(element, ("loc",))
            if loc:
                child_urls.append(loc)
        return [], child_urls[:5]

    items: list[DiscoveredURL] = []
    seen: set[str] = set()
    for element in root:
        if element.tag.rsplit("}", 1)[-1].lower() != "url":
            continue
        loc = _find_text(element, ("loc",))
        if not loc.startswith(("http://", "https://")):
            continue
        canonical = canonicalize_url(loc)
        if canonical in seen:
            continue
        lastmod = _find_text(element, ("lastmod", "publication_date"))
        if not _fresh_enough(lastmod, started=started, freshness_days=freshness_days):
            continue
        seen.add(canonical)
        items.append(
            _make_item(
                source=source,
                method=method,
                endpoint=endpoint,
                url=loc,
                title=_find_text(element, ("title",)),
                published_at=lastmod,
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items, []


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


def _normalize_allowed_host(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        host = urlsplit(text).netloc.lower()
    else:
        host = text.split("/", 1)[0]
    return host.removeprefix("www.")


def _section_allowed_subdomains(source: dict[str, Any]) -> set[str]:
    domain = _source_domain(source)
    if not domain:
        return set()
    raw = parse_parser_config(source).get("section_allowed_subdomains", [])
    if isinstance(raw, str):
        values = [
            value.strip()
            for value in raw.replace(",", "|").split("|")
            if value.strip()
        ]
    elif isinstance(raw, (list, tuple, set)):
        values = [str(value).strip() for value in raw if str(value).strip()]
    else:
        values = []
    allowed: set[str] = set()
    for value in values:
        host = _normalize_allowed_host(value)
        if host and host != domain and host.endswith(f".{domain}"):
            allowed.add(host)
    return allowed


def _section_candidate_domain_allowed(
    source: dict[str, Any],
    candidate_domain: str,
) -> bool:
    domain = _source_domain(source)
    candidate = str(candidate_domain or "").lower().removeprefix("www.")
    if not domain or not candidate:
        return False
    if candidate == domain:
        return True
    return candidate in _section_allowed_subdomains(source)


def parse_section_html(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
) -> list[DiscoveredURL]:
    parser = _AnchorParser()
    parser.feed(body)
    items: list[DiscoveredURL] = []
    seen: set[str] = set()
    for href, title in parser.links:
        url = urljoin(endpoint, href)
        parts = urlsplit(url)
        candidate_domain = parts.netloc.lower().removeprefix("www.")
        if parts.scheme not in {"http", "https"} or not _section_candidate_domain_allowed(
            source, candidate_domain
        ):
            continue
        path = parts.path or "/"
        if NON_ARTICLE_PATH_RE.search(path):
            continue
        if not ARTICLE_PATH_RE.search(path) and len([part for part in path.split("/") if part]) < 2:
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


class NativeSourceDiscovery:
    def __init__(self, *, timeout: float = 15.0, concurrency: int = 10) -> None:
        self.timeout = timeout
        self.concurrency = max(concurrency, 1)

    async def _get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        response = await client.get(url, follow_redirects=True, timeout=self.timeout)
        response.raise_for_status()
        return response

    async def discover_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
        *,
        limit: int,
        started: datetime,
        freshness_days: int,
    ) -> tuple[list[DiscoveredURL], NativeDiscoveryLog]:
        source_id = str(source.get("source_id", ""))
        source_name = str(source.get("source_name", ""))
        config = parse_parser_config(source)
        methods = [str(value) for value in config.get("fallback_order", [])]
        declared = source.get("discovery_method") or []
        if isinstance(declared, str):
            declared = [value.strip() for value in declared.split("|") if value.strip()]
        attempts: list[dict[str, Any]] = []
        last_error: Exception | None = None

        for method in methods:
            if method == "firecrawl_search":
                break
            if method not in declared and method not in {"news_sitemap", "sitemap", "section_scan"}:
                continue
            endpoints = _method_endpoints(source, method)
            for endpoint in endpoints:
                attempt: dict[str, Any] = {"method": method, "endpoint": endpoint}
                try:
                    response = await self._get(client, endpoint)
                    attempt["http_status"] = response.status_code
                    attempt["content_type"] = response.headers.get("content-type", "")
                    if method in {"rss", "atom"}:
                        items = parse_feed(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=limit,
                            started=started,
                            freshness_days=freshness_days,
                        )
                    elif method in {"news_sitemap", "sitemap"}:
                        items, child_sitemaps = parse_sitemap(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=limit,
                            started=started,
                            freshness_days=freshness_days,
                            method=method,
                        )
                        for child_url in child_sitemaps:
                            if len(items) >= limit:
                                break
                            child_response = await self._get(client, child_url)
                            child_items, _ = parse_sitemap(
                                child_response.text,
                                source=source,
                                endpoint=child_url,
                                limit=limit - len(items),
                                started=started,
                                freshness_days=freshness_days,
                                method=method,
                            )
                            items.extend(child_items)
                    elif method in {"section_scan", "homepage"}:
                        items = parse_section_html(
                            response.text,
                            source=source,
                            endpoint=endpoint,
                            limit=limit,
                        )
                    else:
                        items = []
                    attempt["results_count"] = len(items)
                    attempts.append(attempt)
                    if items:
                        return items, NativeDiscoveryLog(
                            source_id=source_id,
                            source_name=source_name,
                            success=True,
                            selected_method=method,
                            selected_endpoint=endpoint,
                            results_count=len(items),
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
            error_message=str(last_error)[:300] if last_error else "No native endpoint returned article URLs",
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

            output = await asyncio.gather(*(one(source) for source in sources))

        items: list[DiscoveredURL] = []
        logs: list[dict[str, Any]] = []
        fallback_sources: list[dict[str, Any]] = []
        source_by_id = {str(source.get("source_id", "")): source for source in sources}
        for discovered, log in output:
            items.extend(discovered)
            logs.append(
                {
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
                }
            )
            if log.fallback_needed and log.source_id in source_by_id:
                fallback_sources.append(source_by_id[log.source_id])
        return NativeDiscoveryBatch(items=items, logs=logs, fallback_sources=fallback_sources)
