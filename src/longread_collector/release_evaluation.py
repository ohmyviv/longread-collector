from __future__ import annotations

from dataclasses import asdict
from urllib.parse import urlsplit

from .classification import CLASSIFICATION_VERSION
from .dedupe import apply_batch_duplicate_clusters
from .evaluation import GROUND_TRUTH_BATCH_ID, calculate_metrics
from .models import ExtractedArticle


def _to_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def build_release_predictions(
    ground_truth: list[dict[str, object]],
    cache_rows: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    cache = {
        str(row.get("article_id", "")): row
        for row in cache_rows
        if row.get("article_id")
    }
    articles: list[ExtractedArticle] = []
    for truth in ground_truth:
        article_id = str(truth.get("article_id", ""))
        cached = cache.get(article_id, {})
        url = str(cached.get("url") or truth.get("url") or "")
        articles.append(
            ExtractedArticle(
                article_id=article_id,
                url=url,
                url_canonical=str(cached.get("url_canonical") or url),
                domain=str(cached.get("domain") or _domain(url)),
                title=str(cached.get("title") or truth.get("title") or ""),
                author=str(cached.get("author") or ""),
                published_at=str(cached.get("published_at") or ""),
                language=str(cached.get("language") or ""),
                canonical_source=str(cached.get("canonical_source") or ""),
                hosting_source=str(cached.get("hosting_source") or ""),
                description=str(cached.get("description") or ""),
                extraction_status=str(cached.get("extraction_status") or "failed"),
                verification_level=str(cached.get("verification_level") or "D"),
                content_markdown=str(cached.get("content_markdown") or ""),
                content_chars=_to_int(cached.get("content_chars")),
                eligible_for_editor=_to_bool(cached.get("eligible_for_editor")),
            )
        )
    apply_batch_duplicate_clusters(articles)
    return {
        article.article_id: {
            "candidate_disposition": article.candidate_disposition,
            "page_type": article.page_type,
            "content_type": article.content_type,
            "source_action": article.source_action,
            "duplicate_type": article.duplicate_type,
            "content_cluster_id": article.content_cluster_id,
            "classification_reason": article.classification_reason,
        }
        for article in articles
    }


def _update_health_metric(worksheet: object, metric: str, value: object) -> None:
    for row_number, row in enumerate(worksheet.get_all_values()[1:], start=2):
        if row and str(row[0]).strip() == metric:
            worksheet.update(
                range_name=f"B{row_number}",
                values=[[value]],
                value_input_option="USER_ENTERED",
            )
            return
    raise ValueError(f"collector_health metric not found: {metric}")


def _append_item_diagnostics(
    worksheet: object,
    *,
    evaluation_id: str,
    truth_rows: list[dict[str, object]],
    predictions: dict[str, dict[str, object]],
) -> list[int]:
    rows: list[list[object]] = []
    incorrect: list[int] = []
    for truth in truth_rows:
        article_id = str(truth.get("article_id", ""))
        prediction = predictions.get(article_id, {})
        expected = str(truth.get("disposition", ""))
        predicted = str(prediction.get("candidate_disposition", "reject"))
        review_index = _to_int(truth.get("review_index"))
        correct = expected == predicted
        if not correct:
            incorrect.append(review_index)
        rows.append(
            [
                evaluation_id,
                review_index,
                article_id,
                str(truth.get("title", "")),
                expected,
                predicted,
                str(truth.get("page_type", "")),
                str(prediction.get("page_type", "")),
                str(prediction.get("content_type", "")),
                str(prediction.get("source_action", "")),
                str(prediction.get("duplicate_type", "")),
                str(prediction.get("content_cluster_id", "")),
                str(prediction.get("classification_reason", "")),
                str(correct).upper(),
            ]
        )
    worksheet.append_rows(
        rows,
        value_input_option="USER_ENTERED",
        table_range="A:N",
    )
    return incorrect


def evaluate_release_ground_truth(store: object) -> dict[str, object]:
    truth_ws = store.book.worksheet("collector_ground_truth")
    cache_ws = store.book.worksheet("article_cache")
    evaluation_ws = store.book.worksheet("collector_evaluations")
    item_ws = store.book.worksheet("collector_evaluation_items")
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
    predictions = build_release_predictions(
        truth_rows,
        cache_ws.get_all_records(),
    )
    metrics = calculate_metrics(truth_rows, predictions)
    now = store._now()
    evaluation_id = f"EVAL-{now.strftime('%Y%m%d-%H%M%S')}-BJT-v04"
    incorrect_items = _append_item_diagnostics(
        item_ws,
        evaluation_id=evaluation_id,
        truth_rows=truth_rows,
        predictions=predictions,
    )
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
            f"fixed fixture evaluation after batch dedupe; incorrect={incorrect_items}; shadow-day gate separate",
        ],
        value_input_option="USER_ENTERED",
    )
    values = {
        "ground_truth_accuracy": metrics.overall_accuracy,
        "candidate_precision": metrics.candidate_precision,
        "source_chase_recall": metrics.source_chase_recall,
        "critical_false_accepts": metrics.critical_false_accepts,
        "wire_dedup_accuracy": metrics.wire_dedup_accuracy,
        "last_v04_evaluation": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for metric, value in values.items():
        _update_health_metric(health_ws, metric, value)
    return {
        "evaluation_id": evaluation_id,
        "collector_version": CLASSIFICATION_VERSION,
        "ground_truth_batch_id": GROUND_TRUTH_BATCH_ID,
        "incorrect_items": incorrect_items,
        **asdict(metrics),
    }
