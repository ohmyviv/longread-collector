"""Bounded Jiemian S3-B evidence completion.

This module is measurement-only. It implements the exact four-item blocker set
emitted by S3-A v1.1 and the frozen S3-B contract. It never writes the
Production cache, Editor, live selection ledger, source registry or scheduler.

Execution note: Actions run 33302533697 passed provider readiness and entered
manifest ordinal 1, then crashed while constructing the result row because the
shared S2-B observer expected a bookkeeping-only `deterministic_rank` field.
The crash occurred before ordinal 2 could start. To avoid resetting the
experiment after real sample exposure, ordinal 1 is permanently censored and
never re-requested; continuation requests only ordinals 2..4 under conservatively
reduced Firecrawl/network budgets.
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
EXECUTION_VERSION = "zh-route-shadow-s3b-execution-v1.1-partial-continuation"
SCHEMA_VERSION = "zh-route-shadow-s3b-results-v1.1"
MANIFEST_SCHEMA = "zh-route-shadow-s3b-manifest-v1"
MANIFEST_SHA256 = "ff4fe7d54b1c38b3105329ec5653bed14799e7ae493bd36dc4d93fd88bfbc865"
ARTICLE_ATTEMPT_CAP = 4
FROZEN_FIRECRAWL_LOGICAL_CAP = 2
FROZEN_NETWORK_SAFETY_CAP = 40
JINA_MIN_INTERVAL_SECONDS = 3.1

# Immutable execution history. Run 33302365508 failed before any network call.
ZERO_NETWORK_INIT_FAILURE_RUN_ID = 33302365508
PARTIAL_NETWORK_RUN_ID = 33302533697
INSTRUMENTATION_CENSORED_ORDINALS = (1,)
CONTINUATION_ORDINALS = (2, 3, 4)

# We cannot recover exact request telemetry from the crashed process, so consume
# the worst-case amount that ordinal 1 could have used. This guarantees the
# original experiment-wide caps cannot be exceeded by continuation.
PRIOR_NETWORK_REQUESTS_UPPER_BOUND = 16  # 3 canaries*3 + direct 1 + Jina*3 + Firecrawl*3
CONTINUATION_NETWORK_SAFETY_CAP = FROZEN_NETWORK_SAFETY_CAP - PRIOR_NETWORK_REQUESTS_UPPER_BOUND
PRIOR_FIRECRAWL_LOGICAL_UPPER_BOUND = 1
CONTINUATION_FIRECRAWL_LOGICAL_CAP = FROZEN_FIRECRAWL_LOGICAL_CAP - PRIOR_FIRECRAWL_LOGICAL_UPPER_BOUND

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


def _instrumentation_censored_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_ordinal": int(item["manifest_ordinal"]),
        "url_canonical": item["url_canonical"],
        "source_id": item["source_id"],
        "first_surface": item["first_surface"],
        "metadata_class": item["metadata_class"],
        "sampling_role": item["sampling_role"],
        "deterministic_rank": int(item["manifest_ordinal"]),
        "manifest_title": item["title"],
        "acquisition_status": "instrumentation_censored",
        "body_evaluable": False,
        "censoring_reason": "prior_network_attempt_result_lost_after_observe_before_row_return",
        "paid_fallback_used": None,
        "network_request_count": None,
        "extraction_attempts": [],
        "extractor_used": "unknown_prior_attempt",
        "valid_article_body": False,
        "page_quality_reason": "not_evaluable_instrumentation_failure_after_network_attempt",
        "prose_chars": 0,
        "content_chars": 0,
        "content_sha256": "",
        "content_markdown": "",
        "content_truncated": False,
        "extracted_title": "",
        "author": "",
        "published_at": "",
        "prior_partial_run_id": PARTIAL_NETWORK_RUN_ID,
        "re_request_forbidden": True,
    }


async def run_s3b(settings: Settings) -> dict[str, Any]:
    """Continue the frozen four-item experiment without re-requesting ordinal 1."""
    items = validate_manifest()
    counter = NetworkCounter(cap=CONTINUATION_NETWORK_SAFETY_CAP)
    pacer = JinaFreeTierPacer(min_interval_seconds=JINA_MIN_INTERVAL_SECONDS)
    jina = JinaReaderClient(settings.jina_reader_base_url, api_key=None)
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)

    counter.install()
    pacer.install()
    try:
        canary = await run_canaries(jina)
        censored = _instrumentation_censored_row(items[0])
        base = {
            "schema_version": SCHEMA_VERSION,
            "experiment_version": S3B_VERSION,
            "execution_version": EXECUTION_VERSION,
            "manifest": manifest_payload(),
            "manifest_sha256": MANIFEST_SHA256,
            "manifest_count": ARTICLE_ATTEMPT_CAP,
            "existing_evidence_gate_checked": True,
            "existing_evidence_reusable_count": 0,
            "existing_evidence_sources": ["article_cache", "extraction_log", "s2b_v21_results"],
            "zero_network_init_failure_run_id": ZERO_NETWORK_INIT_FAILURE_RUN_ID,
            "prior_partial_network_run_id": PARTIAL_NETWORK_RUN_ID,
            "prior_attempted_ordinals": list(INSTRUMENTATION_CENSORED_ORDINALS),
            "continuation_ordinals": list(CONTINUATION_ORDINALS),
            "prior_network_requests_upper_bound": PRIOR_NETWORK_REQUESTS_UPPER_BOUND,
            "continuation_network_safety_cap": CONTINUATION_NETWORK_SAFETY_CAP,
            "frozen_experiment_network_safety_cap": FROZEN_NETWORK_SAFETY_CAP,
            "prior_firecrawl_logical_upper_bound": PRIOR_FIRECRAWL_LOGICAL_UPPER_BOUND,
            "continuation_firecrawl_logical_cap": CONTINUATION_FIRECRAWL_LOGICAL_CAP,
            "frozen_experiment_firecrawl_logical_cap": FROZEN_FIRECRAWL_LOGICAL_CAP,
            "jina_auth_mode": "unauthenticated_free_tier",
            "jina_authorization_header_sent": False,
            "jina_min_request_interval_seconds": JINA_MIN_INTERVAL_SECONDS,
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
                "instrumentation_censored_count": 1,
                "results": [censored],
            }

        remaining_firecrawl = CONTINUATION_FIRECRAWL_LOGICAL_CAP
        results: list[dict[str, Any]] = [censored]
        for item in items[1:]:
            if int(item["manifest_ordinal"]) not in CONTINUATION_ORDINALS:
                raise RuntimeError("unexpected continuation ordinal")
            before = remaining_firecrawl
            # `deterministic_rank` is bookkeeping required by the shared observer;
            # it is injected only into the working copy and never changes the frozen manifest/hash.
            working_item = {**item, "deterministic_rank": int(item["manifest_ordinal"])}
            row = await observe_item(
                working_item,
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
            ordinal = int(row["manifest_ordinal"])
            if ordinal in CONTINUATION_ORDINALS:
                row["network_request_count"] = counter.by_ordinal[ordinal]

        firecrawl_calls = sum(bool(row.get("paid_fallback_used")) for row in results if row.get("paid_fallback_used") is not None)
        if firecrawl_calls > CONTINUATION_FIRECRAWL_LOGICAL_CAP:
            raise RuntimeError("S3-B continuation Firecrawl logical cap exceeded")
        if counter.total > CONTINUATION_NETWORK_SAFETY_CAP:
            raise RuntimeError("S3-B continuation network safety cap exceeded")
        if PRIOR_NETWORK_REQUESTS_UPPER_BOUND + counter.total > FROZEN_NETWORK_SAFETY_CAP:
            raise RuntimeError("S3-B cumulative worst-case network cap exceeded")
        if PRIOR_FIRECRAWL_LOGICAL_UPPER_BOUND + firecrawl_calls > FROZEN_FIRECRAWL_LOGICAL_CAP:
            raise RuntimeError("S3-B cumulative worst-case Firecrawl cap exceeded")
        if [row["url_canonical"] for row in results] != [row["url_canonical"] for row in items]:
            raise RuntimeError("S3-B result identity/order drift")

        return {
            **base,
            "status": "COMPLETED_WITH_INSTRUMENTATION_CENSORING",
            "panel_requests_started": True,
            "network_request_count": counter.total,
            "network_requests_by_scope": dict(counter.by_scope),
            "cumulative_network_requests_upper_bound": PRIOR_NETWORK_REQUESTS_UPPER_BOUND + counter.total,
            "firecrawl_logical_calls": firecrawl_calls,
            "cumulative_firecrawl_logical_upper_bound": PRIOR_FIRECRAWL_LOGICAL_UPPER_BOUND + firecrawl_calls,
            "body_evaluable_count": sum(bool(row.get("body_evaluable")) for row in results),
            "instrumentation_censored_count": 1,
            "acquisition_failed_count": sum(row.get("acquisition_status") == "acquisition_failed" for row in results),
            "budget_censored_count": sum(row.get("acquisition_status") == "budget_censored" for row in results),
            "results": results,
        }
    finally:
        pacer.restore()
        counter.restore()


__all__ = [
    "ARTICLE_ATTEMPT_CAP",
    "CONTINUATION_FIRECRAWL_LOGICAL_CAP",
    "CONTINUATION_NETWORK_SAFETY_CAP",
    "CONTINUATION_ORDINALS",
    "EXECUTION_VERSION",
    "FROZEN_FIRECRAWL_LOGICAL_CAP",
    "FROZEN_NETWORK_SAFETY_CAP",
    "INSTRUMENTATION_CENSORED_ORDINALS",
    "JINA_MIN_INTERVAL_SECONDS",
    "MANIFEST_ITEMS",
    "MANIFEST_SHA256",
    "PARTIAL_NETWORK_RUN_ID",
    "S3B_VERSION",
    "manifest_payload",
    "run_s3b",
    "validate_manifest",
]
