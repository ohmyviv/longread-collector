from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import time
from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx

VERSION = "yicai-acquisition-forensic-v1"
SEED = "yicai-acquisition-forensic-v1-20260830"
SURFACES = ("yicai_auto", "yicai_finance", "yicai_kechuang", "yicai_news_breadth")
MAX_DIAGNOSTIC_URLS = 4
THEORETICAL_HTTP_CAP = 20
HARD_HTTP_CAP = 25
JINA_MIN_INTERVAL_SECONDS = 3.1


@dataclass(frozen=True, slots=True)
class DiagnosticItem:
    ordinal: int
    first_surface: str
    canonical_url: str
    title: str
    deterministic_rank: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def rank_item(surface: str, canonical_url: str) -> str:
    return hashlib.sha256(f"{SEED} | {surface} | {canonical_url}".encode("utf-8")).hexdigest()


def select_manifest(rows: Iterable[Mapping[str, Any]]) -> list[DiagnosticItem]:
    eligible: dict[str, list[DiagnosticItem]] = {surface: [] for surface in SURFACES}
    seen: set[str] = set()
    for row in rows:
        if _text(row.get("source_id")) != "yicai":
            continue
        if _text(row.get("sampling_role")) != "primary_plausible":
            continue
        surface = _text(row.get("first_surface"))
        if surface not in eligible:
            continue
        url = _text(row.get("url_canonical") or row.get("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        eligible[surface].append(
            DiagnosticItem(
                ordinal=0,
                first_surface=surface,
                canonical_url=url,
                title=_text(row.get("title")),
                deterministic_rank=rank_item(surface, url),
            )
        )
    selected: list[DiagnosticItem] = []
    for surface in SURFACES:
        candidates = sorted(eligible[surface], key=lambda value: (value.deterministic_rank, value.canonical_url))
        if not candidates:
            raise ValueError(f"missing frozen Yicai primary stratum: {surface}")
        chosen = candidates[0]
        selected.append(
            DiagnosticItem(
                ordinal=len(selected) + 1,
                first_surface=chosen.first_surface,
                canonical_url=chosen.canonical_url,
                title=chosen.title,
                deterministic_rank=chosen.deterministic_rank,
            )
        )
    if len(selected) != MAX_DIAGNOSTIC_URLS or len({item.canonical_url for item in selected}) != 4:
        raise ValueError("Yicai forensic manifest must contain exactly four unique URLs")
    return selected


def manifest_sha256(items: Iterable[DiagnosticItem]) -> str:
    payload = [asdict(item) for item in items]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def www_variant(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc
    if host.startswith("www."):
        return url
    return urlunsplit((parts.scheme, f"www.{host}", parts.path, parts.query, parts.fragment))


class RequestBudget:
    def __init__(self, hard_cap: int = HARD_HTTP_CAP) -> None:
        self.hard_cap = hard_cap
        self.total = 0
        self.by_scope: dict[str, int] = {}

    def consume(self, scope: str) -> None:
        if self.total >= self.hard_cap:
            raise RuntimeError("Yicai forensic HTTP hard cap exceeded")
        self.total += 1
        self.by_scope[scope] = self.by_scope.get(scope, 0) + 1


async def _dns(host: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
        addresses = sorted({str(info[4][0]) for info in infos})
        return {"status": "ok", "addresses": addresses, "latency_ms": round((time.perf_counter()-started)*1000)}
    except Exception as exc:  # diagnostic telemetry
        return {"status": "error", "error_class": type(exc).__name__, "error": str(exc)[:500], "latency_ms": round((time.perf_counter()-started)*1000)}


async def direct_probe(url: str, *, budget: RequestBudget, label: str) -> dict[str, Any]:
    host = urlsplit(url).hostname or ""
    dns = await _dns(host)
    budget.consume(f"direct:{label}")
    started = time.perf_counter()
    try:
        timeout = httpx.Timeout(25.0, connect=10.0)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; longread-forensic/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        body = response.content
        return {
            "kind": "direct",
            "label": label,
            "requested_url": url,
            "dns": dns,
            "status": "response",
            "http_status": response.status_code,
            "final_url": str(response.url),
            "redirect_history": [str(item.url) for item in response.history],
            "latency_ms": round((time.perf_counter()-started)*1000),
            "response_bytes": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest() if body else "",
        }
    except Exception as exc:
        return {
            "kind": "direct",
            "label": label,
            "requested_url": url,
            "dns": dns,
            "status": "error",
            "error_class": type(exc).__name__,
            "error": str(exc)[:1000],
            "latency_ms": round((time.perf_counter()-started)*1000),
        }


async def jina_probe(url: str, *, budget: RequestBudget, label: str, pacer_lock: asyncio.Lock, pacer_state: dict[str, float | None]) -> dict[str, Any]:
    async with pacer_lock:
        now = time.monotonic()
        last = pacer_state.get("last")
        if isinstance(last, float):
            wait = JINA_MIN_INTERVAL_SECONDS - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
        pacer_state["last"] = time.monotonic()
        budget.consume(f"jina:{label}")
        target = f"https://r.jina.ai/{url}"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                response = await client.get(
                    target,
                    headers={
                        "Accept": "text/plain",
                        "User-Agent": "longread-forensic/1.0",
                        "X-Return-Format": "markdown",
                        "X-Timeout": "40",
                    },
                )
            text = response.text
            url_source = ""
            for line in text[:5000].splitlines():
                if line.lower().startswith("url source:"):
                    url_source = line.split(":", 1)[1].strip()
                    break
            return {
                "kind": "jina",
                "label": label,
                "requested_url": url,
                "jina_target": target,
                "authorization_header_sent": False,
                "status": "response",
                "http_status": response.status_code,
                "latency_ms": round((time.perf_counter()-started)*1000),
                "response_bytes": len(response.content),
                "url_source": url_source,
                "body_sha256": hashlib.sha256(response.content).hexdigest() if response.content else "",
            }
        except Exception as exc:
            return {
                "kind": "jina",
                "label": label,
                "requested_url": url,
                "jina_target": target,
                "authorization_header_sent": False,
                "status": "error",
                "error_class": type(exc).__name__,
                "error": str(exc)[:1000],
                "latency_ms": round((time.perf_counter()-started)*1000),
            }


async def firecrawl_probe(url: str, *, api_key: str, budget: RequestBudget) -> dict[str, Any]:
    budget.consume("firecrawl:canonical")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=70.0, follow_redirects=True) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v2/scrape",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "timeout": 60000,
                    "blockAds": True,
                    "removeBase64Images": True,
                    "maxAge": 0,
                },
            )
        raw: Any = None
        try:
            raw = response.json()
        except Exception:
            raw = None
        data = raw.get("data", raw) if isinstance(raw, dict) else None
        markdown = data.get("markdown", "") if isinstance(data, dict) else ""
        return {
            "kind": "firecrawl",
            "requested_url": url,
            "status": "response",
            "http_status": response.status_code,
            "latency_ms": round((time.perf_counter()-started)*1000),
            "response_bytes": len(response.content),
            "markdown_chars": len(str(markdown or "")),
            "credits_used": raw.get("creditsUsed") if isinstance(raw, dict) else None,
            "body_sha256": hashlib.sha256(str(markdown or "").encode("utf-8")).hexdigest() if markdown else "",
        }
    except Exception as exc:
        return {
            "kind": "firecrawl",
            "requested_url": url,
            "status": "error",
            "error_class": type(exc).__name__,
            "error": str(exc)[:1000],
            "latency_ms": round((time.perf_counter()-started)*1000),
        }


def _success(probe: Mapping[str, Any]) -> bool:
    return probe.get("status") == "response" and isinstance(probe.get("http_status"), int) and 200 <= int(probe["http_status"]) < 400


def classify_signals(rows: list[dict[str, Any]]) -> list[str]:
    signals: list[str] = []
    host_pairs = 0
    jina_pairs = 0
    firecrawl_success = 0
    firecrawl_fail_408_5xx = 0
    for row in rows:
        probes = row["probes"]
        direct_can = probes["direct_canonical"]
        direct_www = probes["direct_www"]
        if not _success(direct_can) and _success(direct_www):
            host_pairs += 1
        jina_can = probes["jina_canonical"]
        jina_www = probes["jina_www"]
        if _success(jina_can) != _success(jina_www) or jina_can.get("http_status") != jina_www.get("http_status"):
            jina_pairs += 1
        fc = probes["firecrawl"]
        if _success(fc):
            firecrawl_success += 1
        status = fc.get("http_status")
        if fc.get("status") == "error" or status == 408 or (isinstance(status, int) and status >= 500):
            firecrawl_fail_408_5xx += 1
    if host_pairs >= 3:
        signals.append("HOST_IDENTITY_EXPLAINS_DIRECT_FAILURE")
    if jina_pairs >= 3:
        signals.append("JINA_HOST_NORMALIZATION_SIGNAL")
    if firecrawl_success < 2 and firecrawl_fail_408_5xx >= 2:
        signals.append("FIRECRAWL_PROVIDER_INSTABILITY_SIGNAL")
    if not signals:
        signals.append("NO_SINGLE_CAUSE_ISOLATED")
    return signals


async def execute_manifest(items: list[DiagnosticItem], *, firecrawl_api_key: str) -> dict[str, Any]:
    if len(items) != 4:
        raise ValueError("exact four-item forensic manifest required")
    budget = RequestBudget()
    lock = asyncio.Lock()
    pacer_state: dict[str, float | None] = {"last": None}
    results: list[dict[str, Any]] = []
    for item in items:
        canonical = item.canonical_url
        www = www_variant(canonical)
        direct_canonical = await direct_probe(canonical, budget=budget, label="canonical")
        direct_www = await direct_probe(www, budget=budget, label="www")
        jina_canonical = await jina_probe(canonical, budget=budget, label="canonical", pacer_lock=lock, pacer_state=pacer_state)
        jina_www = await jina_probe(www, budget=budget, label="www", pacer_lock=lock, pacer_state=pacer_state)
        firecrawl = await firecrawl_probe(canonical, api_key=firecrawl_api_key, budget=budget)
        results.append({
            **asdict(item),
            "www_variant": www,
            "probes": {
                "direct_canonical": direct_canonical,
                "direct_www": direct_www,
                "jina_canonical": jina_canonical,
                "jina_www": jina_www,
                "firecrawl": firecrawl,
            },
        })
    if budget.total > THEORETICAL_HTTP_CAP:
        raise RuntimeError(f"unexpected Yicai forensic request count {budget.total} > {THEORETICAL_HTTP_CAP}")
    return {
        "version": VERSION,
        "status": "COMPLETED",
        "manifest_sha256": manifest_sha256(items),
        "manifest_count": len(items),
        "actual_http_requests": budget.total,
        "requests_by_scope": budget.by_scope,
        "theoretical_http_cap": THEORETICAL_HTTP_CAP,
        "hard_http_cap": HARD_HTTP_CAP,
        "jina_authorization_header_sent": False,
        "production_mutations": 0,
        "sheet_writes": 0,
        "article_cache_writes": 0,
        "editor_writes": 0,
        "signals": classify_signals(results),
        "results": results,
    }
