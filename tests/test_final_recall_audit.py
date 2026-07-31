from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.final_recall_audit import (
    build_daily_summary,
    classify_match,
    select_best_match,
)

TZ = ZoneInfo("Asia/Shanghai")


def final_row(**overrides):
    row = {
        "title": "A Deep Investigation Into Battery Supply Chains",
        "title_zh": "",
        "title_norm": "",
        "url": "https://example.com/story?utm_source=test",
        "url_canonical": "https://example.com/story?utm_source=test",
        "canonical_source": "Example",
        "language": "en",
        "is_outside_pool": False,
    }
    row.update(overrides)
    return row


def snapshot(**overrides):
    row = {
        "snapshot_id": "snap-1",
        "collector_run_id": "COL-1",
        "captured_at_bj": "2026-07-31 05:20:00",
        "query_group": "pre_report",
        "url": "https://example.com/story",
        "url_canonical": "https://example.com/story",
        "title": "A Deep Investigation Into Battery Supply Chains",
        "title_norm": "adeepinvestigationintobatterysupplychains",
        "canonical_source": "Example",
        "prefilter_status": "accepted_for_extraction",
        "extraction_status": "success",
        "eligible_for_editor": "TRUE",
        "candidate_disposition": "formal_candidate",
        "article_id": "article-1",
    }
    row.update(overrides)
    return row


def test_exact_url_match_removes_tracking_parameters():
    matched, match_type, manual = select_best_match(final_row(), [snapshot()], TZ)
    assert matched is not None
    assert match_type == "exact_url"
    assert manual is False


def test_normalized_title_match_handles_different_url():
    matched, match_type, manual = select_best_match(
        final_row(
            url="https://syndication.example/item",
            url_canonical="https://syndication.example/item",
        ),
        [
            snapshot(
                url="https://example.com/other",
                url_canonical="https://example.com/other",
            )
        ],
        TZ,
    )
    assert matched is not None
    assert match_type == "normalized_title"
    assert manual is False


def test_same_story_match_requires_manual_review():
    matched, match_type, manual = select_best_match(
        final_row(
            title="Deep Investigation of Battery Supply Chain",
            url="https://example.com/final",
            url_canonical="https://example.com/final",
        ),
        [
            snapshot(
                title="A Deep Investigation Into Battery Supply Chains",
                title_norm="adeepinvestigationintobatterysupplychains",
                url="https://example.com/discovered",
                url_canonical="https://example.com/discovered",
            )
        ],
        TZ,
    )
    assert matched is not None
    assert match_type == "same_story"
    assert manual is True


def test_match_outcome_distinguishes_pipeline_stages():
    cutoff = datetime(2026, 7, 31, 7, 35, tzinfo=TZ)
    assert classify_match(
        snapshot(
            prefilter_status="prefilter_rejected",
            prefilter_reject_reason="homepage",
        ),
        source_pool_status="in_pool",
        published_at=None,
        cutoff=cutoff,
    ) == ("captured_but_rejected", "prefilter")
    assert classify_match(
        snapshot(extraction_status="failed", eligible_for_editor="FALSE"),
        source_pool_status="in_pool",
        published_at=None,
        cutoff=cutoff,
    ) == ("captured_extraction_failed", "extraction")
    assert classify_match(
        snapshot(),
        source_pool_status="in_pool",
        published_at=None,
        cutoff=cutoff,
    ) == ("captured_eligible", "eligible")


def test_no_match_outcomes():
    cutoff = datetime(2026, 7, 31, 7, 35, tzinfo=TZ)
    assert classify_match(
        None,
        source_pool_status="outside_pool",
        published_at=None,
        cutoff=cutoff,
    ) == ("manual_source_only", "manual_outside_pool")
    assert classify_match(
        None,
        source_pool_status="in_pool",
        published_at=datetime(2026, 7, 31, 8, 0, tzinfo=TZ),
        cutoff=cutoff,
    ) == ("not_yet_available", "availability")
    assert classify_match(
        None,
        source_pool_status="in_pool",
        published_at=None,
        cutoff=cutoff,
    ) == ("not_discovered", "discovery")


def test_daily_summary_uses_available_items_as_denominator():
    rows = [
        {
            "match_status": "captured_eligible",
            "match_type": "exact_url",
            "language": "zh",
            "source_pool_status": "in_pool",
            "manual_review_required": "FALSE",
        },
        {
            "match_status": "captured_but_rejected",
            "match_type": "normalized_title",
            "language": "en",
            "source_pool_status": "in_pool",
            "manual_review_required": "FALSE",
        },
        {
            "match_status": "not_yet_available",
            "match_type": "none",
            "language": "en",
            "source_pool_status": "outside_pool",
            "manual_review_required": "FALSE",
        },
    ]
    collector_runs = [
        {"query_group": group}
        for group in ("zh_midday", "zh_evening", "intl_early", "pre_report")
    ]
    result = build_daily_summary(
        rows,
        report_date="2026-07-31",
        final_run_id="LR-1",
        collector_runs=collector_runs,
        cutoff=datetime(2026, 7, 31, 7, 35, tzinfo=TZ),
        lookback_hours=48,
        snapshot_mode="immutable_snapshot",
        audited_at="2026-07-31 08:20:00",
    )
    assert result["eligible_denominator"] == 2
    assert result["discovered_matches"] == 2
    assert result["editable_matches"] == 1
    assert result["discovery_recall"] == 1.0
    assert result["editable_recall"] == 0.5
    assert result["audit_status"] == "complete"
