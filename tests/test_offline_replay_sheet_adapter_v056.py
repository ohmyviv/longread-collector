from __future__ import annotations

from longread_collector.offline_replay_sheet_adapter_v056 import (
    normalize_sheet_rows,
)

RUN_ID = "COL-20260801-190655-BJT-zh_evening"


def test_adapter_resolves_extracted_and_unextracted_truth_rows() -> None:
    snapshot_values = [
        [
            "snapshot_id",
            "collector_run_id",
            "source_id",
            "discovery_method",
            "query_or_source",
            "url",
            "url_canonical",
            "title",
            "discovered_rank",
            "article_id",
        ],
        [
            "snap-a",
            RUN_ID,
            "bjnews-depth",
            "section_scan",
            "source:bjnews-depth",
            "https://example.com/extracted",
            "https://example.com/extracted",
            "Extracted feature",
            "1",
            "article-a",
        ],
        [
            "snap-b",
            RUN_ID,
            "bjnews-depth",
            "section_scan",
            "source:bjnews-depth",
            "https://example.com/reserve",
            "https://example.com/reserve",
            "Reserve investigation",
            "3",
            "",
        ],
    ]
    review_values = [
        [
            "collector_run_id",
            "cache_row",
            "article_id",
            "title",
            "expected_disposition",
            "confidence",
            "review_status",
            "one_sentence_reason",
            "serious_false_accept",
            "should_enter_top32",
            "selection_regret",
        ],
        [
            RUN_ID,
            "222",
            "article-a",
            "Extracted feature",
            "formal_candidate",
            "high",
            "v055_stage3_ground_truth",
            "Valid extracted article.",
            "FALSE",
            "FALSE",
            "none",
        ],
        [
            RUN_ID,
            "3",
            "",
            "Reserve investigation",
            "formal_candidate",
            "high",
            "v055_stage3_capacity_ground_truth",
            "Should have entered Top 32.",
            "FALSE",
            "TRUE",
            "high",
        ],
    ]

    snapshots, truth = normalize_sheet_rows(
        snapshot_values=snapshot_values,
        review_values=review_values,
        run_ids={RUN_ID},
    )

    assert len(snapshots) == 2
    assert snapshots[0]["run_id"] == RUN_ID
    assert snapshots[0]["selection_group"] == "native"
    assert snapshots[0]["rank_score"] == "1"

    assert len(truth) == 2
    by_title = {row["title"]: row for row in truth}
    assert by_title["Extracted feature"]["url_canonical"].endswith("/extracted")
    assert by_title["Reserve investigation"]["url_canonical"].endswith("/reserve")
    assert (
        by_title["Reserve investigation"]["expected_candidate_disposition"]
        == "formal_candidate"
    )
    assert by_title["Reserve investigation"]["review_confidence"] == "high"


def test_adapter_ignores_interim_reviews_and_other_runs() -> None:
    snapshot_values = [
        ["snapshot_id", "collector_run_id", "url", "url_canonical", "title"],
        ["snap-a", RUN_ID, "https://example.com/a", "https://example.com/a", "A"],
    ]
    review_values = [
        [
            "collector_run_id",
            "cache_row",
            "article_id",
            "title",
            "expected_disposition",
            "confidence",
            "review_status",
        ],
        [RUN_ID, "2", "", "A", "reject", "high", "interim_only"],
    ]
    _, truth = normalize_sheet_rows(
        snapshot_values=snapshot_values,
        review_values=review_values,
        run_ids={RUN_ID},
    )
    assert truth == []
