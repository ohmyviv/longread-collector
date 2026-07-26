from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx

from .models import DiscoveredURL

_RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


async def _sleep_for_retry(response: httpx.Response | None, attempt: int) -> None:
    retry_after = None if response is None else response.headers.get("retry-after")
    try:
        delay = float(retry_after) if retry_after else min(2 ** attempt, 12)
    except ValueError:
        delay = min(2 ** attempt, 12)
    await asyncio.sleep(delay)


class FirecrawlClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 65.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.timeout = timeout

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            response: httpx.Response | None = None
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.post(f"{self.base_url}{path}", headers=self.headers, json=payload)
                if response.status_code not in _RETRYABLE:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"retryable Firecrawl status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if response is not None and response.status_code not in _RETRYABLE:
                    raise
            if attempt < 2:
                await _sleep_for_retry(response, attempt + 1)
        assert last_error is not None
        raise last_error

    async def search(
        self,
        query: str,
        limit: int = 10,
        tbs: str | None = None,
        *,
        country: str | None = None,
        location: str | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> tuple[list[DiscoveredURL], dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "sources": ["web"],
            "ignoreInvalidURLs": True,
            "highlights": False,
            "timeout": 60000,
        }
        if tbs:
            payload["tbs"] = tbs
        if country:
            payload["country"] = country
        if location:
            payload["location"] = location
        if include_domains:
            payload["includeDomains"] = include_domains
        if exclude_domains:
            payload["excludeDomains"] = exclude_domains
        if categories:
            payload["categories"] = categories

        started = time.perf_counter()
        response = await self._post("/v2/search", payload)
        latency_ms = round((time.perf_counter() - started) * 1000)
        data = response.json()
        results: list[DiscoveredURL] = []
        body = data.get("data", data)
        if isinstance(body, list):
            groups = {"web": body}
        elif isinstance(body, dict):
            groups = {k: v for k, v in body.items() if isinstance(v, list)}
        else:
            groups = {}
        rank = 0
        for group_name in ("news", "web"):
            for item in groups.get(group_name, []):
                url = str(item.get("url") or item.get("link") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                rank += 1
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                results.append(DiscoveredURL(
                    url=url,
                    title=str(item.get("title") or metadata.get("title") or "").strip(),
                    description=str(item.get("description") or item.get("snippet") or metadata.get("description") or "").strip(),
                    published_at=str(item.get("date") or metadata.get("publishedTime") or metadata.get("date") or "").strip(),
                    query_or_source=query,
                    rank=rank,
                    metadata={"firecrawl_group": group_name, **metadata},
                ))
        meta = {
            "latency_ms": latency_ms,
            "credits_used": data.get("creditsUsed"),
            "warning": data.get("warning"),
            "result_count": len(results),
        }
        return results, meta

    async def scrape(self, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "onlyCleanContent": False,
            "timeout": 60000,
            "blockAds": True,
            "removeBase64Images": True,
            "maxAge": 172800000,
        }
        started = time.perf_counter()
        response = await self._post("/v2/scrape", payload)
        latency_ms = round((time.perf_counter() - started) * 1000)
        raw = response.json()
        data = raw.get("data", raw)
        return data if isinstance(data, dict) else {}, {
            "latency_ms": latency_ms,
            "credits_used": raw.get("creditsUsed"),
            "http_status": response.status_code,
        }


class JinaReaderClient:
    META_PATTERNS = {
        "title": re.compile(r"^Title:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
        "url": re.compile(r"^URL Source:\s*(.+)$", re.MULTILINE | re.IGNORECASE),
        "published_at": re.compile(r"^(?:Published Time|Published Date|Date):\s*(.+)$", re.MULTILINE | re.IGNORECASE),
        "author": re.compile(r"^(?:Author|Authors|By):\s*(.+)$", re.MULTILINE | re.IGNORECASE),
    }

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 45.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def read(self, url: str) -> tuple[dict[str, Any], dict[str, Any]]:
        target = f"{self.base_url}/{url}"
        headers = {
            "Accept": "text/plain",
            "User-Agent": "longread-collector/0.2",
            "X-Return-Format": "markdown",
            "X-Timeout": "40",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(3):
            response: httpx.Response | None = None
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    response = await client.get(target, headers=headers)
                if response.status_code not in _RETRYABLE:
                    response.raise_for_status()
                    break
                last_error = httpx.HTTPStatusError(
                    f"retryable Jina status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if response is not None and response.status_code not in _RETRYABLE:
                    raise
            if attempt < 2:
                await _sleep_for_retry(response, attempt + 1)
        else:
            assert last_error is not None
            raise last_error

        latency_ms = round((time.perf_counter() - started) * 1000)
        text = response.text.strip()
        parsed: dict[str, Any] = {"raw": text}
        for key, pattern in self.META_PATTERNS.items():
            match = pattern.search(text[:5000])
            parsed[key] = match.group(1).strip() if match else ""
        marker = re.search(r"^Markdown Content:\s*$", text, re.MULTILINE | re.IGNORECASE)
        content = text[marker.end():].strip() if marker else text
        parsed["markdown"] = content
        if not parsed["title"]:
            heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            if heading:
                parsed["title"] = heading.group(1).strip()
        if not parsed["author"]:
            byline = re.search(r"^(?:By|作者[：:]?)\s+([^\n]{2,120})$", content[:4000], re.MULTILINE | re.IGNORECASE)
            if byline:
                parsed["author"] = byline.group(1).strip()
        return parsed, {"latency_ms": latency_ms, "http_status": response.status_code}


def compact_json(value: Any, limit: int = 15000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return text if len(text) <= limit else text[:limit] + "…"
