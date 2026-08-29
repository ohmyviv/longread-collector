from __future__ import annotations

import contextvars
import hashlib
import html as html_lib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .quality import content_quality_reason

MANIFEST_SHA256 = "7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b"
MANIFEST_SCHEMA = "zh-route-shadow-s2b-manifest-v1"
MANIFEST_COUNT = 40
ACQUISITION_VERSION = "zh-route-shadow-s2b-body-observability-v2"
CANARY_URLS = (
    "https://www.iana.org/help/example-domains",
    "https://www.python.org/about/",
    "https://www.gnu.org/philosophy/free-sw.en.html",
)
PROVIDER_FAILURE_STATUSES = {401, 402, 403, 429}
CANARY_MIN_CHARS = 300
DIRECT_STOP_MIN_CHARS = 1200
NETWORK_SAFETY_CAP = 230
FIRECRAWL_TOTAL_CAP = 20
FIRECRAWL_PRIMARY_RESERVATION = {"jiemian-depth": 10, "yicai": 10}

_REQUEST_SCOPE: contextvars.ContextVar[str] = contextvars.ContextVar("s2b_v2_request_scope", default="unscoped")
_REQUEST_ORDINAL: contextvars.ContextVar[int | None] = contextvars.ContextVar("s2b_v2_request_ordinal", default=None)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_manifest(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("unexpected manifest schema")
    if payload.get("manifest_sha256") != MANIFEST_SHA256:
        raise ValueError("manifest hash identity mismatch")
    items = list(payload.get("items") or [])
    if len(items) != MANIFEST_COUNT:
        raise ValueError(f"expected {MANIFEST_COUNT} manifest items")
    digest = hashlib.sha256(canonical_json(items).encode("utf-8")).hexdigest()
    if digest != MANIFEST_SHA256:
        raise ValueError("manifest content hash mismatch")
    ordinals = [int(item.get("manifest_ordinal") or 0) for item in items]
    if ordinals != list(range(1, MANIFEST_COUNT + 1)):
        raise ValueError("manifest ordinals are not exactly 1..40")
    urls = [str(item.get("url_canonical") or "").strip() for item in items]
    if len(set(urls)) != MANIFEST_COUNT or any(not url.startswith("http") for url in urls):
        raise ValueError("manifest URLs missing or duplicated")
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for item in items:
        counts[(str(item.get("source_id")), str(item.get("sampling_role")))] += 1
    expected = {
        ("jiemian-depth", "primary_plausible"): 15,
        ("jiemian-depth", "uncertainty_explore"): 4,
        ("yicai", "primary_plausible"): 15,
        ("yicai", "uncertainty_explore"): 6,
    }
    if dict(counts) != expected:
        raise ValueError(f"manifest source/role drift: {dict(counts)}")
    return items


def _status_from_exception(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code
    return None


def decide_canary_status(rows: list[dict[str, Any]]) -> str:
    successes = sum(bool(row.get("success")) for row in rows)
    provider_failures = sum(int(row.get("http_status") or 0) in PROVIDER_FAILURE_STATUSES for row in rows)
    if provider_failures >= 2:
        return "PROVIDER_NOT_READY"
    if successes >= 2:
        return "READY"
    return "INDETERMINATE"


class NetworkSafetyCapExceeded(RuntimeError):
    pass


@dataclass
class NetworkCounter:
    cap: int = NETWORK_SAFETY_CAP

    def __post_init__(self) -> None:
        self.total = 0
        self.by_scope: dict[str, int] = defaultdict(int)
        self.by_ordinal: dict[int, int] = defaultdict(int)
        self._original_get = None
        self._original_post = None

    def install(self) -> None:
        if self._original_get is not None:
            raise RuntimeError("counter already installed")
        self._original_get = httpx.AsyncClient.get
        self._original_post = httpx.AsyncClient.post
        counter = self

        async def counted_get(client, *args, **kwargs):
            counter._before_request()
            return await counter._original_get(client, *args, **kwargs)

        async def counted_post(client, *args, **kwargs):
            counter._before_request()
            return await counter._original_post(client, *args, **kwargs)

        httpx.AsyncClient.get = counted_get
        httpx.AsyncClient.post = counted_post

    def _before_request(self) -> None:
        if self.total >= self.cap:
            raise NetworkSafetyCapExceeded(f"actual HTTP request cap {self.cap} reached")
        self.total += 1
        self.by_scope[_REQUEST_SCOPE.get()] += 1
        ordinal = _REQUEST_ORDINAL.get()
        if ordinal is not None:
            self.by_ordinal[ordinal] += 1

    def restore(self) -> None:
        if self._original_get is not None:
            httpx.AsyncClient.get = self._original_get
            httpx.AsyncClient.post = self._original_post
            self._original_get = None
            self._original_post = None


class _BodyHTMLParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "canvas", "nav", "header", "footer", "aside", "form"}
    BLOCKS = {"p", "h1", "h2", "h3", "blockquote", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.article_depth = 0
        self.current_tag: str | None = None
        self.current_parts: list[str] = []
        self.current_in_article = False
        self.blocks: list[tuple[str, bool]] = []
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag in self.SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "article":
            self.article_depth += 1
        if tag == "meta":
            key = (attr.get("property") or attr.get("name") or "").lower().strip()
            value = attr.get("content", "").strip()
            if key and value and key not in self.meta:
                self.meta[key] = value
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCKS and self.current_tag is None:
            self.current_tag = tag
            self.current_parts = []
            self.current_in_article = self.article_depth > 0

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.in_title = False
        if self.current_tag == tag:
            text = re.sub(r"\s+", " ", html_lib.unescape("".join(self.current_parts))).strip()
            if text:
                self.blocks.append((text, self.current_in_article))
            self.current_tag = None
            self.current_parts = []
        if tag == "article" and self.article_depth:
            self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.current_tag is not None:
            self.current_parts.append(data)

    def body_text(self) -> str:
        article = [text for text, flag in self.blocks if flag]
        all_blocks = [text for text, _ in self.blocks]
        article_chars = len(re.sub(r"\s+", "", "".join(article)))
        chosen = article if article_chars >= 600 else all_blocks
        deduped: list[str] = []
        for text in chosen:
            if not deduped or deduped[-1] != text:
                deduped.append(text)
        return "\n\n".join(deduped)

    def page_title(self) -> str:
        return (
            self.meta.get("og:title")
            or self.meta.get("twitter:title")
            or re.sub(r"\s+", " ", "".join(self.title_parts)).strip()
        )

    def author(self) -> str:
        return self.meta.get("author") or self.meta.get("article:author") or ""

    def published_at(self) -> str:
        for key in ("article:published_time", "datepublished", "date", "publishdate", "pubdate"):
            if self.meta.get(key):
                return self.meta[key]
        return ""


def extract_direct_html(html: str, manifest_title: str = "") -> dict[str, Any]:
    parser = _BodyHTMLParser()
    parser.feed(html or "")
    content = parser.body_text()
    return {
        "content": content,
        "title": parser.page_title() or manifest_title,
        "author": parser.author(),
        "published_at": parser.published_at(),
    }


def _candidate(*, extractor: str, url: str, content: str, title: str, author: str = "",
               published_at: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    valid, reason, prose_chars = content_quality_reason(url, title, content)
    return {
        "extractor": extractor,
        "content": content,
        "title": title,
        "author": author,
        "published_at": published_at,
        "metadata": metadata or {},
        "valid_body": valid,
        "quality_reason": reason,
        "prose_chars": prose_chars,
    }


def _sufficient(candidate: dict[str, Any] | None) -> bool:
    return bool(candidate and candidate.get("valid_body") and len(str(candidate.get("content") or "")) >= DIRECT_STOP_MIN_CHARS)


def _best_candidate(candidates: list[dict[str, Any]], manifest_title: str) -> dict[str, Any]:
    if not candidates:
        return {
            "extractor": "none", "content": "", "title": manifest_title, "author": "", "published_at": "",
            "metadata": {}, "valid_body": False, "quality_reason": "no_extracted_content", "prose_chars": 0,
        }
    return max(
        candidates,
        key=lambda row: (
            int(bool(row.get("valid_body"))),
            int(row.get("prose_chars") or 0),
            len(str(row.get("content") or "")),
        ),
    )


async def run_canaries(jina: JinaReaderClient) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    scope_token = _REQUEST_SCOPE.set("canary:jina")
    try:
        for url in CANARY_URLS:
            try:
                data, meta = await jina.read(url)
                content = str(data.get("markdown") or "")
                rows.append({
                    "url": url,
                    "success": int(meta.get("http_status") or 0) // 100 == 2 and len(content) >= CANARY_MIN_CHARS,
                    "http_status": int(meta.get("http_status") or 0),
                    "body_chars": len(content),
                    "latency_ms": meta.get("latency_ms"),
                    "error_type": "",
                    "error_message": "",
                })
            except Exception as exc:
                rows.append({
                    "url": url,
                    "success": False,
                    "http_status": _status_from_exception(exc),
                    "body_chars": 0,
                    "latency_ms": None,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                })
    finally:
        _REQUEST_SCOPE.reset(scope_token)
    return {
        "canary_urls": list(CANARY_URLS),
        "status": decide_canary_status(rows),
        "success_count": sum(bool(row["success"]) for row in rows),
        "provider_failure_count": sum(int(row.get("http_status") or 0) in PROVIDER_FAILURE_STATUSES for row in rows),
        "rows": rows,
    }


async def _direct_attempt(item: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = str(item["url_canonical"])
    started_scope = _REQUEST_SCOPE.set("panel:direct_html")
    try:
        try:
            async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "longread-collector-s2b-v2/1.0"})
            response.raise_for_status()
            parsed = extract_direct_html(response.text, str(item.get("title") or ""))
            candidate = _candidate(
                extractor="direct_html", url=url, content=str(parsed["content"]), title=str(parsed["title"]),
                author=str(parsed["author"]), published_at=str(parsed["published_at"]),
                metadata={"http_status": response.status_code, "content_type": response.headers.get("content-type", "")},
            )
            return candidate, {
                "extractor": "direct_html", "success": bool(candidate["valid_body"]),
                "body_chars": len(str(candidate["content"])), "prose_chars": candidate["prose_chars"],
                "quality_reason": candidate["quality_reason"], "http_status": response.status_code,
            }
        except Exception as exc:
            return None, {
                "extractor": "direct_html", "success": False, "body_chars": 0,
                "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
                "http_status": _status_from_exception(exc),
            }
    finally:
        _REQUEST_SCOPE.reset(started_scope)


async def _jina_attempt(item: dict[str, Any], jina: JinaReaderClient) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = str(item["url_canonical"])
    scope_token = _REQUEST_SCOPE.set("panel:jina")
    try:
        try:
            data, meta = await jina.read(url)
            content = str(data.get("markdown") or "")
            candidate = _candidate(
                extractor="jina", url=url, content=content,
                title=str(data.get("title") or item.get("title") or ""),
                author=str(data.get("author") or ""), published_at=str(data.get("published_at") or ""),
                metadata={k: v for k, v in data.items() if k not in {"raw", "markdown"}},
            )
            return candidate, {
                "extractor": "jina", "success": bool(candidate["valid_body"]),
                "body_chars": len(content), "prose_chars": candidate["prose_chars"],
                "quality_reason": candidate["quality_reason"], **meta,
            }
        except Exception as exc:
            return None, {
                "extractor": "jina", "success": False, "body_chars": 0,
                "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
                "http_status": _status_from_exception(exc),
            }
    finally:
        _REQUEST_SCOPE.reset(scope_token)


async def _firecrawl_attempt(item: dict[str, Any], firecrawl: FirecrawlClient) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = str(item["url_canonical"])
    scope_token = _REQUEST_SCOPE.set("panel:firecrawl")
    try:
        try:
            data, meta = await firecrawl.scrape(url)
            md = data.get("markdown")
            if isinstance(md, dict):
                md = md.get("content") or md.get("markdown") or ""
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            content = str(md or "")
            candidate = _candidate(
                extractor="firecrawl", url=url, content=content,
                title=str(metadata.get("title") or item.get("title") or ""),
                author=str(metadata.get("author") or metadata.get("authors") or ""),
                published_at=str(metadata.get("publishedTime") or metadata.get("publishedDate") or metadata.get("date") or ""),
                metadata=metadata,
            )
            return candidate, {
                "extractor": "firecrawl", "success": bool(candidate["valid_body"]),
                "body_chars": len(content), "prose_chars": candidate["prose_chars"],
                "quality_reason": candidate["quality_reason"], **meta,
            }
        except Exception as exc:
            return None, {
                "extractor": "firecrawl", "success": False, "body_chars": 0,
                "error_type": type(exc).__name__, "error_message": str(exc)[:1000],
                "http_status": _status_from_exception(exc),
            }
    finally:
        _REQUEST_SCOPE.reset(scope_token)


async def observe_item(
    item: dict[str, Any], *, jina: JinaReaderClient, firecrawl: FirecrawlClient,
    firecrawl_allowed: bool,
) -> dict[str, Any]:
    ordinal = int(item["manifest_ordinal"])
    ordinal_token = _REQUEST_ORDINAL.set(ordinal)
    attempts: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    paid_fallback_used = False
    try:
        direct, attempt = await _direct_attempt(item)
        attempts.append(attempt)
        if direct:
            candidates.append(direct)
        best = _best_candidate(candidates, str(item.get("title") or ""))

        if not _sufficient(best):
            jina_candidate, attempt = await _jina_attempt(item, jina)
            attempts.append(attempt)
            if jina_candidate:
                candidates.append(jina_candidate)
            best = _best_candidate(candidates, str(item.get("title") or ""))

        if not _sufficient(best):
            if firecrawl_allowed:
                paid_fallback_used = True
                fc_candidate, attempt = await _firecrawl_attempt(item, firecrawl)
                attempts.append(attempt)
                if fc_candidate:
                    candidates.append(fc_candidate)
            else:
                attempts.append({
                    "extractor": "firecrawl", "success": False, "body_chars": 0,
                    "error_type": "PaidFallbackReservationUnavailable",
                    "error_message": "row is outside the pre-authorized source/role paid fallback reservation",
                    "credits_used": 0,
                })
        best = _best_candidate(candidates, str(item.get("title") or ""))
        content = str(best.get("content") or "")
        body_evaluable = bool(best.get("valid_body"))
        if body_evaluable:
            acquisition_status = "body_observed"
            censoring_reason = ""
        elif any(attempt.get("error_type") == "PaidFallbackReservationUnavailable" for attempt in attempts):
            acquisition_status = "budget_censored"
            censoring_reason = "paid_fallback_reservation_unavailable"
        else:
            acquisition_status = "acquisition_failed"
            censoring_reason = "no_usable_body_after_authorized_paths"
        return {
            "manifest_ordinal": ordinal,
            "url_canonical": item["url_canonical"],
            "source_id": item["source_id"],
            "first_surface": item["first_surface"],
            "metadata_class": item["metadata_class"],
            "sampling_role": item["sampling_role"],
            "deterministic_rank": item["deterministic_rank"],
            "manifest_title": item.get("title", ""),
            "acquisition_status": acquisition_status,
            "body_evaluable": body_evaluable,
            "censoring_reason": censoring_reason,
            "paid_fallback_used": paid_fallback_used,
            "network_request_count": 0,
            "extraction_attempts": attempts,
            "extractor_used": best.get("extractor", "none"),
            "valid_article_body": body_evaluable,
            "page_quality_reason": best.get("quality_reason", ""),
            "prose_chars": int(best.get("prose_chars") or 0),
            "content_chars": len(content),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            "content_markdown": content[:45000],
            "content_truncated": len(content) > 45000,
            "extracted_title": best.get("title", ""),
            "author": best.get("author", ""),
            "published_at": best.get("published_at", ""),
        }
    finally:
        _REQUEST_ORDINAL.reset(ordinal_token)


async def run_track_v(manifest: dict[str, Any], settings: Settings) -> dict[str, Any]:
    items = validate_manifest(manifest)
    counter = NetworkCounter()
    jina = JinaReaderClient(settings.jina_reader_base_url, settings.jina_api_key)
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)
    counter.install()
    try:
        canary = await run_canaries(jina)
        base = {
            "schema_version": "zh-route-shadow-s2b-track-v-results-v2",
            "experiment_track": "VALUE",
            "acquisition_version": ACQUISITION_VERSION,
            "manifest_sha256": MANIFEST_SHA256,
            "manifest_count": MANIFEST_COUNT,
            "jina_api_key_present": bool(settings.jina_api_key),
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
                # A source reservation is consumed only when the row reaches Firecrawl.
                # The per-source loop is ordinal-ordered, so there is no cross-source or
                # concurrency-driven allocation bias.
                before = remaining
                row = await observe_item(
                    item, jina=jina, firecrawl=firecrawl, firecrawl_allowed=remaining > 0,
                )
                if row["paid_fallback_used"]:
                    remaining -= 1
                row["source_fallback_reservation_before"] = before
                row["source_fallback_reservation_after"] = remaining
                results.append(row)

        import asyncio
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
        counter.restore()
