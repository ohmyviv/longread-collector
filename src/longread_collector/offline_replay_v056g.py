"""Replay v0.5.6g initial selection and bounded 24+8 reserve scheduling.

Historical snapshots do not persist article bodies for every discovered URL, so
this evaluator does not claim to replay extraction or classification.  It does,
however, have enough persisted metadata to replay the exact pre-extraction
gates, initial portfolio, reserve plan and stage-two scheduling order.

The staged simulation uses a conservative all-first-stage-usable assumption.
Real extraction/classification failures can only create additional same-group
replacement opportunities; they are not invented here.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from . import offline_replay_v056 as base
from .config import get_settings
from .freshness_policy_v056f import evaluate_freshness_policy
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url
from .offline_replay_sheet_adapter_v056 import load_replay_rows
from .page_gate_policy_v056 import evaluate_page_gate_policy
from .ranked_freshness_v056 import install_ranked_freshness
from .ranked_selection_plan_v056 import filter_discovered as select_ranked_candidates
from .selection_plan_v056 import clear_selection_plan, current_selection_plan
from .sheets import GoogleSheetStore
from .staged_reserve_v056 import build_second_stage, split_first_stage

REPLAY_VERSION = "offline-selection-reserve-replay-v0.5.6g"


def _truth_metrics(
    *,
    attempted: list[DiscoveredURL],
    truth_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    truth_by_url = {
        key: row for row in truth_rows if (key := base._truth_key(row))
    }
    attempted_urls = {base._canonical(item.url) for item in attempted}
    labelled = [truth_by_url[url] for url in attempted_urls if url in truth_by_url]
    true_candidates = sum(base._truth_positive(row) for row in labelled)
    false_accepts = sum(not base._truth_positive(row) for row in labelled)
    truth_candidates = sum(base._truth_positive(row) for row in truth_rows)
    severe_false_accepts = sum(
        (not base._truth_positive(row))
        and base._as_bool(row.get("serious_false_accept"))
        for row in labelled
    )
    high_regret = sum(
        base._truth_regret(row) and base._truth_key(row) not in attempted_urls
        for row in truth_rows
    )
    return {
        "attempt_count": len(attempted),
        "attempted_labelled": len(labelled),
        "attempted_true_candidates": true_candidates,
        "attempted_false_accepts": false_accepts,
        "attempted_unlabelled": len(attempted) - len(labelled),
        "truth_candidates": truth_candidates,
        "precision": base._ratio(true_candidates, len(labelled)),
        "recall": base._ratio(true_candidates, truth_candidates),
        "severe_false_accepts": severe_false_accepts,
        "high_confidence_selection_regret": high_regret,
    }


def _successful_stub(item: DiscoveredURL, index: int) -> ExtractedArticle:
    canonical = canonicalize_url(item.url)
    return ExtractedArticle(
        article_id=f"offline-stage-{index}",
        url=item.url,
        url_canonical=canonical,
        domain=domain_from_url(canonical),
        title=item.title,
        extraction_status="success",
        extractor_used="offline_stage_assumption",
        candidate_disposition="formal_candidate",
        eligible_for_editor=True,
        classification_version="offline-stage-all-first-usable",
    )


def _prepare_candidates(
    *,
    run_id: str,
    snapshot_rows: list[dict[str, Any]],
) -> tuple[list[DiscoveredURL], int]:
    run_now = base._run_datetime(run_id)
    candidates: list[DiscoveredURL] = []
    gate_rejections = 0
    for row in snapshot_rows:
        if str(row.get("run_id")) != run_id:
            continue
        item = base._snapshot_item(row)
        page = evaluate_page_gate_policy(item)
        if page.rejected:
            gate_rejections += 1
            continue
        freshness = evaluate_freshness_policy(
            item,
            phase="prefilter",
            now=run_now,
        )
        if not freshness.allowed:
            gate_rejections += 1
            continue
        candidates.append(item)
    return candidates, gate_rejections


def replay_run_with_stage(
    *,
    run_id: str,
    snapshot_rows: list[dict[str, Any]],
    truth_rows: list[dict[str, Any]],
    max_urls: int = 32,
) -> tuple[base.RunReplayMetrics, dict[str, Any], dict[str, Any]]:
    # Keep the legacy initial-selection metric contract for longitudinal
    # comparison, but bind it to the active v0.5.6f freshness policy.
    base.evaluate_freshness_policy = evaluate_freshness_policy
    initial_metrics, initial_evidence = base.replay_run(
        run_id=run_id,
        snapshot_rows=snapshot_rows,
        truth_rows=truth_rows,
        max_urls=max_urls,
    )
    initial_metrics = replace(
        initial_metrics,
        capacity_not_selected=max(
            0,
            initial_metrics.discovered_rows
            - initial_metrics.pre_extraction_rejects
            - initial_metrics.selected_count,
        ),
    )

    candidates, _ = _prepare_candidates(run_id=run_id, snapshot_rows=snapshot_rows)
    clear_selection_plan()
    install_ranked_freshness()
    selected, _ = select_ranked_candidates(
        candidates,
        max_urls=max_urls,
        max_per_domain=2,
    )
    plan = current_selection_plan()
    if plan is None:
        raise RuntimeError("v0.5.6g selection did not publish a reserve plan")

    first_stage, deferred = split_first_stage(
        selected,
        max_attempts=max_urls,
    )
    first_articles = [
        _successful_stub(item, index)
        for index, item in enumerate(first_stage, start=1)
    ]
    decision = build_second_stage(
        plan=plan,
        first_stage=first_stage,
        deferred=deferred,
        first_articles=first_articles,
        max_attempts=max_urls,
    )
    attempted = decision.first_stage + decision.second_stage
    run_truth = [row for row in truth_rows if str(row.get("run_id")) == run_id]
    staged_metrics = {
        **_truth_metrics(attempted=attempted, truth_rows=run_truth),
        "first_stage_count": len(decision.first_stage),
        "second_stage_count": len(decision.second_stage),
        "reserve_promotions": len(decision.promoted_reserves),
        "deferred_displacements": len(decision.deferred_not_extracted),
        "failed_first_stage_assumed": 0,
        "simulation_assumption": "all_first_stage_items_usable",
    }
    truth_by_url = {
        key: row for row in run_truth if (key := base._truth_key(row))
    }

    staged_evidence = {
        "attempted": [
            {
                "url": item.url,
                "title": item.title,
                "truth_disposition": str(
                    truth_by_url.get(base._canonical(item.url), {}).get(
                        "expected_candidate_disposition", "unlabelled"
                    )
                ),
                "selection": item.metadata.get("selection", {}),
            }
            for item in attempted
        ],
        "reserve_promotions": [
            {
                "url": item.url,
                "title": item.title,
                "truth_disposition": str(
                    truth_by_url.get(base._canonical(item.url), {}).get(
                        "expected_candidate_disposition", "unlabelled"
                    )
                ),
                "selection": item.metadata.get("selection", {}),
            }
            for item in decision.promoted_reserves
        ],
        "deferred_not_extracted": [
            {
                "url": item.url,
                "title": item.title,
                "truth_disposition": str(
                    truth_by_url.get(base._canonical(item.url), {}).get(
                        "expected_candidate_disposition", "unlabelled"
                    )
                ),
                "selection": item.metadata.get("selection", {}),
            }
            for item in decision.deferred_not_extracted
        ],
        "missed_high_confidence": [
            {
                "url": base._truth_key(row),
                "title": row.get("title", ""),
                "expected_disposition": row.get(
                    "expected_candidate_disposition", ""
                ),
                "review_reason": row.get("review_reason", ""),
            }
            for row in run_truth
            if base._truth_regret(row)
            and base._truth_key(row)
            not in {base._canonical(item.url) for item in attempted}
        ],
    }
    return initial_metrics, staged_metrics, {
        "initial": initial_evidence,
        "staged": staged_evidence,
    }


def _aggregate_staged(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sums = {
        key: sum(int(row[key]) for row in rows)
        for key in (
            "attempt_count",
            "attempted_labelled",
            "attempted_true_candidates",
            "attempted_false_accepts",
            "attempted_unlabelled",
            "truth_candidates",
            "severe_false_accepts",
            "high_confidence_selection_regret",
            "first_stage_count",
            "second_stage_count",
            "reserve_promotions",
            "deferred_displacements",
        )
    }
    return {
        "run_count": len(rows),
        **sums,
        "precision": base._ratio(
            sums["attempted_true_candidates"], sums["attempted_labelled"]
        ),
        "recall": base._ratio(
            sums["attempted_true_candidates"], sums["truth_candidates"]
        ),
        "simulation_assumption": "all_first_stage_items_usable",
    }


def run_replay(
    store: GoogleSheetStore,
    *,
    run_ids: list[str],
    max_urls: int = 32,
    expected_truth_count: int | None = None,
) -> dict[str, Any]:
    snapshot_rows, truth_rows = load_replay_rows(store, run_ids=set(run_ids))
    if expected_truth_count is not None and len(truth_rows) != expected_truth_count:
        raise RuntimeError(
            f"Expected {expected_truth_count} truth rows, found {len(truth_rows)}"
        )

    initial_rows: list[base.RunReplayMetrics] = []
    staged_rows: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {}
    per_run: list[dict[str, Any]] = []
    for run_id in run_ids:
        initial, staged, run_evidence = replay_run_with_stage(
            run_id=run_id,
            snapshot_rows=snapshot_rows,
            truth_rows=truth_rows,
            max_urls=max_urls,
        )
        initial_rows.append(initial)
        staged_rows.append(staged)
        per_run.append(
            {
                "run_id": run_id,
                "initial": asdict(initial),
                "staged": staged,
            }
        )
        evidence[run_id] = run_evidence

    return {
        "replay_version": REPLAY_VERSION,
        "generated_at_bj": datetime.now(base.BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "scope": {
            "run_ids": run_ids,
            "max_attempts": max_urls,
            "first_stage_cap": max(0, max_urls - 8),
            "second_stage_cap": min(8, max_urls),
            "classification_replayed": False,
            "extraction_failures_replayed": False,
            "reserve_scheduling_replayed": True,
            "limitations": [
                "Historical Sheets do not persist full bodies for every URL.",
                "Initial metrics replay gates and portfolio selection exactly.",
                "Staged metrics conservatively assume all first-stage items are usable.",
                "Actual failures may create additional same-group reserve promotions.",
            ],
        },
        "initial_aggregate": asdict(base.aggregate_metrics(initial_rows)),
        "staged_aggregate": _aggregate_staged(staged_rows),
        "per_run": per_run,
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay v0.5.6g initial selection and bounded reserve scheduling"
    )
    parser.add_argument("--run-id", action="append", dest="run_ids", required=True)
    parser.add_argument("--max-urls", type=int, default=32)
    parser.add_argument("--expected-truth-count", type=int)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    store = GoogleSheetStore(get_settings())
    result = run_replay(
        store,
        run_ids=args.run_ids,
        max_urls=args.max_urls,
        expected_truth_count=args.expected_truth_count,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
