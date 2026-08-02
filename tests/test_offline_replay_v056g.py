from __future__ import annotations

import json

from longread_collector.offline_replay_v056g import replay_run_with_stage

RUN_ID = "COL-20260801-190655-BJT-zh_evening"


def snapshot(
    url: str,
    title: str,
    *,
    published_at: str = "2026-08-01",
    description: str = "A complete reported article.",
    source_id: str = "source-a",
    discovery_method: str = "rss",
) -> dict:
    return {
        "run_id": RUN_ID,
        "url": url,
        "url_canonical": url,
        "title": title,
        "description": description,
        "published_at": published_at,
        "query_id": f"source:{source_id}",
        "source_id": source_id,
        "source_name": source_id,
        "discovery_method": discovery_method,
        "rank_score": 1,
        "selection_group": "native",
        "metadata_json": json.dumps(
            {
                "purpose": "native_source_scan",
                "source_id": source_id,
                "native_method": discovery_method,
            }
        ),
    }


def truth(url: str, title: str, disposition: str, *, regret: bool = False) -> dict:
    return {
        "run_id": RUN_ID,
        "url": url,
        "url_canonical": url,
        "title": title,
        "expected_candidate_disposition": disposition,
        "serious_false_accept": "FALSE",
        "should_enter_top32": str(regret).upper(),
        "selection_regret": str(regret).upper(),
        "review_confidence": "high",
        "audit_status": "v055_stage3_ground_truth",
        "review_reason": "synthetic truth",
    }


def test_staged_replay_promotes_high_value_evidence_reserve() -> None:
    selected_good = snapshot(
        "https://good.example.com/2026/08/01/feature.html",
        "A reported feature on public health",
        source_id="good",
    )
    selected_weak = snapshot(
        "https://weak.example.com/2026/08/01/update.html",
        "Daily company appointment update",
        description="A short routine update.",
        source_id="weak",
    )
    reserve_good = snapshot(
        "https://fallback.example.com/investigation-hidden-pollution.html",
        "Investigation reveals hidden pollution in drinking water",
        published_at="",
        description="Documents, interviews and laboratory evidence reveal the failures.",
        source_id="fallback",
        discovery_method="firecrawl_search",
    )
    snapshots = [selected_good, selected_weak, reserve_good]
    truth_rows = [
        truth(selected_good["url"], selected_good["title"], "formal_candidate"),
        truth(selected_weak["url"], selected_weak["title"], "reject"),
        truth(
            reserve_good["url"],
            reserve_good["title"],
            "formal_candidate",
            regret=True,
        ),
    ]

    initial, staged, evidence = replay_run_with_stage(
        run_id=RUN_ID,
        snapshot_rows=snapshots,
        truth_rows=truth_rows,
        max_urls=2,
    )

    assert initial.severe_false_accepts == 0
    assert staged["attempt_count"] == 2
    assert staged["attempted_true_candidates"] == 2
    assert staged["precision"] == 1.0
    assert staged["recall"] == 1.0
    assert staged["high_confidence_selection_regret"] == 0
    promoted_urls = {
        row["url"] for row in evidence["staged"]["reserve_promotions"]
    }
    assert reserve_good["url"] in promoted_urls


def test_staged_replay_never_borrows_more_than_eight_late_slots() -> None:
    snapshots = [
        snapshot(
            f"https://source{index}.example.com/2026/08/01/feature-{index}.html",
            f"Investigation feature {index}",
            source_id=f"source{index}",
        )
        for index in range(12)
    ]
    truth_rows = [
        truth(row["url"], row["title"], "formal_candidate") for row in snapshots
    ]

    _, staged, _ = replay_run_with_stage(
        run_id=RUN_ID,
        snapshot_rows=snapshots,
        truth_rows=truth_rows,
        max_urls=32,
    )

    assert staged["first_stage_count"] == 12
    assert staged["second_stage_count"] == 0
    assert staged["attempt_count"] == 12
    assert staged["second_stage_count"] <= 8
