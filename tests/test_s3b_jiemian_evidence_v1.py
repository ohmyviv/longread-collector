from __future__ import annotations

import asyncio
from types import SimpleNamespace

from longread_collector import zh_route_shadow_s3b_evidence_v1 as s3b


EXPECTED_URLS = [
    "https://jiemian.com/article/14977759.html",
    "https://jiemian.com/article/14997276.html",
    "https://jiemian.com/article/14998723.html",
    "https://jiemian.com/article/15018993.html",
]


def _settings():
    return SimpleNamespace(
        jina_reader_base_url="https://r.jina.ai/http://",
        firecrawl_base_url="https://api.firecrawl.dev/v1",
        firecrawl_api_key="test",
    )


def test_manifest_is_exact_and_hashed() -> None:
    payload = s3b.manifest_payload()
    assert payload["manifest_count"] == 4
    assert payload["manifest_sha256"] == "ff4fe7d54b1c38b3105329ec5653bed14799e7ae493bd36dc4d93fd88bfbc865"
    assert [row["url_canonical"] for row in payload["items"]] == EXPECTED_URLS
    assert [row["manifest_ordinal"] for row in payload["items"]] == [1, 2, 3, 4]
    assert {row["source_id"] for row in payload["items"]} == {"jiemian-depth"}
    assert s3b.FIRECRAWL_LOGICAL_CAP == 2
    assert s3b.NETWORK_SAFETY_CAP == 40
    assert s3b.JINA_MIN_INTERVAL_SECONDS >= 3.1


def test_provider_not_ready_fails_before_panel(monkeypatch) -> None:
    async def fake_canary(_jina):
        return {"status": "PROVIDER_NOT_READY", "rows": [], "success_count": 0, "provider_failure_count": 3}

    async def forbidden_observe(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("panel request started despite failed provider gate")

    monkeypatch.setattr(s3b, "run_canaries", fake_canary)
    monkeypatch.setattr(s3b, "observe_item", forbidden_observe)
    result = asyncio.run(s3b.run_s3b(_settings()))
    assert result["status"] == "PROVIDER_NOT_READY"
    assert result["panel_requests_started"] is False
    assert result["results"] == []
    assert result["jina_authorization_header_sent"] is False
    assert result["article_cache_writes"] == 0
    assert result["editor_writes"] == 0


def test_global_firecrawl_cap_and_no_replacement(monkeypatch) -> None:
    async def fake_canary(_jina):
        return {"status": "READY", "rows": [], "success_count": 3, "provider_failure_count": 0}

    allowed: list[bool] = []

    async def fake_observe(item, *, jina, firecrawl, firecrawl_allowed):
        allowed.append(bool(firecrawl_allowed))
        use_fallback = bool(firecrawl_allowed)
        return {
            "manifest_ordinal": item["manifest_ordinal"],
            "url_canonical": item["url_canonical"],
            "source_id": item["source_id"],
            "first_surface": item["first_surface"],
            "metadata_class": item["metadata_class"],
            "sampling_role": item["sampling_role"],
            "deterministic_rank": item["manifest_ordinal"],
            "manifest_title": item["title"],
            "acquisition_status": "body_observed",
            "body_evaluable": True,
            "censoring_reason": "",
            "paid_fallback_used": use_fallback,
            "network_request_count": 0,
            "extraction_attempts": [],
            "extractor_used": "firecrawl" if use_fallback else "direct_html",
            "valid_article_body": True,
            "page_quality_reason": "ok",
            "prose_chars": 3000,
            "content_chars": 3000,
            "content_sha256": "x",
            "content_markdown": "body",
            "content_truncated": False,
            "extracted_title": item["title"],
            "author": "",
            "published_at": "",
        }

    monkeypatch.setattr(s3b, "run_canaries", fake_canary)
    monkeypatch.setattr(s3b, "observe_item", fake_observe)
    result = asyncio.run(s3b.run_s3b(_settings()))

    assert result["status"] == "COMPLETED"
    assert [row["url_canonical"] for row in result["results"]] == EXPECTED_URLS
    assert len(result["results"]) == 4
    assert allowed == [True, True, False, False]
    assert result["firecrawl_logical_calls"] == 2
    assert result["existing_evidence_reusable_count"] == 0
    assert result["live_sheet_writes"] == 0
    assert result["live_selection_writes"] == 0
