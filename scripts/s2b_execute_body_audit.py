from __future__ import annotations

import argparse
import asyncio
import contextvars
import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

import httpx

from longread_collector.clients import FirecrawlClient, JinaReaderClient
from longread_collector.config import Settings
from longread_collector.extraction import FallbackBudget, extract_article
from longread_collector.models import DiscoveredURL

EXPECTED_SCHEMA = "zh-route-shadow-s2b-manifest-v1"
EXPECTED_TOTAL = 40
SEMANTIC_RUNTIME_BASELINE = "a380c68920c1de26f1e703b721d7eb2195900002"
ACQUISITION_FILES = (
    "src/longread_collector/extraction.py",
    "src/longread_collector/clients.py",
    "src/longread_collector/pipeline.py",
    "src/longread_collector/config.py",
)
_REQUEST_ORDINAL: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "s2b_request_ordinal", default=None
)
_NETWORK_REQUESTS_BY_ORDINAL: dict[int, int] = defaultdict(int)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def acquisition_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ACQUISITION_FILES:
        path = Path(name)
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_manifest(payload: dict[str, object]) -> list[dict[str, object]]:
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        raise ValueError("unexpected manifest schema")
    if payload.get("semantic_runtime_baseline") != SEMANTIC_RUNTIME_BASELINE:
        raise ValueError("semantic runtime baseline mismatch")
    items = list(payload.get("items") or [])
    if len(items) != EXPECTED_TOTAL:
        raise ValueError(f"manifest must contain {EXPECTED_TOTAL} items")
    digest = hashlib.sha256(canonical_json(items).encode("utf-8")).hexdigest()
    if digest != payload.get("manifest_sha256"):
        raise ValueError("manifest sha256 mismatch")
    urls = [str(item.get("url_canonical") or "") for item in items]
    if len(set(urls)) != EXPECTED_TOTAL or any(not url.startswith("http") for url in urls):
        raise ValueError("manifest canonical URLs invalid or duplicated")
    return items


def install_http_request_counter():
    original_get = httpx.AsyncClient.get
    original_post = httpx.AsyncClient.post

    async def counted_get(self, *args, **kwargs):
        ordinal = _REQUEST_ORDINAL.get()
        if ordinal is not None:
            _NETWORK_REQUESTS_BY_ORDINAL[ordinal] += 1
        return await original_get(self, *args, **kwargs)

    async def counted_post(self, *args, **kwargs):
        ordinal = _REQUEST_ORDINAL.get()
        if ordinal is not None:
            _NETWORK_REQUESTS_BY_ORDINAL[ordinal] += 1
        return await original_post(self, *args, **kwargs)

    httpx.AsyncClient.get = counted_get
    httpx.AsyncClient.post = counted_post
    return original_get, original_post


def restore_http_request_counter(original_get, original_post) -> None:
    httpx.AsyncClient.get = original_get
    httpx.AsyncClient.post = original_post


async def run_one(item: dict[str, object], *, settings: Settings, jina: JinaReaderClient,
                  firecrawl: FirecrawlClient, budget: FallbackBudget, semaphore: asyncio.Semaphore) -> dict[str, object]:
    ordinal = int(item["manifest_ordinal"])
    discovered = DiscoveredURL(
        url=str(item["url_canonical"]),
        title=str(item.get("title") or ""),
        language="zh",
        discovery_method="s2b_frozen_manifest",
        query_or_source=f"s2b:{item.get('source_id')}:{item.get('first_surface')}",
        metadata={
            "s2b_sampling_role": item.get("sampling_role"),
            "s2b_metadata_class": item.get("metadata_class"),
            "s2b_first_surface": item.get("first_surface"),
        },
    )
    token = _REQUEST_ORDINAL.set(ordinal)
    try:
        async with semaphore:
            article = await extract_article(discovered, jina, firecrawl, settings, budget)
    finally:
        _REQUEST_ORDINAL.reset(token)
    attempts = list(article.extraction_attempts)
    return {
        "manifest_ordinal": ordinal,
        "url_canonical": item["url_canonical"],
        "source_id": item["source_id"],
        "first_surface": item["first_surface"],
        "metadata_class": item["metadata_class"],
        "sampling_role": item["sampling_role"],
        "deterministic_rank": item["deterministic_rank"],
        "manifest_title": item.get("title", ""),
        "network_request_count": _NETWORK_REQUESTS_BY_ORDINAL[ordinal],
        "extraction_attempts": attempts,
        "extractor_used": article.extractor_used,
        "extraction_status": article.extraction_status,
        "verification_level": article.verification_level,
        "content_chars": article.content_chars,
        "content_sha256": article.content_sha256,
        "content_markdown": article.content_markdown,
        "extracted_title": article.title,
        "author": article.author,
        "published_at": article.published_at,
        "page_role": article.page_role,
        "page_type": article.page_type,
        "content_type": article.content_type,
        "candidate_disposition": article.candidate_disposition,
        "classification_reason": article.classification_reason,
        "reject_reason": article.reject_reason,
        "eligible_for_editor": article.eligible_for_editor,
        "valid_article_body": bool(article.metadata.get("valid_article_body")),
        "page_quality_reason": article.metadata.get("page_quality_reason", ""),
        "prose_chars": article.metadata.get("prose_chars", 0),
        "fallback_requested": article.metadata.get("fallback_requested", False),
        "fallback_allowed": article.metadata.get("fallback_allowed", False),
    }


async def execute(manifest: dict[str, object]) -> dict[str, object]:
    items = validate_manifest(manifest)
    settings = Settings()
    jina = JinaReaderClient(settings.jina_reader_base_url, settings.jina_api_key)
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)
    # Isolated diagnostic budget: same Control per-article chain and same cap=3,
    # but never reads/writes the natural Collector's daily ledger.
    budget = FallbackBudget(remaining=settings.firecrawl_fallback_daily_limit)
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    original_get, original_post = install_http_request_counter()
    try:
        tasks = [
            run_one(
                item,
                settings=settings,
                jina=jina,
                firecrawl=firecrawl,
                budget=budget,
                semaphore=semaphore,
            )
            for item in items
        ]
        results = await asyncio.gather(*tasks)
    finally:
        restore_http_request_counter(original_get, original_post)
    results = sorted(results, key=lambda row: int(row["manifest_ordinal"]))
    total_network = sum(int(row["network_request_count"]) for row in results)
    firecrawl_attempts = sum(
        1 for row in results for attempt in row["extraction_attempts"]
        if attempt.get("extractor") == "firecrawl" and attempt.get("error_type") != "DailyFallbackBudgetExhausted"
    )
    return {
        "schema_version": "zh-route-shadow-s2b-acquisition-results-v1",
        "semantic_runtime_baseline": SEMANTIC_RUNTIME_BASELINE,
        "execution_commit": os.environ.get("GITHUB_SHA", ""),
        "acquisition_files": list(ACQUISITION_FILES),
        "acquisition_fingerprint_sha256": acquisition_fingerprint(),
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest_count": len(items),
        "control_acquisition_contract": "legacy extract_article: jina -> budgeted firecrawl fallback",
        "firecrawl_fallback_cap_isolated": settings.firecrawl_fallback_daily_limit,
        "network_request_count": total_network,
        "firecrawl_actual_attempts": firecrawl_attempts,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="s2b-acquisition-results.json")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output = asyncio.run(execute(manifest))
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(canonical_json({k: v for k, v in output.items() if k != "results"}))


if __name__ == "__main__":
    main()
