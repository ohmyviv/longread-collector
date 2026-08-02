"""Read-only v0.5.6 selection replay against immutable snapshots and human truth.

This evaluator intentionally replays only the layers supported by persisted data:

- pre-extraction page gates;
- publication evidence and freshness policy;
- native/open reserve ranking and the initial Top 32 selection.

The historical Sheet does not persist full article bodies. Therefore this module
never claims to re-run post-extraction classification or the 24+8 replacement
stage for candidates that were not originally extracted. Those layers remain
covered by deterministic regression fixtures and subsequent live shadow runs.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .config import get_settings
from .freshness_policy_v056 import evaluate_freshness_policy
from .models import DiscoveredURL
from .normalization import canonicalize_url
from .page_gate_policy_v056 import evaluate_page_gate_policy
from .ranked_freshness_v056 import install_ranked_freshness
from .ranked_selection_plan_v056 import filter_discovered as select_ranked_candidates
from .sheets import GoogleSheetStore

REPLAY_VERSION = "offline-selection-replay-v0.5.6"
BJ = ZoneInfo("Asia/Shanghai")
POSITIVE_DISPOSITIONS = {
    "formal_candidate",
    "special_candidate",
    "original_source_required",
}
_RUN_RE = re.compile(r"^COL-(\d{8})-(\d{6})-BJT-")


@dataclass(frozen=True, slots=True)
class RunReplayMetrics:
    run_id: str
    discovered_rows: int
    labelled_rows: int
    selected_count: int
    selected_labelled: int
    selected_true_candidates: int
    selected_false_accepts: int
    selected_unlabelled: int
    truth_candidates: int
    selection_precision: float
    selection_recall: float
    severe_false_accepts: int
    high_confidence_selection_regret: int
    pre_extraction_rejects: int
    pre_extraction_reject_precision: float
    positive_false_rejects: int
    page_gate_rejects: int
    freshness_gate_rejects: int
    capacity_not_selected: int


@dataclass(frozen=True, slots=True)
class AggregateReplayMetrics:
    run_count: int
    discovered_rows: int
    labelled_rows: int
    selected_count: int
    selected_labelled: int
    selected_true_candidates: int
    selected_false_accepts: int
    selected_unlabelled: int
    truth_candidates: int
    selection_precision: float
    selection_recall: float
    severe_false_accepts: int
    high_confidence_selection_regret: int
    pre_extraction_rejects: int
    pre_extraction_reject_precision: float
    positive_false_rejects: int
    page_gate_rejects: int
    freshness_gate_rejects: int
    capacity_not_selected: int


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().upper() in {"TRUE", "1", "YES", "Y"}


def _canonical(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return canonicalize_url(text)
    except Exception:
        return text


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _run_datetime(run_id: str) -> datetime:
    match = _RUN_RE.match(run_id)
    if not match:
        raise ValueError(f"Unsupported collector run id: {run_id}")
    return datetime.strptime(
        f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S"
    ).replace(tzinfo=BJ)


def _snapshot_item(row: dict[str, Any]) -> DiscoveredURL:
    metadata = _json_dict(row.get("metadata_json"))
    # Remove historical decision output while retaining source/query provenance.
    for key in ("selection", "freshness", "page_gate"):
        metadata.pop(key, None)
    source_id = str(row.get("source_id", "") or "").strip()
    source_name = str(row.get("source_name", "") or "").strip()
    query_id = str(row.get("query_id", "") or "").strip()
    if source_id:
        metadata.setdefault("source_id", source_id)
    if source_name:
        metadata.setdefault("source_name", source_name)
    if query_id:
        metadata.setdefault("query_id", query_id)
    selection_group = str(row.get("selection_group", "") or "").strip()
    if selection_group == "native" or source_id:
        metadata.setdefault("purpose", "native_source_scan")
    try:
        rank_score = float(row.get("rank_score") or 0)
    except (TypeError, ValueError):
        rank_score = 0.0
    return DiscoveredURL(
        url=str(row.get("url_canonical") or row.get("url") or ""),
        title=str(row.get("title") or ""),
        description=str(row.get("description") or ""),
        published_at=str(row.get("published_at") or ""),
        query_id=query_id,
        discovery_method=str(row.get("discovery_method") or ""),
        rank_score=rank_score,
        metadata=metadata,
    )


def _truth_key(row: dict[str, Any]) -> str:
    return _canonical(row.get("url_canonical") or row.get("url"))


def _truth_positive(row: dict[str, Any]) -> bool:
    return str(row.get("expected_candidate_disposition", "")).strip() in POSITIVE_DISPOSITIONS


def _truth_regret(row: dict[str, Any]) -> bool:
    high_confidence = str(row.get("review_confidence", "")).strip().lower() == "high"
    return high_confidence and (
        _as_bool(row.get("should_enter_top32"))
        or _as_bool(row.get("selection_regret"))
    )


def replay_run(
    *,
    run_id: str,
    snapshot_rows: list[dict[str, Any]],
    truth_rows: list[dict[str, Any]],
    max_urls: int = 32,
) -> tuple[RunReplayMetrics, dict[str, Any]]:
    run_snapshots = [row for row in snapshot_rows if str(row.get("run_id")) == run_id]
    run_truth = [row for row in truth_rows if str(row.get("run_id")) == run_id]
    truth_by_url = {
        key: row for row in run_truth if (key := _truth_key(row))
    }
    run_now = _run_datetime(run_id)

    candidates: list[DiscoveredURL] = []
    gate_rejections: list[dict[str, str]] = []
    for row in run_snapshots:
        item = _snapshot_item(row)
        page = evaluate_page_gate_policy(item)
        if page.rejected:
            gate_rejections.append(
                {"url": item.url, "reason": page.reject_reason, "gate": "page"}
            )
            continue
        freshness = evaluate_freshness_policy(
            item,
            phase="prefilter",
            now=run_now,
        )
        if not freshness.allowed:
            gate_rejections.append(
                {"url": item.url, "reason": freshness.reject_reason, "gate": "freshness"}
            )
            continue
        candidates.append(item)

    install_ranked_freshness()
    selected, ranked_rejected = select_ranked_candidates(
        candidates,
        max_urls=max_urls,
        max_per_domain=2,
    )
    selected_urls = {_canonical(item.url) for item in selected}
    gate_rejected_urls = {_canonical(item["url"]) for item in gate_rejections}

    selected_truth = [truth_by_url[url] for url in selected_urls if url in truth_by_url]
    selected_true = sum(_truth_positive(row) for row in selected_truth)
    selected_false = sum(not _truth_positive(row) for row in selected_truth)
    severe_false = sum(
        (not _truth_positive(row)) and _as_bool(row.get("serious_false_accept"))
        for row in selected_truth
    )
    truth_candidates = sum(_truth_positive(row) for row in run_truth)
    high_regret = sum(
        _truth_regret(row) and _truth_key(row) not in selected_urls
        for row in run_truth
    )

    gated_truth = [truth_by_url[url] for url in gate_rejected_urls if url in truth_by_url]
    gated_true_rejects = sum(not _truth_positive(row) for row in gated_truth)
    positive_false_rejects = sum(_truth_positive(row) for row in gated_truth)
    page_gate_rejects = sum(row["gate"] == "page" for row in gate_rejections)
    freshness_gate_rejects = sum(row["gate"] == "freshness" for row in gate_rejections)

    metrics = RunReplayMetrics(
        run_id=run_id,
        discovered_rows=len(run_snapshots),
        labelled_rows=len(run_truth),
        selected_count=len(selected),
        selected_labelled=len(selected_truth),
        selected_true_candidates=selected_true,
        selected_false_accepts=selected_false,
        selected_unlabelled=len(selected) - len(selected_truth),
        truth_candidates=truth_candidates,
        selection_precision=_ratio(selected_true, len(selected_truth)),
        selection_recall=_ratio(selected_true, truth_candidates),
        severe_false_accepts=severe_false,
        high_confidence_selection_regret=high_regret,
        pre_extraction_rejects=len(gate_rejections),
        pre_extraction_reject_precision=_ratio(gated_true_rejects, len(gated_truth)),
        positive_false_rejects=positive_false_rejects,
        page_gate_rejects=page_gate_rejects,
        freshness_gate_rejects=freshness_gate_rejects,
        capacity_not_selected=len(ranked_rejected),
    )
    evidence = {
        "selected": [
            {
                "url": item.url,
                "title": item.title,
                "truth_disposition": str(
                    truth_by_url.get(_canonical(item.url), {}).get(
                        "expected_candidate_disposition", "unlabelled"
                    )
                ),
                "selection": item.metadata.get("selection", {}),
                "freshness": item.metadata.get("freshness", {}),
                "page_gate": item.metadata.get("page_gate", {}),
            }
            for item in selected
        ],
        "gate_rejections": [
            {
                **row,
                "truth_disposition": str(
                    truth_by_url.get(_canonical(row["url"]), {}).get(
                        "expected_candidate_disposition", "unlabelled"
                    )
                ),
            }
            for row in gate_rejections
        ],
        "capacity_rejections": ranked_rejected,
        "missed_high_confidence": [
            {
                "url": _truth_key(row),
                "title": row.get("title", ""),
                "expected_disposition": row.get("expected_candidate_disposition", ""),
                "review_reason": row.get("review_reason", ""),
            }
            for row in run_truth
            if _truth_regret(row) and _truth_key(row) not in selected_urls
        ],
    }
    return metrics, evidence


def aggregate_metrics(metrics: Iterable[RunReplayMetrics]) -> AggregateReplayMetrics:
    rows = list(metrics)
    totals = {
        field: sum(int(getattr(row, field)) for row in rows)
        for field in (
            "discovered_rows",
            "labelled_rows",
            "selected_count",
            "selected_labelled",
            "selected_true_candidates",
            "selected_false_accepts",
            "selected_unlabelled",
            "truth_candidates",
            "severe_false_accepts",
            "high_confidence_selection_regret",
            "pre_extraction_rejects",
            "positive_false_rejects",
            "page_gate_rejects",
            "freshness_gate_rejects",
            "capacity_not_selected",
        )
    }
    gated_labelled = 0
    gated_true_rejects = 0
    # Recover denominator and numerator from rounded per-run metrics only when
    # exact values are unavailable would be unsafe. The CLI aggregates exact
    # evidence separately and overwrites this pair below.
    for row in rows:
        if row.pre_extraction_rejects:
            gated_labelled += row.pre_extraction_rejects
            gated_true_rejects += round(
                row.pre_extraction_reject_precision * row.pre_extraction_rejects
            )
    return AggregateReplayMetrics(
        run_count=len(rows),
        **totals,
        selection_precision=_ratio(
            totals["selected_true_candidates"], totals["selected_labelled"]
        ),
        selection_recall=_ratio(
            totals["selected_true_candidates"], totals["truth_candidates"]
        ),
        pre_extraction_reject_precision=_ratio(gated_true_rejects, gated_labelled),
    )


def load_replay_rows(
    store: GoogleSheetStore,
    *,
    run_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    snapshots = store.book.worksheet("collector_discovery_snapshot").get_all_records()
    truth = store.book.worksheet("collector_shadow_review_items").get_all_records()
    snapshot_rows = [row for row in snapshots if str(row.get("run_id")) in run_ids]
    truth_rows = [
        row
        for row in truth
        if str(row.get("run_id")) in run_ids
        and str(row.get("audit_status", "")) == "v055_stage3_ground_truth"
    ]
    return snapshot_rows, truth_rows


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
    per_run: list[RunReplayMetrics] = []
    evidence: dict[str, Any] = {}
    for run_id in run_ids:
        metrics, run_evidence = replay_run(
            run_id=run_id,
            snapshot_rows=snapshot_rows,
            truth_rows=truth_rows,
            max_urls=max_urls,
        )
        per_run.append(metrics)
        evidence[run_id] = run_evidence
    aggregate = aggregate_metrics(per_run)
    return {
        "replay_version": REPLAY_VERSION,
        "generated_at_bj": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "scope": {
            "run_ids": run_ids,
            "max_urls": max_urls,
            "classification_replayed": False,
            "post_extraction_replacement_replayed": False,
            "limitations": [
                "Historical Sheets do not persist full article bodies.",
                "Metrics cover pre-extraction gates and initial Top 32 selection only.",
                "Classification is validated by fixtures and future live shadow runs.",
                "24+8 replacement requires live extraction outcomes for newly selected URLs.",
            ],
        },
        "aggregate": asdict(aggregate),
        "per_run": [asdict(row) for row in per_run],
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay v0.5.6 selection on labelled snapshots")
    parser.add_argument("--run-id", action="append", dest="run_ids", required=True)
    parser.add_argument("--max-urls", type=int, default=32)
    parser.add_argument("--expected-truth-count", type=int)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    settings = get_settings()
    store = GoogleSheetStore(settings)
    result = run_replay(
        store,
        run_ids=args.run_ids,
        max_urls=args.max_urls,
        expected_truth_count=args.expected_truth_count,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps({"aggregate": result["aggregate"], "per_run": result["per_run"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
