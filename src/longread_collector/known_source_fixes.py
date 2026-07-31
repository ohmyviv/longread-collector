from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .native_discovery import (
    NativeDiscoveryLog,
    NativeSourceDiscovery,
    _clean_text,
    _make_item,
    select_sources_for_run as _base_select_sources_for_run,
)
from .normalization import canonicalize_url

READER_LINK_RE = re.compile(r"\[([^\]\n]{2,300})\]\((https?://[^)\s]+)\)")
READER_IMAGE_LINK_RE = re.compile(
    r"\[!\[[^\]]*\]\([^)]+\)\]\((https?://[^)\s]+)\)"
)


def _parser_config(source: dict[str, Any]) -> dict[str, Any]:
    raw = source.get("parser_config_json")
    if isinstance(raw, dict):
        return deepcopy(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def apply_known_source_fix(source: dict[str, Any]) -> dict[str, Any]:
    """Apply narrowly scoped, validated endpoint corrections at runtime."""
    item = deepcopy(source)
    source_id = str(item.get("source_id", ""))
    config = _parser_config(item)
    config.setdefault(
        "fallback_order",
        ["rss", "news_sitemap", "sitemap", "section_scan", "firecrawl_search"],
    )

    if source_id == "jiemian-depth":
        config["section_urls"] = ["https://www.jiemian.com/lists/423.html"]
        item["notes"] = "v0.5.1: corrected current Jiemian Depth section endpoint"
    elif source_id == "knowable":
        item["homepage_url"] = "https://www.knowablemagazine.org/"
        item["rss_url"] = "https://www.knowablemagazine.org/rss"
        item["notes"] = "v0.5.1: corrected official Knowable RSS endpoint"
    elif source_id == "deeptech":
        item["homepage_url"] = "https://www.mittrchina.com/"
        config["section_urls"] = ["https://www.mittrchina.com/news"]
        item["discovery_method"] = ["section_scan", "firecrawl_search"]
        item["notes"] = (
            "v0.5.1: legacy domain migrated to MITTR China; "
            "use Jina reader section fallback when the JS shell has no links"
        )
    elif source_id == "inside-climate-news":
        # The official feed, news page, WordPress API and Jina reader path all
        # return anti-bot pages to GitHub-hosted runners. Avoid repeated failed
        # requests and retain the existing bounded Firecrawl domain search.
        item["discovery_method"] = ["firecrawl_search"]
        config["fallback_order"] = ["firecrawl_search"]
        item["notes"] = (
            "v0.5.1: official native endpoints blocked for GitHub runners; "
            "retain bounded Firecrawl search fallback"
        )

    config.setdefault("section_urls", [])
    item["parser_config_json"] = config
    return item


def apply_known_source_fixes(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_known_source_fix(source) for source in sources]


def select_sources_for_run(
    sources: list[dict[str, Any]],
    *,
    started: datetime,
    max_sources: int,
    rotate_share: float = 0.75,
) -> list[dict[str, Any]]:
    return _base_select_sources_for_run(
        apply_known_source_fixes(sources),
        started=started,
        max_sources=max_sources,
        rotate_share=rotate_share,
    )


def parse_reader_section(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    limit: int,
) -> list[Any]:
    """Extract same-domain article links from Jina Reader markdown."""
    domain = urlsplit(str(source.get("homepage_url", ""))).netloc.lower().removeprefix(
        "www."
    )
    candidates: list[tuple[str, str]] = []
    for match in READER_LINK_RE.finditer(body or ""):
        title = _clean_text(match.group(1))
        url = match.group(2).strip()
        candidates.append((title, url))
    for match in READER_IMAGE_LINK_RE.finditer(body or ""):
        candidates.append(("", match.group(1).strip()))

    items = []
    seen: set[str] = set()
    for title, url in candidates:
        parts = urlsplit(url)
        candidate_domain = parts.netloc.lower().removeprefix("www.")
        if candidate_domain != domain:
            continue
        if source.get("source_id") == "deeptech" and "/news/detail/" not in parts.path:
            continue
        if len(title) < 6 or title.lower().startswith(("image ", "logo")):
            continue
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        items.append(
            _make_item(
                source=source,
                method="reader_section",
                endpoint=endpoint,
                url=url,
                title=title,
                rank=len(items) + 1,
            )
        )
        if len(items) >= limit:
            break
    return items


class KnownFallbackAwareDiscovery(NativeSourceDiscovery):
    """Native discovery with validated repairs for the four initial fallbacks."""

    async def discover_source(
        self,
        client: httpx.AsyncClient,
        source: dict[str, Any],
        *,
        limit: int,
        started: datetime,
        freshness_days: int,
    ):
        source = apply_known_source_fix(source)
        source_id = str(source.get("source_id", ""))

        if source_id == "inside-climate-news":
            return [], NativeDiscoveryLog(
                source_id=source_id,
                source_name=str(source.get("source_name", "")),
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
                    "Official feed, archive, API and reader endpoints were validated "
                    "as blocked; use bounded Firecrawl fallback"
                ),
            )

        items, log = await super().discover_source(
            client,
            source,
            limit=limit,
            started=started,
            freshness_days=freshness_days,
        )
        if items or source_id != "deeptech":
            return items, log

        endpoint = "https://r.jina.ai/http://www.mittrchina.com/news"
        attempt: dict[str, Any] = {"method": "reader_section", "endpoint": endpoint}
        try:
            response = await self._get(client, endpoint)
            reader_items = parse_reader_section(
                response.text,
                source=source,
                endpoint=endpoint,
                limit=limit,
            )
            attempt.update(
                {
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                    "results_count": len(reader_items),
                }
            )
            attempts = list(log.attempts) + [attempt]
            if reader_items:
                return reader_items, NativeDiscoveryLog(
                    source_id=source_id,
                    source_name=str(source.get("source_name", "")),
                    success=True,
                    selected_method="reader_section",
                    selected_endpoint=endpoint,
                    results_count=len(reader_items),
                    attempts=attempts,
                )
            log.attempts = attempts
        except Exception as exc:
            attempt.update(
                {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                }
            )
            log.attempts = list(log.attempts) + [attempt]
            log.error_type = type(exc).__name__
            log.error_message = str(exc)[:300]
        return [], log


async def probe_known_sources(
    sources: list[dict[str, Any]],
    *,
    timeout: float = 15.0,
    limit_per_source: int = 6,
    freshness_days: int = 3,
) -> dict[str, Any]:
    selected_ids = {
        "jiemian-depth",
        "deeptech",
        "knowable",
        "inside-climate-news",
    }
    selected = [source for source in apply_known_source_fixes(sources) if source.get("source_id") in selected_ids]
    discovery = KnownFallbackAwareDiscovery(timeout=timeout, concurrency=4)
    batch = await discovery.discover(
        selected,
        limit_per_source=limit_per_source,
        started=datetime.now(),
        freshness_days=freshness_days,
    )
    return {
        "sources_attempted": len(selected),
        "native_successes": sum(bool(log.get("success")) for log in batch.logs),
        "fallback_sources": [
            str(log.get("source_id", ""))
            for log in batch.logs
            if log.get("fallback_needed")
        ],
        "items_discovered": len(batch.items),
        "logs": batch.logs,
    }
