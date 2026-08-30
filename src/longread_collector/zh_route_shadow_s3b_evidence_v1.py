"""Bounded Jiemian S3-B evidence completion.

This module is measurement-only. It implements the exact four-item blocker set
emitted by S3-A v1.1 and the already-frozen S3-B contract. It never writes the
Production cache, Editor, live selection ledger, source registry or scheduler.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .zh_route_shadow_s2b_track_v2 import NetworkCounter, observe_item, run_canaries
from .zh_route_shadow_s2b_track_v21 import JinaFreeTierPacer

S3B_VERSION = "zh-route-shadow-s3b-jiemian-evidence-completion-v1"
SCHEMA_VERSION = "zh-route-shadow-s3b-results-v1"
MANIFEST_SCHEMA = "zh-route-shadow-s3b-manifest-v1"
MANIFEST_SHA256 = "ff4fe7d54b1c38b3105329ec5653bed14799e7ae493bd36dc4d93fd88bfbc865"
ARTICLE_ATTEMPT_CAP = 4
FIRECRAWL_LOGICAL_CAP = 2
NETWORK_SAFETY_CAP = 40
JINA_MIN_INTERVAL_SECONDS = 3.1

MANIFEST_ITEMS: tuple[dict[str, Any], ...] = (
    {
        "manifest_ordinal": 1,
        "url_canonical": "https://jiemian.com/article/14977759.html",
        "title": "白云山转型半年：创新投入增长、王牌仍在下滑",
        "source_id": "jiemian-depth",
        "first_surface": "jiemian_medicine",
        "metadata_class": "plausible_standard_longread",
        "sampling_role": "s3b_treatment_blocker",
    },
    {
        "manifest_ordinal": 2,
        "url_canonical": "https://jiemian.com/article/14997276.html",
        "title": "从“长寿”到“健康长寿”，抗衰开始走进整个生活",
        "source_id": "jiemian-depth",
        "first_surface": "jiemian_consumer",
        "metadata_class": "plausible_standard_longread",
        "sampling_role": "s3b_treatment_blocker",
    },
    {
        "manifest_ordinal": 3,
        "url_canonical": "https://jiemian.com/article/14998723.html",
        "title": "ST香雪“保壳”命悬一线",
        "source_id": "jiemian-depth",
        "first_surface": "jiemian_medicine",
        "metadata_class": "plausible_standard_longread",
        "sampling_role": "s3b_treatment_blocker",
    },
    {
        "manifest_ordinal": 4,
        "url_canonical": "https://jiemian.com/article/15018993.html",
        "title": "衰老干预技术的高价困局，瑞拓龄能否打破成本壁垒",
        "source_id": "jiemian-depth",
        "first_surface": "jiemian_medicine",
        "metadata_class": "plausible_standard_longread",
        "sampling_role": "s3b_treatment_blocker",
    },
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_payload() -> dict[str, Any]:
    items = [dict(row) for row in MANIFEST_ITEMS]
    digest = hashlib.sha256(_canonical_json(items).encode("utf-8")).hexdigest()
    if digest != MANIFEST_SHA256:
        raise RuntimeError("S3-B manifest identity drift")
    return {
        "schema_version": MANIFEST_SCHEMA,
        "manifest_sha256": MANIFEST_SHA256,
        "manifest_count": ARTICLE_ATTEMPT_CAP,
        "items": items,
    }


def validate_manifest() -> list[dict[str, Any]]:
    payload = manifest_payload()
    items = list(payload["items"])
    if len(items) != ARTICLE_ATTEMPT_CAP:
        raise RuntimeError("S3-B article-attempt denominator drift")
    if [int(row["manifest_ordinal"]) for row in items] != [1, 2, 3, 4]:
        raise RuntimeError("S3-B manifest ordinals drifted")
    urls = [str(row["url_canonical"]) for row in items]
    if len(set(urls)) != ARTICLE_ATTEMPT_CAP:
        raise RuntimeError("S3-B manifest contains duplicate identities")
    if any(row["source_id"] != "jiemian-depth" for row in items):
        raise RuntimeError("S3-B source identity drift")
    return items


async def run_s3b(settings: Settings) -> dict[str, Any]:
    """Run the exact four-item evidence completion under the frozen 2/40 caps."""
    items = validate_manifest()
    counter = NetworkCounter(cap=NETWORK_SAFETY_CAP)
    pacer = JinaFreeTierPacer(min_interval_seconds=JINA_MIN_INTERVAL_SECONDS)
    jina = JinaReaderClient(settings.jina_reader_base_url, api_key=None)
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)

    counter.install()
    pacer.install()
    try:
        canary = await run_canaries(jina)
        base = {
            "schema_version": SCHEMA_VERSION,
            "experiment_version": S3B_VERSION,
            "manifest": manifest_payload(),
            "manifest_sha256": MANIFEST_SHA256,
            "manifest_count": ARTICLE_ATTEMPT_CAP,
            "existing_evidence_gate_checked": True,
            "existing_evidence_reusable_count": 0,
            "existing_evidence_sources": ["article_cache", "extraction_log", "s2b_v21_results"],
            "jina_auth_mode": "unauthenticated_free_tier",
            "jina_authorization_header_sent": False,
            "jina_min_request_interval_seconds": JINA_MIN_INTERVAL_SECONDS,
            "firecrawl_logical_cap": FIRECRAWL_LOGICAL_CAP,
            "network_safety_cap": NETWORK_SAFETY_CAP,
            "canary": canary,
            "production_equivalent": False,
            "live_sheet_writes": 0,
            "article_cache_writes": 0,
            "editor_writes": 0,
            "live_selection_writes": 0,
        }
        if canary["status"] != "READY":
            return {
                **base,
                "status": canary["status"],
                "panel_requests_started": False,
                "network_request_count": counter.total,
                "network_requests_by_scope": dict(counter.by_scope),
                "firecrawl_logical_calls": 0,
                "body_evaluable_count": 0,
                "results": [],
            }

        remaining_firecrawl = FIRECRAWL_LOGICAL_CAP
        results: list[dict[str, Any]] = []
        for item in items:
            before = remaining_firecrawl
            row = await observe_item(
                item,
                jina=jina,
                firecrawl=firecrawl,
                firecrawl_allowed=remaining_firecrawl > 0,
            )
            if bool(row.get("paid_fallback_used")):
                remaining_firecrawl -= 1
            row["global_firecrawl_remaining_before"] = before
            row["global_firecrawl_remaining_after"] = remaining_firecrawl
            results.append(row)

        results.sort(key=lambda row: int(row["manifest_ordinal"]))
        for row in results:
            row["network_request_count"] = counter.by_ordinal[int(row["manifest_ordinal"])]

        firecrawl_calls = sum(bool(row.get("paid_fallback_used")) for row in results)
        if firecrawl_calls > FIRECRAWL_LOGICAL_CAP:
            raise RuntimeError("S3-B Firecrawl logical cap exceeded")
        if counter.total > NETWORK_SAFETY_CAP:
            raise RuntimeError("S3-B network safety cap exceeded")
        if [row["url_canonical"] for row in results] != [row["url_canonical"] for row in items]:
            raise RuntimeError("S3-B result identity/order drift")

        return {
            **base,
            "status": "COMPLETED",
            "panel_requests_started": True,
            "network_request_count": counter.total,
            "network_requests_by_scope": dict(counter.by_scope),
            "firecrawl_logical_calls": firecrawl_calls,
            "body_evaluable_count": sum(bool(row.get("body_evaluable")) for row in results),
            "acquisition_failed_count": sum(row.get("acquisition_status") == "acquisition_failed" for row in results),
            "budget_censored_count": sum(row.get("acquisition_status") == "budget_censored" for row in results),
            "results": results,
        }
    finally:
        pacer.restore()
        counter.restore()


__all__ = [
    "ARTICLE_ATTEMPT_CAP",
    "FIRECRAWL_LOGICAL_CAP",
    "JINA_MIN_INTERVAL_SECONDS",
    "MANIFEST_ITEMS",
    "MANIFEST_SHA256",
    "NETWORK_SAFETY_CAP",
    "S3B_VERSION",
    "manifest_payload",
    "run_s3b",
    "validate_manifest",
]
