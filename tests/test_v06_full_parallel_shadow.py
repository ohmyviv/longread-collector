from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.v06.contracts import RunContext
from longread_collector.v06.shadow.runner import FullParallelShadowRunner


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-TEST-PR7",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-07 17:50:00",
        started_at_bj="2026-08-07 17:51:00",
        collector_version="collector-v0.6-pr7",
        max_acquisition_attempts=32,
        firecrawl_daily_limit=3,
    )


def _article(discovered: DiscoveredURL, *, article_id: str, disposition: str = "formal_candidate") -> ExtractedArticle:
    body = (
        "# Deep reported feature\n\n"
        "记者采访了多位研究人员，并查阅公开文件和历史数据。" * 80
        + "\n\nThe reporting includes evidence, chronology, competing explanations and context. " * 40
    )
    return ExtractedArticle(
        article_id=article_id,
        url=discovered.url,
        url_canonical=discovered.url,
        domain="example.com",
        title=discovered.title or "Deep reported feature",
        published_at="2026-08-07T10:00:00+08:00",
        hosting_source="Example",
        canonical_source="Example",
        source_relationship="original",
        source_action="none",
        page_role="standalone_content",
        page_type="article",
        content_type="reported_feature",
        candidate_disposition=disposition,
        classification_confidence="high",
        classification_version="collector-v0.5.6m",
        classification_reason="fixture",
        extraction_status="success",
        verification_level="A",
        content_markdown=body,
        content_chars=len(body),
        eligible_for_editor=disposition == "formal_candidate",
        metadata={
            "valid_article_body": True,
            "content_metrics": {
                "body_prose_chars": len(body),
                "template_chars": 0,
                "image_count": 0,
                "video_count": 0,
            },
        },
        extraction_attempts=[
            {
                "extractor": "jina",
                "success": True,
                "request_sent": True,
                "request_outcome": "request_succeeded",
                "body_chars": len(body),
                "credits_used": 0,
            },
            {
                "extractor": "firecrawl",
                "success": True,
                "request_sent": True,
                "request_outcome": "request_succeeded",
                "body_chars": len(body),
                "credits_used": 1,
            },
        ],
    )


def test_full_parallel_shadow_reuses_snapshot_and_bodies_without_requests() -> None:
    normal = DiscoveredURL(
        url="https://example.com/features/deep-report.html",
        title="Deep reported feature",
        published_at="2026-08-07T10:00:00+08:00",
        discovery_method="rss",
        metadata={"source_id": "example", "purpose": "native_source_scan"},
    )
    login = DiscoveredURL(
        url="https://example.com/login",
        title="A misleading control fixture",
        discovery_method="section_scan",
        metadata={"source_id": "example"},
    )
    unacquired = DiscoveredURL(
        url="https://another.example.com/story/unobserved",
        title="Potentially valuable unobserved story",
        discovery_method="firecrawl_search",
    )
    captured = (
        SimpleNamespace(item=normal, prefilter_status="accepted_for_extraction", prefilter_reject_reason=""),
        SimpleNamespace(item=login, prefilter_status="accepted_for_extraction", prefilter_reject_reason=""),
        SimpleNamespace(item=unacquired, prefilter_status="not_selected_capacity", prefilter_reject_reason="deferred_not_extracted"),
    )
    pairs = (
        (normal, _article(normal, article_id="a-normal")),
        (login, _article(login, article_id="a-login")),
    )

    report = FullParallelShadowRunner().run(
        _context(),
        captured_discoveries=captured,
        acquired_pairs=pairs,
        now_bj=datetime(2026, 8, 7, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    payload = report.as_dict()

    assert payload["discovery_snapshot_count"] == 3
    assert payload["control_acquired_count"] == 2
    assert payload["shared_body_count"] == 2
    assert payload["shadow_request_count"] == 0
    assert payload["shadow_firecrawl_request_count"] == 0
    assert payload["shadow_incremental_cost"] == 0.0
    assert payload["zero_duplicate_network_invariant"] is True
    assert payload["body_fingerprint_mismatches"] == 0
    assert any(item["gate_action"] == "hard_reject" for item in payload["items"])
    assert any(
        item["difference_tags"] and "gate_rejects_legacy_actionable" in item["difference_tags"]
        for item in payload["items"]
    )
    unobserved = next(item for item in payload["items"] if "unobserved" in item["url"])
    assert unobserved["acquired_by_control"] is False
    assert unobserved["v06_policy_action"] == "defer"
    assert "control_did_not_acquire_gate_pass" in unobserved["difference_tags"]
    assert payload["event_count"] >= 3 * 3
    assert len(payload["event_digest_sha256"]) == 64


def test_shadow_failure_is_fail_open_and_preserves_legacy_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector.v06.shadow.pipeline import ParallelShadowCollectorPipeline
    from longread_collector import pipeline_v056f

    async def fake_control_collect(self, group_id=None, query_file=None):
        return {
            "collector_run_id": "COL-CONTROL",
            "started_at_bj": "2026-08-07 17:51:00",
            "scheduled_at_bj": "2026-08-07 17:50:00",
            "final_status": "success",
            "written_cache": 7,
        }

    def explode(*args, **kwargs):
        raise RuntimeError("shadow-only failure")

    monkeypatch.setattr(pipeline_v056f.NativeCollectorPipeline, "collect", fake_control_collect)

    pipeline = ParallelShadowCollectorPipeline.__new__(ParallelShadowCollectorPipeline)
    pipeline.settings = SimpleNamespace(max_urls_per_run=32, firecrawl_fallback_daily_limit=3)
    pipeline.tz = ZoneInfo("Asia/Shanghai")
    pipeline._v06_acquired_pairs = []
    pipeline._v06_runner = SimpleNamespace(run=explode)

    result = asyncio.run(pipeline.collect(group_id="zh_evening"))

    assert result["final_status"] == "success"
    assert result["written_cache"] == 7
    assert result["v06_shadow"]["status"] == "failed_open"
    assert result["v06_shadow"]["control_result_preserved"] is True
    assert result["v06_shadow"]["shadow_request_count"] == 0
