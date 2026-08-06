from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.v06.audit.metrics import summarize_stage_events
from longread_collector.v06.contracts import RunContext, StageEventType
from longread_collector.v06.legacy.adapter import LegacyV056mAdapter


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="run-1",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-06 17:50:00",
        started_at_bj="2026-08-06 19:52:35",
        collector_version="collector-v0.5.6m",
    )


def _pair(
    item_id: str,
    disposition: str,
    extractor: str,
    attempts: list[dict[str, object]],
    status: str = "success",
) -> tuple[DiscoveredURL, ExtractedArticle]:
    discovered = DiscoveredURL(
        url=f"https://example.com/{item_id}",
        title=f"Title {item_id}",
        metadata={"selection": {"selected_order": 1}},
    )
    article = ExtractedArticle(
        article_id=item_id,
        url=discovered.url,
        url_canonical=discovered.url,
        domain="example.com",
        title=discovered.title,
        content_markdown="Body " * 500,
        content_chars=2500,
        extractor_used=extractor,
        extraction_status=status,
        candidate_disposition=disposition,
        eligible_for_editor=disposition == "formal_candidate",
        page_type="article",
        content_type="reported_feature",
        classification_confidence="high",
        classification_version="collector-v0.5.6m",
        metadata={"valid_article_body": status == "success"},
        extraction_attempts=attempts,
    )
    return discovered, article


def test_metrics_are_derived_from_attempt_events_and_close_items() -> None:
    pairs = [
        _pair(
            "a1",
            "formal_candidate",
            "jina",
            [
                {
                    "extractor": "jina",
                    "success": True,
                    "body_chars": 2500,
                }
            ],
        ),
        _pair(
            "a2",
            "reject",
            "firecrawl",
            [
                {
                    "extractor": "jina",
                    "success": False,
                    "body_chars": 0,
                    "error_type": "TimeoutError",
                },
                {
                    "extractor": "firecrawl",
                    "success": True,
                    "body_chars": 2600,
                    "request_sent": True,
                },
            ],
        ),
        _pair(
            "a3",
            "reject",
            "none",
            [
                {
                    "extractor": "firecrawl",
                    "success": False,
                    "body_chars": 0,
                    "error_type": "GroupFallbackBudgetExhausted",
                    "request_sent": False,
                }
            ],
            status="failed",
        ),
    ]
    legacy_summary = {
        "jina_success": 1,
        "firecrawl_success": 1,
        "failed": 1,
        "fallback_request_audit": {
            "requests_sent": 1,
            "requests_succeeded": 1,
            "requests_failed": 0,
            "requests_skipped_group_cap": 1,
            "requests_skipped_daily_cap": 0,
        },
    }

    run = LegacyV056mAdapter().adapt_run(
        context=_context(),
        pairs=pairs,
        legacy_summary=legacy_summary,
    )
    metrics = run.metrics

    assert metrics.item_count == 3
    assert metrics.closed_item_count == 3
    assert metrics.incomplete_item_count == 0
    assert metrics.disposition_counts == {"formal_candidate": 1, "reject": 2}
    assert metrics.extractor_attempt_counts == {"jina": 2, "firecrawl": 2}
    assert metrics.firecrawl_requests_sent == 1
    assert metrics.firecrawl_requests_succeeded == 1
    assert metrics.firecrawl_requests_failed == 0
    assert metrics.firecrawl_requests_skipped_group_cap == 1
    assert metrics.selected_extractor_success_counts == {
        "jina": 1,
        "firecrawl": 1,
    }
    assert metrics.acquisition_success_count == 2
    assert metrics.acquisition_failed_count == 1
    assert metrics.eligible_for_editor_count == 1
    assert run.legacy_summary_comparison is not None
    assert run.legacy_summary_comparison.is_closed is True


def test_closure_reports_missing_terminal_event() -> None:
    discovered, article = _pair(
        "a1",
        "formal_candidate",
        "jina",
        [{"extractor": "jina", "success": True, "body_chars": 2500}],
    )
    item = LegacyV056mAdapter().adapt_item(
        context=_context(),
        discovered=discovered,
        article=article,
    )
    events = tuple(
        event
        for event in item.events
        if event.event_type is not StageEventType.PROJECTION_RESULT
    )
    metrics = summarize_stage_events(events)
    assert metrics.closed_item_count == 0
    assert metrics.incomplete_item_count == 1
    assert metrics.closure_errors == ("a1:missing=projection_result",)
