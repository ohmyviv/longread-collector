"""Paired natural Chinese route Shadow discovery (S1).

Control native discovery remains authoritative.  When a naturally selected
Chinese source has a Treatment portfolio, this module performs first-party
metadata-only requests immediately after Control native discovery, records the
observations in a ContextVar, and returns the Control batch unchanged.

Treatment never calls Jina, Firecrawl, candidate selection or body extraction.
Any Treatment exception is fail-open and cannot fail the Control run.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import Counter, defaultdict
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import httpx
from dateutil import parser as date_parser

from .effective_route_extensions_v056 import EffectiveRouteDiscovery
from .models import DiscoveredURL
from .native_discovery import DEFAULT_USER_AGENT, NativeDiscoveryBatch, parse_feed
from .normalization import canonicalize_url
from .quality_aware_reserve_replay_v1 import tier1_micro_market_reason
from .zh_route_shadow_contracts_v1 import (
    ROUTE_SHADOW_CONTRACT_VERSION,
    S1_BODY_MODE,
    RouteSurface,
    SurfaceRole,
    active_s1_surfaces,
)

ROUTE_SHADOW_DISCOVERY_VERSION = "zh-route-shadow-discovery-v1"
_FIRST_PARTY_SUFFIX = {
    "yicai": "yicai.com",
    "eeo": "eeo.com.cn",
    "caixin": "caixin.com",
    "jiemian-depth": "jiemian.com",
}
_LISTING_PATH_RE = re.compile(
    r"/(?:lists?|tags?|account|author|authors|category|search|about|contact)(?:/|$)",
    re.I,
)
_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|news|detail|story|stories)/.+|"
    r"/20\d{2}(?:[-/]\d{1,2})?(?:[-/]\d{1,2})?/.+|"
    r"/[^/?#]+\.(?:s?html?)$",
    re.I,
)
_RELATIVE_CLOCK_RE = re.compile(
    r"(?P<day>今天|昨天)\s*(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)"
)
_YMD_CLOCK_RE = re.compile(
    r"(?P<y>20\d{2})[年\-/](?P<mo>0?[1-9]|1[0-2])[月\-/](?P<d>0?[1-9]|[12]\d|3[01])日?"
    r"(?:\s+(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d))?"
)
_MD_CLOCK_RE = re.compile(
    r"(?<!\d)(?P<mo>0?[1-9]|1[0-2])[/\-](?P<d>0?[1-9]|[12]\d|3[01])"
    r"(?:\s+(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d))"
)


@dataclass(slots=True)
class ShadowRouteItem:
    source_id: str
    surface_id: str
    surface_role: str
    publication_surface_id: str
    endpoint: str
    transport: str
    url: str
    url_canonical: str
    title: str
    published_at: str
    publication_time_source: str
    publication_time_confidence: str
    rank: int
    within_freshness: bool
    control_overlap: bool = False
    noise_reason: str = ""


@dataclass(slots=True)
class ShadowSurfaceObservation:
    source_id: str
    surface_id: str
    surface_role: str
    publication_surface_id: str
    endpoint: str
    transport: str
    observed_at_bj: str
    request_success: bool
    http_status: int | str
    parse_success: bool
    surface_status: str
    raw_item_count: int
    unique_item_count: int
    recent_item_count: int
    dated_item_count: int
    exact_timestamp_count: int
    oldest_published_at: str
    newest_published_at: str
    control_overlap_count: int
    treatment_unique_count: int
    noise_item_count: int
    noise_reason_counts: dict[str, int]
    request_latency_ms: int
    error_type: str = ""
    error_message: str = ""


@dataclass(slots=True)
class ZhRouteShadowReport:
    version: str
    contract_version: str
    body_mode: str
    group_id: str
    started_at_bj: str
    observed_at_bj: str
    selected_source_ids: list[str]
    treatment_source_ids: list[str]
    surfaces_attempted: int
    metadata_requests: int
    body_requests: int
    observations: list[ShadowSurfaceObservation] = field(default_factory=list)
    items: list[ShadowRouteItem] = field(default_factory=list)
    control_native_unique_count: int = 0
    treatment_unique_count: int = 0
    incremental_unique_count: int = 0
    status: str = "success"
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "contract_version": self.contract_version,
            "body_mode": self.body_mode,
            "group_id": self.group_id,
            "started_at_bj": self.started_at_bj,
            "observed_at_bj": self.observed_at_bj,
            "selected_source_ids": list(self.selected_source_ids),
            "treatment_source_ids": list(self.treatment_source_ids),
            "surfaces_attempted": self.surfaces_attempted,
            "metadata_requests": self.metadata_requests,
            "body_requests": self.body_requests,
            "control_native_unique_count": self.control_native_unique_count,
            "treatment_unique_count": self.treatment_unique_count,
            "incremental_unique_count": self.incremental_unique_count,
            "status": self.status,
            "error": self.error,
        }


@dataclass(slots=True)
class _ShadowState:
    enabled: bool
    group_id: str
    report: ZhRouteShadowReport | None = None
    error: str = ""


_STATE: ContextVar[_ShadowState | None] = ContextVar("zh_route_shadow_state", default=None)


def begin_zh_route_shadow(*, enabled: bool, group_id: str) -> Token:
    return _STATE.set(_ShadowState(enabled=bool(enabled), group_id=str(group_id or "all")))


def current_zh_route_shadow_state() -> _ShadowState | None:
    return _STATE.get()


def end_zh_route_shadow(token: Token) -> None:
    _STATE.reset(token)


class _EventParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        self._href = values.get("href", "")
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        text = " ".join(str(data or "").split())
        if not text:
            return
        if self._href is not None:
            self._anchor_text.append(text)
        else:
            self.events.append(("text", "", text))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = " ".join(" ".join(self._anchor_text).split())
        self.events.append(("anchor", self._href, title))
        self._href = None
        self._anchor_text = []


def _host_is_first_party(source_id: str, host: str) -> bool:
    suffix = _FIRST_PARTY_SUFFIX.get(source_id, "")
    value = str(host or "").lower().split(":", 1)[0]
    return bool(suffix) and (value == suffix or value.endswith("." + suffix))


def _articleish(surface: RouteSurface, url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not _host_is_first_party(surface.source_id, parts.netloc):
        return False
    if canonicalize_url(url) == canonicalize_url(surface.url):
        return False
    path = parts.path or "/"
    if _LISTING_PATH_RE.search(path):
        return False
    # Core/breadth routes must not silently absorb known non-editorial Caixin
    # products merely because they share the registrable domain.
    if surface.source_id == "caixin" and surface.role is not SurfaceRole.NOISE_CONTROL:
        if parts.netloc.lower().startswith(("promote.", "video.", "photos.", "conferences.")):
            return False
    if surface.source_id == "jiemian-depth" and re.search(r"/(?:jmedia|account|author)/", path, re.I):
        return False
    return bool(_ARTICLE_PATH_RE.search(path))


def _parse_context_time(text: str, observed_at: datetime) -> tuple[str, str, str]:
    relative = _RELATIVE_CLOCK_RE.search(text)
    if relative:
        day = observed_at.date() - (timedelta(days=1) if relative.group("day") == "昨天" else timedelta())
        value = datetime(
            day.year,
            day.month,
            day.day,
            int(relative.group("h")),
            int(relative.group("m")),
            tzinfo=observed_at.tzinfo,
        )
        if value <= observed_at:
            return value.isoformat(), "listing_relative_clock", "high"

    ymd = _YMD_CLOCK_RE.search(text)
    if ymd:
        hour = int(ymd.group("h") or 0)
        minute = int(ymd.group("m") or 0)
        value = datetime(
            int(ymd.group("y")), int(ymd.group("mo")), int(ymd.group("d")),
            hour, minute, tzinfo=observed_at.tzinfo,
        )
        if value <= observed_at + timedelta(minutes=5):
            confidence = "high" if ymd.group("h") else "date_only"
            source = "listing_absolute_clock" if ymd.group("h") else "listing_absolute_date"
            return value.isoformat() if ymd.group("h") else value.date().isoformat(), source, confidence

    md = _MD_CLOCK_RE.search(text)
    if md:
        year = observed_at.year
        value = datetime(
            year, int(md.group("mo")), int(md.group("d")), int(md.group("h")), int(md.group("m")),
            tzinfo=observed_at.tzinfo,
        )
        if value > observed_at + timedelta(days=1):
            value = value.replace(year=year - 1)
        if value <= observed_at + timedelta(minutes=5):
            return value.isoformat(), "listing_month_day_clock", "high"
    return "", "", ""


def _freshness_state(published_at: str, *, started: datetime, freshness_days: int) -> bool:
    text = str(published_at or "").strip()
    if not text:
        return True  # unknown date remains observable in S1; it is not promoted.
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=started.tzinfo)
    else:
        parsed = parsed.astimezone(started.tzinfo)
    return parsed >= started - timedelta(days=max(1, int(freshness_days)))


def _noise_reason(surface: RouteSurface, title: str) -> str:
    if surface.source_id == "yicai" and surface.surface_id == "yicai_commercial_control":
        return "commercial_surface"
    if surface.source_id == "caixin" and surface.surface_id == "caixin_promotion_control":
        return "commercial_surface"
    reason = tier1_micro_market_reason(title)
    if reason:
        return reason
    return ""


def parse_shadow_section_html(
    body: str,
    *,
    source: dict[str, Any],
    surface: RouteSurface,
    observed_at: datetime,
    freshness_days: int,
) -> list[ShadowRouteItem]:
    parser = _EventParser()
    parser.feed(body)
    raw: list[tuple[str, str]] = []
    contexts: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    seen: set[str] = set()

    for kind, href, text in parser.events:
        if kind == "anchor":
            url = urljoin(surface.url, href)
            if _articleish(surface, url) and len(text) >= 6:
                canonical = canonicalize_url(url)
                current = canonical
                if canonical not in seen:
                    seen.add(canonical)
                    raw.append((url, text))
                if len(raw) >= surface.max_items:
                    # Continue collecting nearby context for the final item but
                    # do not admit new article anchors beyond the surface quota.
                    continue
            elif current and text:
                contexts[current].append(text)
            continue
        if current and text:
            contexts[current].append(text)

    items: list[ShadowRouteItem] = []
    for rank, (url, title) in enumerate(raw[: surface.max_items], start=1):
        canonical = canonicalize_url(url)
        published_at, pub_source, confidence = _parse_context_time(
            " ".join(contexts.get(canonical, ())), observed_at
        )
        items.append(
            ShadowRouteItem(
                source_id=surface.source_id,
                surface_id=surface.surface_id,
                surface_role=surface.role.value,
                publication_surface_id=surface.publication_surface_id,
                endpoint=surface.url,
                transport=surface.transport,
                url=url,
                url_canonical=canonical,
                title=title,
                published_at=published_at,
                publication_time_source=pub_source,
                publication_time_confidence=confidence,
                rank=rank,
                within_freshness=_freshness_state(
                    published_at, started=observed_at, freshness_days=freshness_days
                ),
                noise_reason=_noise_reason(surface, title),
            )
        )
    return items


def parse_shadow_feed(
    body: str,
    *,
    source: dict[str, Any],
    surface: RouteSurface,
    observed_at: datetime,
    freshness_days: int,
) -> list[ShadowRouteItem]:
    feed_source = dict(source)
    feed_source["source_id"] = surface.source_id
    # Parse a long horizon on purpose so a HTTP-200 but stale official feed can
    # be diagnosed as stale instead of looking like an empty healthy route.
    parsed = parse_feed(
        body,
        source=feed_source,
        endpoint=surface.url,
        limit=surface.max_items,
        started=observed_at,
        freshness_days=3650,
    )
    items: list[ShadowRouteItem] = []
    for rank, item in enumerate(parsed, start=1):
        published = str(item.published_at or "").strip()
        items.append(
            ShadowRouteItem(
                source_id=surface.source_id,
                surface_id=surface.surface_id,
                surface_role=surface.role.value,
                publication_surface_id=surface.publication_surface_id,
                endpoint=surface.url,
                transport=surface.transport,
                url=item.url,
                url_canonical=canonicalize_url(item.url),
                title=item.title,
                published_at=published,
                publication_time_source="rss_pubdate" if published else "",
                publication_time_confidence="high" if published else "",
                rank=rank,
                within_freshness=_freshness_state(
                    published, started=observed_at, freshness_days=freshness_days
                ),
                noise_reason=_noise_reason(surface, item.title),
            )
        )
    return items


def _surface_status(items: list[ShadowRouteItem], *, request_success: bool) -> str:
    if not request_success:
        return "request_failed"
    if not items:
        return "empty"
    dated = [item for item in items if item.published_at]
    if dated and not any(item.within_freshness for item in dated):
        return "stale_surface"
    if not dated:
        return "date_unknown"
    return "observed"


def _published_bounds(items: list[ShadowRouteItem]) -> tuple[str, str]:
    values: list[datetime] = []
    for item in items:
        if not item.published_at:
            continue
        try:
            parsed = date_parser.parse(item.published_at)
        except (TypeError, ValueError, OverflowError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        values.append(parsed)
    if not values:
        return "", ""
    return min(values).isoformat(), max(values).isoformat()


async def _observe_surface(
    client: httpx.AsyncClient,
    source: dict[str, Any],
    surface: RouteSurface,
    *,
    observed_at: datetime,
    freshness_days: int,
    control_urls: set[str],
) -> tuple[ShadowSurfaceObservation, list[ShadowRouteItem]]:
    started_clock = time.perf_counter()
    status: int | str = ""
    error_type = ""
    error_message = ""
    request_success = False
    parse_success = False
    items: list[ShadowRouteItem] = []
    try:
        response = await client.get(surface.url, follow_redirects=True)
        status = response.status_code
        response.raise_for_status()
        request_success = True
        if surface.transport == "rss":
            items = parse_shadow_feed(
                response.text,
                source=source,
                surface=surface,
                observed_at=observed_at,
                freshness_days=freshness_days,
            )
        else:
            items = parse_shadow_section_html(
                response.text,
                source=source,
                surface=surface,
                observed_at=observed_at,
                freshness_days=freshness_days,
            )
        parse_success = True
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)[:500]

    unique: dict[str, ShadowRouteItem] = {}
    for item in items:
        item.control_overlap = item.url_canonical in control_urls
        unique.setdefault(item.url_canonical, item)
    items = list(unique.values())
    oldest, newest = _published_bounds(items)
    noise_counts = Counter(item.noise_reason for item in items if item.noise_reason)
    observation = ShadowSurfaceObservation(
        source_id=surface.source_id,
        surface_id=surface.surface_id,
        surface_role=surface.role.value,
        publication_surface_id=surface.publication_surface_id,
        endpoint=surface.url,
        transport=surface.transport,
        observed_at_bj=observed_at.strftime("%Y-%m-%d %H:%M:%S"),
        request_success=request_success,
        http_status=status,
        parse_success=parse_success,
        surface_status=_surface_status(items, request_success=request_success),
        raw_item_count=len(items),
        unique_item_count=len(items),
        recent_item_count=sum(item.within_freshness for item in items),
        dated_item_count=sum(bool(item.published_at) for item in items),
        exact_timestamp_count=sum(
            item.publication_time_confidence == "high" for item in items
        ),
        oldest_published_at=oldest,
        newest_published_at=newest,
        control_overlap_count=sum(item.control_overlap for item in items),
        treatment_unique_count=sum(not item.control_overlap for item in items),
        noise_item_count=sum(bool(item.noise_reason) for item in items),
        noise_reason_counts=dict(noise_counts),
        request_latency_ms=int((time.perf_counter() - started_clock) * 1000),
        error_type=error_type,
        error_message=error_message,
    )
    return observation, items


async def discover_treatment_metadata(
    sources: list[dict[str, Any]],
    *,
    control_items: list[DiscoveredURL],
    group_id: str,
    started: datetime,
    freshness_days: int,
    timeout: float,
    concurrency: int,
) -> ZhRouteShadowReport:
    selected_ids = [str(source.get("source_id", "") or "") for source in sources]
    treatment_sources = [source for source in sources if active_s1_surfaces(str(source.get("source_id", "")))]
    surfaces = [
        (source, surface)
        for source in treatment_sources
        for surface in active_s1_surfaces(str(source.get("source_id", "")))
    ]
    observed_at = datetime.now(started.tzinfo or ZoneInfo("Asia/Shanghai"))
    control_urls = {canonicalize_url(item.url) for item in control_items}

    if not surfaces:
        return ZhRouteShadowReport(
            version=ROUTE_SHADOW_DISCOVERY_VERSION,
            contract_version=ROUTE_SHADOW_CONTRACT_VERSION,
            body_mode=S1_BODY_MODE,
            group_id=group_id,
            started_at_bj=started.strftime("%Y-%m-%d %H:%M:%S"),
            observed_at_bj=observed_at.strftime("%Y-%m-%d %H:%M:%S"),
            selected_source_ids=selected_ids,
            treatment_source_ids=[],
            surfaces_attempted=0,
            metadata_requests=0,
            body_requests=0,
            control_native_unique_count=len(control_urls),
            status="no_treatment_source_selected",
        )

    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    limits = httpx.Limits(
        max_connections=max(1, min(int(concurrency), 8)),
        max_keepalive_connections=max(1, min(int(concurrency), 6)),
    )
    semaphore = asyncio.Semaphore(max(1, min(int(concurrency), 8)))
    async with httpx.AsyncClient(headers=headers, limits=limits, timeout=float(timeout)) as client:
        async def one(source: dict[str, Any], surface: RouteSurface):
            async with semaphore:
                return await _observe_surface(
                    client,
                    source,
                    surface,
                    observed_at=observed_at,
                    freshness_days=freshness_days,
                    control_urls=control_urls,
                )

        results = await asyncio.gather(*(one(source, surface) for source, surface in surfaces))

    observations = [result[0] for result in results]
    items = [item for _, group in results for item in group]
    treatment_urls = {item.url_canonical for item in items if item.within_freshness}
    return ZhRouteShadowReport(
        version=ROUTE_SHADOW_DISCOVERY_VERSION,
        contract_version=ROUTE_SHADOW_CONTRACT_VERSION,
        body_mode=S1_BODY_MODE,
        group_id=group_id,
        started_at_bj=started.strftime("%Y-%m-%d %H:%M:%S"),
        observed_at_bj=observed_at.strftime("%Y-%m-%d %H:%M:%S"),
        selected_source_ids=selected_ids,
        treatment_source_ids=[str(source.get("source_id", "")) for source in treatment_sources],
        surfaces_attempted=len(surfaces),
        metadata_requests=len(surfaces),
        body_requests=0,
        observations=observations,
        items=items,
        control_native_unique_count=len(control_urls),
        treatment_unique_count=len(treatment_urls),
        incremental_unique_count=len(treatment_urls - control_urls),
        status="success",
    )


class PairedZhRouteShadowDiscovery(EffectiveRouteDiscovery):
    """Return Control discovery unchanged while observing Treatment metadata."""

    async def discover(
        self,
        sources: list[dict[str, Any]],
        *,
        limit_per_source: int,
        started: datetime,
        freshness_days: int,
    ) -> NativeDiscoveryBatch:
        control = await super().discover(
            sources,
            limit_per_source=limit_per_source,
            started=started,
            freshness_days=freshness_days,
        )
        state = current_zh_route_shadow_state()
        if (
            state is None
            or not state.enabled
            or not state.group_id.startswith("zh_")
        ):
            return control
        try:
            state.report = await discover_treatment_metadata(
                sources,
                control_items=control.items,
                group_id=state.group_id,
                started=started,
                freshness_days=freshness_days,
                timeout=self.timeout,
                concurrency=self.concurrency,
            )
        except Exception as exc:  # fail-open by contract
            state.error = f"{type(exc).__name__}: {exc}"[:1000]
        return control


def install_paired_zh_route_shadow_discovery() -> None:
    """Install only the metadata sidecar class used by v0.6 Shadow runtime."""
    from . import pipeline_v05 as _pipeline_v05

    current = _pipeline_v05.NativeSourceDiscovery
    if current is PairedZhRouteShadowDiscovery:
        return
    _pipeline_v05.NativeSourceDiscovery = PairedZhRouteShadowDiscovery


__all__ = [
    "ROUTE_SHADOW_DISCOVERY_VERSION",
    "PairedZhRouteShadowDiscovery",
    "ShadowRouteItem",
    "ShadowSurfaceObservation",
    "ZhRouteShadowReport",
    "begin_zh_route_shadow",
    "current_zh_route_shadow_state",
    "discover_treatment_metadata",
    "end_zh_route_shadow",
    "install_paired_zh_route_shadow_discovery",
    "parse_shadow_feed",
    "parse_shadow_section_html",
]
