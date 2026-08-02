from __future__ import annotations

import json

from longread_collector.offline_replay_v056 import aggregate_metrics, replay_run

RUN_ID = "COL-20260801-190655-BJT-zh_evening"


def snapshot(
    url: str,
    title: str,
    *,
    published_at: str = "2026-08-01",
    description: str = "A complete reported article.",
    source_id: str = "source-a",
) -> dict:
    return {
        "run_id": RUN_ID,
        "url": url,
        "url_canonical": url,
        "title": title,
        "description": description,
        "published_at": published_at,
        "query_id": "query-a",
        "source_id": source_id,
        "source_name": source_id,
        "discovery_method": "rss",
        "rank_score": 1,
        "selection_group": "native",
        "metadata_json": json.dumps(
            {
                "purpose": "native_source_scan",
                "source_id": source_id,
                "native_method": "rss",
                "selection": {"historical": True},
                "freshness": {"historical": True},
                "page_gate": {"historical": True},
            }
        ),
    }


def truth(
    url: str,
    title: str,
    disposition: str,
    *,
    serious: bool = False,
    should_enter: bool = False,
    regret: bool = False,
) -> dict:
    return {
        "run_id": RUN_ID,
        "url": url,
        "url_canonical": url,
        "title": title,
        "expected_candidate_disposition": disposition,
        "serious_false_accept": str(serious).upper(),
        "should_enter_top32": str(should_enter).upper(),
        "selection_regret": str(regret).upper(),
        "review_confidence": "high",
        "audit_status": "v055_stage3_ground_truth",
        "review_reason": "synthetic truth",
    }


def test_replay_applies_gates_and_selects_true_candidates() -> None:
    good_one = snapshot(
        "https://one.example.com/2026/08/01/investigation.html",
        "Investigation reveals procurement failures",
        source_id="one",
    )
    good_two = snapshot(
        "https://two.example.com/2026/08/01/feature.html",
        "A reported feature on climate adaptation",
        source_id="two",
    )
    buying_guide = snapshot(
        "https://www.wired.com/gallery/best-organic-mattresses/",
        "Best Organic Mattresses (2026)",
        description="We tested products and may earn a commission.",
        source_id="wired",
    )
    old_article = snapshot(
        "https://old.example.com/2019/03/04/commentary.html",
        "An old commentary on economic reform",
        published_at="2019-03-04",
        source_id="old",
    )
    snapshots = [good_one, buying_guide, old_article, good_two]
    truth_rows = [
        truth(good_one["url"], good_one["title"], "formal_candidate"),
        truth(good_two["url"], good_two["title"], "formal_candidate"),
        truth(
            buying_guide["url"],
            buying_guide["title"],
            "reject",
            serious=True,
        ),
        truth(old_article["url"], old_article["title"], "reject", serious=True),
    ]

    metrics, evidence = replay_run(
        run_id=RUN_ID,
        snapshot_rows=snapshots,
        truth_rows=truth_rows,
        max_urls=2,
    )

    assert metrics.discovered_rows == 4
    assert metrics.labelled_rows == 4
    assert metrics.selected_count == 2, evidence
    assert metrics.selected_true_candidates == 2
    assert metrics.selection_precision == 1.0
    assert metrics.selection_recall == 1.0
    assert metrics.severe_false_accepts == 0
    assert metrics.pre_extraction_rejects == 2
    assert metrics.pre_extraction_reject_precision == 1.0
    assert metrics.positive_false_rejects == 0
    assert {row["reason"] for row in evidence["gate_rejections"]} == {
        "commerce_or_buying_guide",
        "stale_article_over_14d",
    }


def test_replay_counts_high_confidence_missed_candidate() -> None:
    first = snapshot(
        "https://one.example.com/2026/08/01/feature.html",
        "A strong reported feature",
        source_id="one",
    )
    second = snapshot(
        "https://two.example.com/2026/08/01/investigation.html",
        "An important investigation",
        source_id="two",
    )
    truth_rows = [
        truth(first["url"], first["title"], "formal_candidate"),
        truth(
            second["url"],
            second["title"],
            "formal_candidate",
            should_enter=True,
            regret=True,
        ),
    ]
    metrics, evidence = replay_run(
        run_id=RUN_ID,
        snapshot_rows=[first, second],
        truth_rows=truth_rows,
        max_urls=1,
    )
    assert metrics.selected_count == 1, evidence
    assert metrics.truth_candidates == 2
    assert metrics.selection_recall == 0.5
    assert metrics.high_confidence_selection_regret == 1
    assert len(evidence["missed_high_confidence"]) == 1


def test_aggregate_uses_exact_selected_denominators() -> None:
    first_metrics, _ = replay_run(
        run_id=RUN_ID,
        snapshot_rows=[
            snapshot(
                "https://one.example.com/2026/08/01/feature.html",
                "A strong reported feature",
            )
        ],
        truth_rows=[
            truth(
                "https://one.example.com/2026/08/01/feature.html",
                "A strong reported feature",
                "formal_candidate",
            )
        ],
        max_urls=1,
    )
    aggregate = aggregate_metrics([first_metrics])
    assert aggregate.run_count == 1
    assert aggregate.selection_precision == 1.0
    assert aggregate.selection_recall == 1.0
