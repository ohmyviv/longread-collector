from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

import httpx

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .zh_route_shadow_s2b_track_v2 import (
    FIRECRAWL_PRIMARY_RESERVATION,
    FIRECRAWL_TOTAL_CAP,
    MANIFEST_COUNT,
    MANIFEST_SHA256,
    NETWORK_SAFETY_CAP,
    NetworkCounter,
    _REQUEST_SCOPE,
    observe_item,
    run_canaries,
    validate_manifest,
)

ACQUISITION_VERSION = "zh-route-shadow-s2b-body-observability-v2.1-free-tier"
FREE_TIER_DOCUMENTED_RPM = 20
FREE_TIER_MIN_INTERVAL_SECONDS = 3.1


class JinaFreeTierPacer:
    """Pace every actual unauthenticated Reader GET below Jina's documented 20 RPM.

    This wraps httpx only inside the isolated Track V runner. It does not alter the
    production JinaReaderClient or natural Collector behavior. Contextvars from the
    v2 measurement runner identify Jina requests, including retry attempts.
    """

    def __init__(self, min_interval_seconds: float = FREE_TIER_MIN_INTERVAL_SECONDS) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_started: float | None = None
        self._original_get = None

    def install(self) -> None:
        if self._original_get is not None:
            raise RuntimeError("free-tier pacer already installed")
        self._original_get = httpx.AsyncClient.get
        pacer = self

        async def paced_get(client, *args, **kwargs):
            scope = _REQUEST_SCOPE.get()
            if scope in {"canary:jina", "panel:jina"}:
                async with pacer._lock:
                    now = time.monotonic()
                    if pacer._last_started is not None:
                        delay = pacer.min_interval_seconds - (now - pacer._last_started)
                        if delay > 0:
                            await asyncio.sleep(delay)
                    pacer._last_started = time.monotonic()
                    return await pacer._original_get(client, *args, **kwargs)
            return await pacer._original_get(client, *args, **kwargs)

        httpx.AsyncClient.get = paced_get

    def restore(self) -> None:
        if self._original_get is not None:
            httpx.AsyncClient.get = self._original_get
            self._original_get = None


async def run_track_v_free_tier(manifest: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Execute the already-authorized Track V panel using Jina's no-key free Reader path.

    The exact frozen panel, body rubric, Firecrawl reservations, no-replacement rule,
    network safety cap and isolation boundaries are inherited from v2. The only
    acquisition change is explicit unauthenticated Jina Reader plus deterministic
    pacing below the documented free-tier 20 RPM limit.
    """

    items = validate_manifest(manifest)
    counter = NetworkCounter()
    pacer = JinaFreeTierPacer()
    # Deliberately do not pass settings.jina_api_key. This is measurement-only and
    # avoids the authenticated account/token path that returned HTTP 402 on 3/3 canaries.
    jina = JinaReaderClient(settings.jina_reader_base_url, api_key=None)
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)

    counter.install()
    pacer.install()
    try:
        canary = await run_canaries(jina)
        base = {
            "schema_version": "zh-route-shadow-s2b-track-v-results-v2.1",
            "experiment_track": "VALUE",
            "acquisition_version": ACQUISITION_VERSION,
            "manifest_sha256": MANIFEST_SHA256,
            "manifest_count": MANIFEST_COUNT,
            "jina_auth_mode": "unauthenticated_free_tier",
            "configured_jina_api_key_present": bool(settings.jina_api_key),
            "jina_authorization_header_sent": False,
            "jina_documented_free_tier_rpm": FREE_TIER_DOCUMENTED_RPM,
            "jina_min_request_interval_seconds": FREE_TIER_MIN_INTERVAL_SECONDS,
            "canary": canary,
            "paid_firecrawl_total_cap": FIRECRAWL_TOTAL_CAP,
            "paid_firecrawl_reservations": dict(FIRECRAWL_PRIMARY_RESERVATION),
            "network_safety_cap": NETWORK_SAFETY_CAP,
            "production_equivalent": False,
            "live_sheet_writes": 0,
            "article_cache_writes": 0,
            "editor_writes": 0,
        }
        if canary["status"] != "READY":
            return {
                **base,
                "status": canary["status"],
                "panel_requests_started": False,
                "network_request_count": counter.total,
                "network_requests_by_scope": dict(counter.by_scope),
                "firecrawl_logical_calls": 0,
                "firecrawl_credits_reported": 0,
                "results": [],
            }

        primary_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        uncertainty: list[dict[str, Any]] = []
        for item in items:
            if item.get("sampling_role") == "primary_plausible":
                primary_by_source[str(item["source_id"])].append(item)
            else:
                uncertainty.append(item)
        for rows in primary_by_source.values():
            rows.sort(key=lambda row: int(row["manifest_ordinal"]))
        uncertainty.sort(key=lambda row: int(row["manifest_ordinal"]))

        results: list[dict[str, Any]] = []

        async def run_primary_source(source_id: str) -> None:
            remaining = FIRECRAWL_PRIMARY_RESERVATION[source_id]
            for item in primary_by_source[source_id]:
                before = remaining
                row = await observe_item(
                    item, jina=jina, firecrawl=firecrawl, firecrawl_allowed=remaining > 0,
                )
                if row["paid_fallback_used"]:
                    remaining -= 1
                row["source_fallback_reservation_before"] = before
                row["source_fallback_reservation_after"] = remaining
                results.append(row)

        await asyncio.gather(
            run_primary_source("jiemian-depth"),
            run_primary_source("yicai"),
        )

        semaphore = asyncio.Semaphore(4)

        async def run_uncertainty(item: dict[str, Any]) -> None:
            async with semaphore:
                row = await observe_item(item, jina=jina, firecrawl=firecrawl, firecrawl_allowed=False)
                row["source_fallback_reservation_before"] = 0
                row["source_fallback_reservation_after"] = 0
                results.append(row)

        await asyncio.gather(*(run_uncertainty(item) for item in uncertainty))
        results.sort(key=lambda row: int(row["manifest_ordinal"]))
        for row in results:
            row["network_request_count"] = counter.by_ordinal[int(row["manifest_ordinal"])]

        firecrawl_calls = sum(bool(row["paid_fallback_used"]) for row in results)
        if firecrawl_calls > FIRECRAWL_TOTAL_CAP:
            raise RuntimeError("paid Firecrawl logical-call cap exceeded")
        credits = 0.0
        for row in results:
            for attempt in row["extraction_attempts"]:
                if attempt.get("extractor") != "firecrawl":
                    continue
                value = attempt.get("credits_used")
                if isinstance(value, (int, float)):
                    credits += float(value)

        return {
            **base,
            "status": "COMPLETED",
            "panel_requests_started": True,
            "network_request_count": counter.total,
            "network_requests_by_scope": dict(counter.by_scope),
            "firecrawl_logical_calls": firecrawl_calls,
            "firecrawl_credits_reported": credits,
            "body_evaluable_count": sum(bool(row["body_evaluable"]) for row in results),
            "budget_censored_count": sum(row["acquisition_status"] == "budget_censored" for row in results),
            "acquisition_failed_count": sum(row["acquisition_status"] == "acquisition_failed" for row in results),
            "results": results,
        }
    finally:
        pacer.restore()
        counter.restore()
