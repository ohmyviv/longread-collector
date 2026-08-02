from __future__ import annotations

from longread_collector.final_recall_audit_v11 import (
    classify_source_coverage,
    enrich_recall_result,
)


def source(index: int, *, partial: bool = False) -> dict:
    domain = f"source{index}.example.com"
    return {
        "source_id": f"source-{index}",
        "source_name": f"Source {index}",
        "homepage_url": f"https://{domain}/",
        "rss_url": "" if partial else f"https://{domain}/feed.xml",
        "sitemap_url": "",
        "news_sitemap_url": "",
        "author_pages": "",
        "newsletter_url": "",
        "discovery_method": "section_scan" if partial else "rss",
        "parser_config_json": '{"lookback_days":7}',
    }


def final_item(index: int, *, registered: bool, status: str) -> dict:
    domain = f"source{index}.example.com" if registered else f"outside{index}.example.com"
    return {
        "audit_id": f"audit-{index}",
        "report_date": "2026-08-02",
        "final_run_id": "LR-20260802-0738-BJT-LRv34",
        "item_index": index,
        "final_source": f"Source {index}" if registered else f"Outside {index}",
        "final_url_canonical": f"https://{domain}/article-{index}.html",
        "source_pool_status": "in_pool",
        "match_status": status,
        "match_type": "exact_url" if status != "not_discovered" else "none",
        "audit_version": "final-recall-audit-v1.0",
    }


def test_source_coverage_separates_editor_pool_registry_and_route() -> None:
    final = final_item(1, registered=True, status="not_discovered")
    coverage = classify_source_coverage(final, [source(1)])
    assert coverage.editor_source_allowed is True
    assert coverage.registry_status == "registered"
    assert coverage.effective_route_status == "effective_native"
    assert coverage.route_lookback_hours == 168
    assert coverage.promotion_denominator_status == "effective_route_denominator"


def test_partial_registration_is_not_mislabeled_as_full_coverage() -> None:
    final = final_item(2, registered=True, status="not_discovered")
    coverage = classify_source_coverage(final, [source(2, partial=True)])
    assert coverage.registry_status == "registered_partial"
    assert coverage.effective_route_status == "partial_native"
    assert coverage.promotion_denominator_status == "effective_route_denominator"


def test_outside_registry_remains_editor_allowed_but_excluded_from_registry_denominator() -> None:
    final = final_item(9, registered=False, status="not_discovered")
    coverage = classify_source_coverage(final, [source(1)])
    assert coverage.editor_source_allowed is True
    assert coverage.registry_status == "outside_registry"
    assert coverage.promotion_denominator_status == "outside_registry"


def test_stage_four_sample_reproduces_ten_eight_two_one_denominators() -> None:
    sources = [source(index, partial=index in {4, 5, 7, 8}) for index in range(1, 9)]
    items = [
        final_item(
            index,
            registered=index <= 8,
            status="captured_but_rejected" if index == 7 else "not_discovered",
        )
        for index in range(1, 11)
    ]
    base = {
        "items": items,
        "summary": {
            "report_date": "2026-08-02",
            "final_run_id": "LR-20260802-0738-BJT-LRv34",
            "final_items": 10,
            "eligible_denominator": 10,
            "discovered_matches": 1,
            "editable_matches": 0,
            "discovery_recall": 0.1,
            "editable_recall": 0.0,
            "audit_version": "final-recall-audit-v1.0",
        },
        "snapshot_mode": "immutable_snapshot",
    }
    result = enrich_recall_result(base, sources)
    summary = result["summary"]
    assert len(result["items"]) == 10
    assert summary["registered_denominator"] == 8
    assert summary["source_pool_gaps"] == 2
    assert summary["registered_discovered"] == 1
    assert summary["registered_discovery_recall"] == 0.125
    assert summary["registered_editable"] == 0
    assert summary["registered_editable_recall"] == 0.0
    assert summary["registered_route_misses"] == 7
