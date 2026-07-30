from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable

from .classification import CLASSIFICATION_VERSION, classify_candidate

GROUND_TRUTH_BATCH_ID = "LC-GT-20260729-48-v1"
NON_REJECT_DISPOSITIONS = {
    "formal_candidate",
    "special_candidate",
    "original_source_required",
}
CRITICAL_PAGE_TYPES = {
    "job_or_career",
    "login_or_auth",
    "homepage",
    "channel_or_listing",
    "spam_or_malicious",
}


@dataclass(slots=True)
class EvaluationMetrics:
    item_count: int
    overall_accuracy: float
    candidate_precision: float
    source_chase_recall: float
    critical_false_accepts: int
    wire_dedup_accuracy: float
    formal_correct: int
    special_correct: int
    source_chase_correct: int
    reject_correct: int
    metrics_gate: str


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def calculate_metrics(
    ground_truth: Iterable[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> EvaluationMetrics:
    truth_rows = list(ground_truth)
    correct = 0
    predicted_candidates = 0
    correct_candidates = 0
    source_chase_total = 0
    source_chase_correct = 0
    critical_false_accepts = 0
    per_disposition_correct = {
        "formal_candidate": 0,
        "special_candidate": 0,
        "original_source_required": 0,
        "reject": 0,
    }

    for row in truth_rows:
        article_id = str(row.get("article_id", ""))
        expected = str(row.get("disposition", ""))
        predicted = str(predictions.get(article_id, {}).get("candidate_disposition", "reject"))
        if predicted == expected:
            correct += 1
            per_disposition_correct[expected] = per_disposition_correct.get(expected, 0) + 1
        if predicted in NON_REJECT_DISPOSITIONS:
            predicted_candidates += 1
            if expected in NON_REJECT_DISPOSITIONS:
                correct_candidates += 1
        if expected == "original_source_required":
            source_chase_total += 1
            if predicted == "original_source_required":
                source_chase_correct += 1
        if (
            predicted == "formal_candidate"
            and str(row.get("page_type", "")) in CRITICAL_PAGE_TYPES
        ):
            critical_false_accepts += 1

    wire_rows = [
        row
        for row in truth_rows
        if _to_int(row.get("review_index")) in {21, 46, 48}
    ]
    predicted_clusters = {
        str(predictions.get(str(row.get("article_id", "")), {}).get("content_cluster_id", ""))
        for row in wire_rows
    }
    wire_dedup_accuracy = float(
        len(wire_rows) == 3
        and len(predicted_clusters) == 1
        and "" not in predicted_clusters
    )

    item_count = len(truth_rows)
    overall_accuracy = correct / item_count if item_count else 0.0
    candidate_precision = (
        correct_candidates / predicted_candidates if predicted_candidates else 0.0
    )
    source_chase_recall = (
        source_chase_correct / source_chase_total if source_chase_total else 0.0
    )
    metrics_ready = (
        overall_accuracy >= 0.85
        and candidate_precision >= 0.85
        and source_chase_recall >= (6 / 7)
        and critical_false_accepts == 0
        and wire_dedup_accuracy == 1.0
    )
    return EvaluationMetrics(
        item_count=item_count,
        overall_accuracy=overall_accuracy,
        candidate_precision=candidate_precision,
        source_chase_recall=source_chase_recall,
        critical_false_accepts=critical_false_accepts,
        wire_dedup_accuracy=wire_dedup_accuracy,
        formal_correct=per_disposition_correct["formal_candidate"],
        special_correct=per_disposition_correct["special_candidate"],
        source_chase_correct=source_chase_correct,
        reject_correct=per_disposition_correct["reject"],
        metrics_gate="METRICS_READY" if metrics_ready else "NOT_READY",
    )


def predictions_from_cache_rows(
    ground_truth: Iterable[dict[str, Any]],
    cache_rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    cache = {
        str(row.get("article_id", "")): row
        for row in cache_rows
        if row.get("article_id")
    }
    result: dict[str, dict[str, Any]] = {}
    for truth in ground_truth:
        article_id = str(truth.get("article_id", ""))
        cached = cache.get(article_id, {})
        classification = classify_candidate(
            url=str(cached.get("url") or truth.get("url") or ""),
            title=str(cached.get("title") or truth.get("title") or ""),
            description=str(cached.get("description") or ""),
            author=str(cached.get("author") or ""),
            markdown=str(cached.get("content_markdown") or ""),
            published_at=str(cached.get("published_at") or ""),
            verification_level=str(cached.get("verification_level") or ""),
            content_chars=_to_int(cached.get("content_chars")),
        )
        result[article_id] = {
            "candidate_disposition": classification.candidate_disposition,
            "page_type": classification.page_type,
            "content_type": classification.content_type,
            "source_action": classification.source_action,
            "duplicate_type": classification.duplicate_type,
            "content_cluster_id": classification.content_cluster_id,
            "classification_reason": classification.reason,
        }
    return result


def _update_health_metric(worksheet: object, metric: str, value: object) -> None:
    rows = worksheet.get_all_values()
    for row_number, row in enumerate(rows[1:], start=2):
        if row and str(row[0]).strip() == metric:
            worksheet.update(
                range_name=f"B{row_number}",
                values=[[value]],
                value_input_option="USER_ENTERED",
            )
            return
    raise ValueError(f"collector_health metric not found: {metric}")


def evaluate_ground_truth(store: object) -> dict[str, Any]:
    """Evaluate the fixed release fixture and persist release-gate metrics.

    This command is manual/release-only. It does not run in the scheduled
    collector workflow and never inserts fixture rows into daily candidates.
    """

    truth_ws = store.book.worksheet("collector_ground_truth")
    cache_ws = store.book.worksheet("article_cache")
    evaluation_ws = store.book.worksheet("collector_evaluations")
    health_ws = store.book.worksheet("collector_health")

    truth_rows = [
        row
        for row in truth_ws.get_all_records()
        if str(row.get("review_batch_id", "")).strip() == GROUND_TRUTH_BATCH_ID
    ]
    if len(truth_rows) != 48:
        raise ValueError(
            f"Expected 48 ground-truth rows for {GROUND_TRUTH_BATCH_ID}, got {len(truth_rows)}"
        )
    predictions = predictions_from_cache_rows(
        truth_rows,
        cache_ws.get_all_records(),
    )
    metrics = calculate_metrics(truth_rows, predictions)
    now: datetime = store._now()
    evaluation_id = f"EVAL-{now.strftime('%Y%m%d-%H%M%S')}-BJT-v04"
    evaluation_ws.append_row(
        [
            evaluation_id,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            CLASSIFICATION_VERSION,
            GROUND_TRUTH_BATCH_ID,
            metrics.item_count,
            metrics.overall_accuracy,
            metrics.candidate_precision,
            metrics.source_chase_recall,
            metrics.critical_false_accepts,
            metrics.wire_dedup_accuracy,
            metrics.formal_correct,
            metrics.special_correct,
            metrics.source_chase_correct,
            metrics.reject_correct,
            metrics.metrics_gate,
            "fixed fixture evaluation; shadow-day gate evaluated separately",
        ],
        value_input_option="USER_ENTERED",
    )
    _update_health_metric(health_ws, "ground_truth_accuracy", metrics.overall_accuracy)
    _update_health_metric(health_ws, "candidate_precision", metrics.candidate_precision)
    _update_health_metric(health_ws, "source_chase_recall", metrics.source_chase_recall)
    _update_health_metric(
        health_ws,
        "critical_false_accepts",
        metrics.critical_false_accepts,
    )
    _update_health_metric(health_ws, "wire_dedup_accuracy", metrics.wire_dedup_accuracy)
    _update_health_metric(
        health_ws,
        "last_v04_evaluation",
        now.strftime("%Y-%m-%d %H:%M:%S"),
    )
    return {
        "evaluation_id": evaluation_id,
        "collector_version": CLASSIFICATION_VERSION,
        "ground_truth_batch_id": GROUND_TRUTH_BATCH_ID,
        **asdict(metrics),
    }
