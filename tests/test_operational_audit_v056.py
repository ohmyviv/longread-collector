from __future__ import annotations

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.operational_audit_v056 import (
    annotate_discovery_schedule,
    annotate_fallback_attempts,
    classify_firecrawl_attempt,
    count_persisted_firecrawl_requests,
)


def article(attempts: list[dict]) -> ExtractedArticle:
    return ExtractedArticle(
        article_id="article-1",
        url="https://example.com/article.html",
        url_canonical="https://example.com/article.html",
        domain="example.com",
        title="Example article",
        metadata={},
        extraction_attempts=attempts,
    )


def test_one_real_request_and_three_group_skips_count_as_one() -> None:
    value = article(
        [
            {"extractor": "firecrawl", "success": True, "http_status": 200},
            {
                "extractor": "firecrawl",
                "success": False,
                "error_type": "GroupFallbackBudgetExhausted",
            },
            {
                "extractor": "firecrawl",
                "success": False,
                "error_type": "GroupFallbackBudgetExhausted",
            },
            {
                "extractor": "firecrawl",
                "success": False,
                "error_type": "GroupFallbackBudgetExhausted",
            },
        ]
    )
    counters = annotate_fallback_attempts(value, query_group="pre_report")
    assert counters.requests_sent == 1
    assert counters.requests_succeeded == 1
    assert counters.requests_failed == 0
    assert counters.requests_skipped_group_cap == 3
    assert counters.requests_skipped_daily_cap == 0
    assert value.extraction_attempts[0]["request_sent"] is True
    assert all(
        attempt["request_sent"] is False for attempt in value.extraction_attempts[1:]
    )


def test_real_failed_http_request_still_counts_as_sent() -> None:
    attempt = {
        "extractor": "firecrawl",
        "success": False,
        "error_type": "TimeoutError",
    }
    assert classify_firecrawl_attempt(attempt) == "request_failed"


def test_daily_and_group_budget_placeholders_never_count_as_sent() -> None:
    for error_type, expected in (
        ("DailyFallbackBudgetExhausted", "skipped_daily_cap"),
        ("GroupFallbackBudgetExhausted", "skipped_group_cap"),
    ):
        assert (
            classify_firecrawl_attempt(
                {"extractor": "firecrawl", "error_type": error_type}
            )
            == expected
        )


def test_persisted_request_count_uses_request_sent_and_legacy_inference() -> None:
    rows = [
        {
            "attempted_at_bj": "2026-08-02 04:40:00",
            "extractor": "firecrawl",
            "error_type": "",
            "response_meta_json": '{"query_group":"pre_report","request_sent":true}',
        },
        {
            "attempted_at_bj": "2026-08-02 04:40:01",
            "extractor": "firecrawl",
            "error_type": "GroupFallbackBudgetExhausted",
            "response_meta_json": '{"query_group":"pre_report","request_sent":false}',
        },
        {
            "attempted_at_bj": "2026-08-02 04:40:02",
            "extractor": "firecrawl",
            "error_type": "GroupFallbackBudgetExhausted",
            "response_meta_json": '{"query_group":"pre_report"}',
        },
        {
            "attempted_at_bj": "2026-08-02 04:40:03",
            "extractor": "firecrawl",
            "error_type": "DailyFallbackBudgetExhausted",
            "response_meta_json": '{"query_group":"pre_report"}',
        },
    ]
    assert (
        count_persisted_firecrawl_requests(
            rows,
            date_prefix="2026-08-02",
        )
        == 1
    )
    assert (
        count_persisted_firecrawl_requests(
            rows,
            date_prefix="2026-08-02",
            query_group="pre_report",
        )
        == 1
    )


def test_schedule_metadata_preserves_intended_and_actual_times() -> None:
    items = [
        DiscoveredURL(
            url="https://example.com/article.html",
            title="Article",
            metadata={"scheduled_time_bj": "19:06"},
        )
    ]
    annotate_discovery_schedule(
        items,
        scheduled_at_bj="2026-08-01 17:50:00",
        started_at_bj="2026-08-01 19:06:54",
        start_delay_seconds=4614,
    )
    metadata = items[0].metadata
    assert metadata["scheduled_time_bj"] == "17:50"
    assert metadata["scheduled_at_bj"] == "2026-08-01 17:50:00"
    assert metadata["run_started_at_bj"] == "2026-08-01 19:06:54"
    assert metadata["start_delay_seconds"] == 4614
