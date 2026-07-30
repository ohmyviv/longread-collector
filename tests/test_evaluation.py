from __future__ import annotations

from longread_collector.evaluation import calculate_metrics
from longread_collector.models import ExtractedArticle
from longread_collector.shadow import build_shadow_row


def test_calculate_metrics_applies_release_thresholds() -> None:
    ground_truth = [
        {
            "review_index": 1,
            "article_id": "formal",
            "page_type": "article",
            "disposition": "formal_candidate",
        },
        {
            "review_index": 2,
            "article_id": "chase",
            "page_type": "article",
            "disposition": "original_source_required",
        },
        {
            "review_index": 3,
            "article_id": "reject",
            "page_type": "job_or_career",
            "disposition": "reject",
        },
        {
            "review_index": 21,
            "article_id": "wire-21",
            "page_type": "article",
            "disposition": "reject",
        },
        {
            "review_index": 46,
            "article_id": "wire-46",
            "page_type": "article",
            "disposition": "reject",
        },
        {
            "review_index": 48,
            "article_id": "wire-48",
            "page_type": "article",
            "disposition": "reject",
        },
    ]
    predictions = {
        "formal": {"candidate_disposition": "formal_candidate"},
        "chase": {"candidate_disposition": "original_source_required"},
        "reject": {"candidate_disposition": "reject"},
        "wire-21": {
            "candidate_disposition": "reject",
            "content_cluster_id": "wire-ap-clean-energy-grants-2026-07",
        },
        "wire-46": {
            "candidate_disposition": "reject",
            "content_cluster_id": "wire-ap-clean-energy-grants-2026-07",
        },
        "wire-48": {
            "candidate_disposition": "reject",
            "content_cluster_id": "wire-ap-clean-energy-grants-2026-07",
        },
    }
    metrics = calculate_metrics(ground_truth, predictions)
    assert metrics.overall_accuracy == 1.0
    assert metrics.candidate_precision == 1.0
    assert metrics.source_chase_recall == 1.0
    assert metrics.critical_false_accepts == 0
    assert metrics.wire_dedup_accuracy == 1.0
    assert metrics.metrics_gate == "METRICS_READY"


def test_shadow_row_preserves_v03_technical_signal() -> None:
    formal = ExtractedArticle(
        article_id="formal",
        url="https://example.com/analysis/story",
        url_canonical="https://example.com/analysis/story",
        domain="example.com",
        title="A substantial analysis",
        published_at="2026-07-30",
        verification_level="B",
        content_chars=5000,
        content_markdown="substantive evidence " * 400,
        eligible_for_editor=True,
    )
    rejected = ExtractedArticle(
        article_id="job",
        url="https://jobs.example.com/job/123",
        url_canonical="https://jobs.example.com/job/123",
        domain="jobs.example.com",
        title="Research writer",
        verification_level="B",
        content_chars=5000,
        content_markdown="job description " * 400,
        eligible_for_editor=True,
    )
    row = build_shadow_row(
        run_id="COL-1",
        completed_at_bj="2026-07-30 09:00:00",
        query_group="pre_report",
        articles=[formal, rejected],
    )
    assert row[3] == 2
    assert row[4] == 2
    assert row[5] == 1
    assert row[8] == 1
    assert row[9] == 1
    assert row[10] == 0
