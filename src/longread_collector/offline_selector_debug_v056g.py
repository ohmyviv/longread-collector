"""Materialize labelled candidate ranking and reserve diagnostics for v0.5.6g."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from . import offline_replay_v056 as base
from .config import get_settings
from .models import DiscoveredURL
from .offline_replay_sheet_adapter_v056 import load_replay_rows
from .offline_replay_v056g import _prepare_candidates, _successful_stub
from .ranked_freshness_v056 import install_ranked_freshness
from .ranked_selection_plan_v056 import filter_discovered
from .selection_plan_v056 import clear_selection_plan, current_selection_plan
from .sheets import GoogleSheetStore
from .staged_reserve_v056 import build_second_stage, split_first_stage

DEBUG_VERSION = "offline-selector-debug-v0.5.6g"


def _record(
    item: DiscoveredURL,
    *,
    truth_by_url: dict[str, dict[str, Any]],
    attempted_urls: set[str],
) -> dict[str, Any]:
    canonical = base._canonical(item.url)
    truth = truth_by_url.get(canonical, {})
    selection = item.metadata.get("selection", {})
    components = selection.get("score_components", {})
    return {
        "url": item.url,
        "title": item.title,
        "source_id": item.metadata.get("source_id", ""),
        "discovery_method": item.discovery_method,
        "published_at": item.published_at,
        "truth_disposition": truth.get(
            "expected_candidate_disposition", "unlabelled"
        ),
        "truth_positive": base._truth_positive(truth) if truth else None,
        "high_confidence_regret_target": base._truth_regret(truth) if truth else False,
        "attempted_in_staged_simulation": canonical in attempted_urls,
        "selection_status": selection.get("selection_status", ""),
        "selection_phase": selection.get("selection_phase", ""),
        "selection_bucket": selection.get("selection_bucket", ""),
        "selection_group": selection.get("selection_group", ""),
        "source_or_domain_rank": selection.get("source_or_domain_rank", ""),
        "selected_order": selection.get("selected_order", ""),
        "reserve_reason": selection.get("reserve_reason", ""),
        "reserve_only_reason": selection.get("reserve_only_reason", ""),
        "editorial_priority": components.get("editorial_priority", 0),
        "quality": components.get("quality", 0),
        "freshness_ordinal": components.get("freshness_ordinal", 0),
        "article_confidence": components.get("article_confidence", 0),
        "reporting_signal": components.get("reporting_signal", 0),
        "policy_report_signal": components.get("policy_report_signal", 0),
        "native_signal": components.get("native_signal", 0),
        "penalties": {
            key: value
            for key, value in components.items()
            if key.endswith("_penalty") and value
        },
        "second_stage_eligible": selection.get("second_stage_eligible"),
        "second_stage_priority_delta": selection.get(
            "second_stage_priority_delta"
        ),
        "late_stage_skip_reason": selection.get("late_stage_skip_reason", ""),
        "freshness": item.metadata.get("freshness", {}),
    }


def run_debug(
    store: GoogleSheetStore,
    *,
    run_ids: list[str],
    max_urls: int,
) -> dict[str, Any]:
    snapshots, truth_rows = load_replay_rows(store, run_ids=set(run_ids))
    result: dict[str, Any] = {}
    for run_id in run_ids:
        candidates, _ = _prepare_candidates(run_id=run_id, snapshot_rows=snapshots)
        clear_selection_plan()
        install_ranked_freshness()
        selected, _ = filter_discovered(
            candidates,
            max_urls=max_urls,
            max_per_domain=2,
        )
        plan = current_selection_plan()
        if plan is None:
            raise RuntimeError("selection plan missing")
        first, deferred = split_first_stage(selected, max_attempts=max_urls)
        decision = build_second_stage(
            plan=plan,
            first_stage=first,
            deferred=deferred,
            first_articles=[
                _successful_stub(item, index)
                for index, item in enumerate(first, start=1)
            ],
            max_attempts=max_urls,
        )
        attempted_urls = {
            base._canonical(item.url)
            for item in decision.first_stage + decision.second_stage
        }
        run_truth = [row for row in truth_rows if str(row.get("run_id")) == run_id]
        truth_by_url = {
            key: row for row in run_truth if (key := base._truth_key(row))
        }
        records = [
            _record(
                item,
                truth_by_url=truth_by_url,
                attempted_urls=attempted_urls,
            )
            for item in candidates
        ]
        records.sort(
            key=lambda row: (
                int(row.get("editorial_priority") or 0),
                int(row.get("quality") or 0),
                int(row.get("freshness_ordinal") or 0),
            ),
            reverse=True,
        )
        result[run_id] = {
            "candidate_count": len(records),
            "selected_count": len(selected),
            "first_stage_count": len(first),
            "second_stage_count": len(decision.second_stage),
            "attempted_count": len(attempted_urls),
            "candidates": records,
        }
    return {
        "debug_version": DEBUG_VERSION,
        "generated_at_bj": datetime.now(base.BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "runs": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug v0.5.6g labelled selection")
    parser.add_argument("--run-id", action="append", dest="run_ids", required=True)
    parser.add_argument("--max-urls", type=int, default=32)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    result = run_debug(
        GoogleSheetStore(get_settings()),
        run_ids=args.run_ids,
        max_urls=args.max_urls,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
