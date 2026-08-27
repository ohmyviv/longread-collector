"""Paired natural Chinese route Shadow discovery (S1).

Control native discovery is authoritative. Treatment performs only first-party
metadata requests immediately after Control native discovery, never enters
selection/extraction, and fails open. Unknown dates remain observable but do not
count as proven-recent coverage.
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
DIAGNOSTIC_RSS_HORIZON_DAYS = 36500
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
    r"(?P<y>20\d{2})[年\-/](?P<mo>0?[1-9]|1[0-2])[月\-/]"
    r"(?P<d>0?[1-9]|[12]\d|3[01])日?"
    r"(?:\s+(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d))?"
)
_MD_CLOCK_RE = re.compile(
    r"(?<!\d)(?P<mo>0?[1-9]|1[0-2])[/\-](?P<d>0?[1-9]|[12]\d|3[01])"
    r"\s+(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)"
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


_STATE: ContextVar[_ShadowState | None] = ContextVar(
    "zh_route_shadow_state", default=None
)


def begin_zh_route_shadow(*, enabled: bool, group_id: str) -> Token:
    return _STATE.set(
        _ShadowState(enabled=bool(enabled), group_id=str(group_id or "all"))
    )


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

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
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
        self.events.append(
            ("anchor", self._href, " ".join(" ".join(self._anchor_text).split()))
        )
        self._href = None
        self._anchor_text = []


def _host_is_first_party(source_id: str, host: str) -> bool:
    suffix = _FIRST_PARTY_SUFFIX.get(source_id, "")
    value = str(host or "").lower().split(":", 1)[0]
    return bool(suffix) and (value == suffix or value.endswith("." + suffix))


def _articleish(surface: RouteSurface, url: str) -> bool:
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not _host_is_first_party(surface.source_id, parts.netloc)
        or canonicalize_url(url) == canonicalize_url(surface.url)
    ):
        return False
    path = parts.path or "/"
    if _LISTING_PATH_RE.search(path):
        return False
    if surface.source_id == "caixin" and surface.role is not SurfaceRole.NOISE_CONTROL:
        if parts.netloc.lower().startswith(
            ("promote.", "video.", "photos.", "conferences.")
        ):
            return False
    if surface.source_id == "jiemian-depth" and re.search(
        r"/(?:jmedia|account|author)/", path, re.I
    ):
        return False
    return bool(_ARTICLE_PATH_RE.search(path))


def _parse_context_time(
    text: str, observed_at: datetime
) -> tuple[str, str, str]:
    match = _RELATIVE_CLOCK_RE.search(text)
    if match:
        day = observed_at.date() - (
            timedelta(days=1) if match.group("day") == "昨天" else timedelta()
        )
        value = datetime(
            day.year,
            day.month,
            day.day,
            int(match.group("h")),
            int(match.group("m")),
            tzinfo=observed_at.tzinfo,
        )
        if value <= observed_at:
            return value.isoformat(), "listing_relative_clock", "high"

    match = _YMD_CLOCK_RE.search(text)
    if match:
        value = datetime(
            int(match.group("y")),
            int(match.group("mo")),
            int(match.group("d")),
            int(match.group("h") or 0),
            int(match.group("m") or 0),
            tzinfo=observed_at.tzinfo,
        )
        if value <= observed_at + timedelta(minutes=5):
            if match.group("h"):
                return value.isoformat(), "listing_absolute_clock", "high"
            return value.date().isoformat(), "listing_absolute_date", "date_only"

    match = _MD_CLOCK_RE.search(text)
    if match:
        value = datetime(
            observed_at.year,
            int(match.group("mo")),
            int(match.group("d")),
            int(match.group("h")),
            int(match.group("m")),
            tzinfo=observed_at.tzinfo,
        )
        if value > observed_at + timedelta(days=1):
            value = value.replace(year=observed_at.year - 1)
        if value <= observed_at + timedelta(minutes=5):
            return value.isoformat(), "listing_month_day_clock", "high"
    return "", "", ""


def _freshness_state(
    published_at: str, *, started: datetime, freshness_days: int
) -> bool:
    text = str(published_at or "").strip()
    if not text:
        return False
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=started.tzinfo)
    else:
        parsed = parsed.astimezone(started.tzinfo)
    return (
        started - timedelta(days=max(1, int(freshness_days)))
        <= parsed
        <= started + timedelta(minutes=5)
    )


def _noise_reason(surface: RouteSurface, title: str) -> str:
    if surface.surface_id in {"yicai_commercial_control", "caixin_promotion_control"}:
        return "commercial_surface"
    return tier1_micro_market_reason(title)


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
    admitted: list[tuple[str, str]] = []
    contexts: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    seen: set[str] = set()

    for kind, href, text in parser.events:
        if kind == "anchor":
            url = urljoin(surface.url, href)
            if _articleish(surface, url) and len(text) >= 6:
                canonical = canonicalize_url(url)
                if canonical not in seen and len(admitted) < surface.max_items:
                    seen.add(canonical)
                    admitted.append((url, text))
                    current = canonical
                elif canonical in seen:
                    current = canonical
                else:
                    current = None
                continue
            if current and text:
                contexts[current].append(text)
            continue
        if current and text:
            contexts[current].append(text)

    result: list[ShadowRouteItem] = []
    for rank, (url, title) in enumerate(admitted, start=1):
        canonical = canonicalize_url(url)
        published, source_name, confidence = _parse_context_time(
            " ".join(contexts.get(canonical, ())), observed_at
        )
        result.append(
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
                published_at=published,
                publication_time_source=source_name,
                publication_time_confidence=confidence,
                rank=rank,
                within_freshness=_freshness_state(
                    published,
                    started=observed_at,
                    freshness_days=freshness_days,
                ),
                noise_reason=_noise_reason(surface, title),
            )
        )
    return result


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
    # Parse far beyond the operational window so old-but-reachable feeds are
    # explicitly classified stale rather than collapsing into an empty route.
    parsed = parse_feed(
        body,
        source=feed_source,
        endpoint=surface.url,
        limit=surface.max_items,
        started=observed_at,
        freshness_days=DIAGNOSTIC_RSS_HORIZON_DAYS,
    )
    result: list[ShadowRouteItem] = []
    for rank, item in enumerate(parsed, start=1):
        published = str(item.published_at or "").strip()
        result.append(
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
                    published,
                    started=observed_at,
                    freshness_days=freshness_days,
                ),
                noise_reason=_noise_reason(surface, item.title),
            )
        )
    return result


def _surface_status(
    items: list[ShadowRouteItem], *, request_success: bool
) -> str:
    if not request_success:
        return "request_failed"
    if not items:
        return "empty"
    dated = [item for item in items if item.published_at]
    if not dated:
        return "date_unknown"
    if not any(item.within_freshness for item in dated):
        return "stale_surface"
    return "observed"


def _published_bounds(items: list[ShadowRouteItem]) -> tuple[str, str]:
    parsed_values: list[datetime] = []
    for item in items:
        if not item.published_at:
            continue
        try:
            value = date_parser.parse(item.published_at)
        except (TypeError, ValueError, OverflowError):
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        parsed_values.append(value)
    if not parsed_values:
        return "", ""
    return min(parsed_values).isoformat(), max(parsed_values).isoformat()


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
    http_status: int | str = ""
    request_success = False
    parse_success = False
    error_type = ""
    error_message = ""
    items: list[ShadowRouteItem] = []
    try:
        response = await client.get(surface.url, follow_redirects=True)
        http_status = response.status_code
        response.raise_for_status()
        request_success = True
        parser = parse_shadow_feed if surface.transport == "rss" else parse_shadow_section_html
        items = parser(
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
    return (
        ShadowSurfaceObservation(
            source_id=surface.source_id,
            surface_id=surface.surface_id,
            surface_role=surface.role.value,
            publication_surface_id=surface.publication_surface_id,
            endpoint=surface.url,
            transport=surface.transport,
            observed_at_bj=observed_at.strftime("%Y-%m-%d %H:%M:%S"),
            request_success=request_success,
            http_status=http_status,
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
        ),
        items,
    )


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
    treatment_sources = [
        source
        for source in sources
        if active_s1_surfaces(str(source.get("source_id", "")))
    ]
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
    async with httpx.AsyncClient(
        headers=headers,
        limits=limits,
        timeout=float(timeout),
    ) as client:
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

        results = await asyncio.gather(
            *(one(source, surface) for source, surface in surfaces)
        )

    observations = [observation for observation, _ in results]
    items = [item for _, group in results for item in group]
    proven_recent_urls = {
        item.url_canonical for item in items if item.within_freshness
    }
    proven_incremental_urls = {
        item.url_canonical
        for item in items
        if item.within_freshness and not item.control_overlap
    }
    return ZhRouteShadowReport(
        version=ROUTE_SHADOW_DISCOVERY_VERSION,
        contract_version=ROUTE_SHADOW_CONTRACT_VERSION,
        body_mode=S1_BODY_MODE,
        group_id=group_id,
        started_at_bj=started.strftime("%Y-%m-%d %H:%M:%S"),
        observed_at_bj=observed_at.strftime("%Y-%m-%d %H:%M:%S"),
        selected_source_ids=selected_ids,
        treatment_source_ids=[
            str(source.get("source_id", "")) for source in treatment_sources
        ],
        surfaces_attempted=len(surfaces),
        metadata_requests=len(surfaces),
        body_requests=0,
        observations=observations,
        items=items,
        control_native_unique_count=len(control_urls),
        treatment_unique_count=len(proven_recent_urls),
        incremental_unique_count=len(proven_incremental_urls),
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
        if state is None or not state.enabled or not state.group_id.startswith("zh_"):
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
        except Exception as exc:
            state.error = f"{type(exc).__name__}: {exc}"[:1000]
        return control


def install_paired_zh_route_shadow_discovery() -> None:
    from . import pipeline_v05 as _pipeline_v05

    if _pipeline_v05.NativeSourceDiscovery is not PairedZhRouteShadowDiscovery:
        _pipeline_v05.NativeSourceDiscovery = PairedZhRouteShadowDiscovery


__all__ = [
    "DIAGNOSTIC_RSS_HORIZON_DAYS",
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
