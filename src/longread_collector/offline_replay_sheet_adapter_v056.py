"""Adapt the persisted Stage 3 Sheet schema to the v0.5.6 replay contract.

The human-review table deliberately stores article IDs for extracted items and
snapshot row numbers for capacity/prefilter items.  This adapter resolves both
without rewriting historical data or loading cached article bodies.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import offline_replay_v056 as replay
from .sheets import GoogleSheetStore

TRUTH_STATUS_PREFIX = "v055_stage3"
TRUTH_STATUS_SUFFIX = "ground_truth"
_ORIGINAL_REPLAY_RUN = replay.replay_run


def _records(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        return []
    headers = [str(value or "").strip() for value in values[0]]
    return [
        {
            header: (row[index] if index < len(row) else "")
            for index, header in enumerate(headers)
            if header
        }
        for row in values[1:]
        if any(str(value or "").strip() for value in row)
    ]


def _truth_status(value: Any) -> bool:
    status = str(value or "").strip()
    return status.startswith(TRUTH_STATUS_PREFIX) and status.endswith(
        TRUTH_STATUS_SUFFIX
    )


def normalize_sheet_rows(
    *,
    snapshot_values: list[list[Any]],
    review_values: list[list[Any]],
    run_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not snapshot_values:
        return [], []
    snapshot_headers = [str(value or "").strip() for value in snapshot_values[0]]
    review_records = _records(review_values)

    normalized_snapshots: list[dict[str, Any]] = []
    snapshot_by_article: dict[str, dict[str, Any]] = {}
    snapshot_by_sheet_row: dict[int, dict[str, Any]] = {}

    # Preserve physical row numbers even if a future Sheet contains blank rows.
    for sheet_row, values in enumerate(snapshot_values[1:], start=2):
        if not any(str(value or "").strip() for value in values):
            continue
        row = {
            header: (values[index] if index < len(values) else "")
            for index, header in enumerate(snapshot_headers)
            if header
        }
        collector_run_id = str(row.get("collector_run_id", "")).strip()
        normalized = dict(row)
        normalized["run_id"] = collector_run_id
        normalized["query_id"] = str(row.get("query_or_source", "") or "")
        normalized["rank_score"] = row.get("discovered_rank", 0)
        normalized["selection_group"] = (
            "native" if str(row.get("source_id", "")).strip() else "open"
        )
        snapshot_by_sheet_row[sheet_row] = normalized
        article_id = str(row.get("article_id", "")).strip()
        if article_id:
            snapshot_by_article[article_id] = normalized
        if collector_run_id in run_ids:
            normalized_snapshots.append(normalized)

    normalized_truth: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for row in review_records:
        collector_run_id = str(row.get("collector_run_id", "")).strip()
        if collector_run_id not in run_ids or not _truth_status(
            row.get("review_status")
        ):
            continue

        article_id = str(row.get("article_id", "")).strip()
        snapshot = snapshot_by_article.get(article_id) if article_id else None
        if snapshot is None:
            try:
                sheet_row = int(str(row.get("cache_row", "")).strip())
            except (TypeError, ValueError):
                sheet_row = 0
            snapshot = snapshot_by_sheet_row.get(sheet_row)

        if snapshot is None:
            unresolved.append(
                {
                    "collector_run_id": collector_run_id,
                    "article_id": article_id,
                    "cache_row": str(row.get("cache_row", "")),
                    "title": str(row.get("title", "")),
                }
            )
            continue

        normalized_truth.append(
            {
                **row,
                "run_id": collector_run_id,
                "url": snapshot.get("url", ""),
                "url_canonical": snapshot.get("url_canonical", ""),
                "expected_candidate_disposition": row.get(
                    "expected_disposition", ""
                ),
                "review_confidence": row.get("confidence", ""),
                "audit_status": row.get("review_status", ""),
                "review_reason": row.get("one_sentence_reason", ""),
            }
        )

    if unresolved:
        sample = unresolved[:5]
        raise RuntimeError(
            f"Could not resolve {len(unresolved)} Stage 3 truth rows to discovery "
            f"snapshots; sample={sample}"
        )
    return normalized_snapshots, normalized_truth


def load_replay_rows(
    store: GoogleSheetStore,
    *,
    run_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    snapshot_values = store.book.worksheet("collector_discovery_snapshot").get(
        "A:Z"
    )
    review_values = store.book.worksheet("collector_shadow_review_items").get(
        "A:X"
    )
    return normalize_sheet_rows(
        snapshot_values=snapshot_values,
        review_values=review_values,
        run_ids=run_ids,
    )


def replay_run_with_capacity_metric(*args: Any, **kwargs: Any):
    metrics, evidence = _ORIGINAL_REPLAY_RUN(*args, **kwargs)
    unselected_survivors = max(
        0,
        metrics.discovered_rows
        - metrics.pre_extraction_rejects
        - metrics.selected_count,
    )
    evidence["capacity_not_selected_count"] = unselected_survivors
    return replace(metrics, capacity_not_selected=unselected_survivors), evidence


def main() -> None:
    replay.load_replay_rows = load_replay_rows
    replay.replay_run = replay_run_with_capacity_metric
    replay.main()


if __name__ == "__main__":
    main()
