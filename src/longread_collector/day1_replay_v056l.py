"""Replay the Aug 6 v0.5.6k human labels through v0.5.6l.

This module is temporary validation scaffolding for PR #55 and is removed
before merge. It reads immutable review rows and the referenced cache rows,
then applies the same final classifier, freshness gate and historical document
dedupe used by production.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from .classification_v056l import (
    CLASSIFICATION_VERSION,
    classify_candidate_v056l,
    sanitize_author_v056l,
)
from .content_identity_v056j import evaluate_content_identity
from .historical_dedupe_v056l import apply_historical_primary_document_dedupe
from .models import DiscoveredURL, ExtractedArticle
from .post_extraction_gates_v056l import apply_post_extraction_gates_v056l
from .publication_date_v056l import extract_body_publication_date_v056l
from .sheets import ARTICLE_HEADERS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
BJ = ZoneInfo("Asia/Shanghai")
AUDIT_ID = "SHADOW-AUDIT-20260806-0740-BJT-V056K-PREREPORT-FULL32"
RUN_ID = "COL-20260806-045023-BJT-pre_report"
REVIEW_HEADERS = [
    "audit_id", "reviewed_at_bj", "collector_run_id", "cache_row", "article_id",
    "title", "predicted_page_type", "predicted_disposition", "expected_page_type",
    "expected_content_type", "expected_disposition", "expected_source_relationship",
    "expected_duplicate_type", "expected_source_action", "review_reason", "confidence",
    "is_disposition_correct", "status", "editorial_value", "serious_false_accept",
    "swap_target_article_id", "batch_id", "should_enter_top32", "selection_regret",
]


def _record(headers: list[str], values: list[Any]) -> dict[str, Any]:
    padded = list(values) + [""] * max(0, len(headers) - len(values))
    return dict(zip(headers, padded, strict=False))


def _apply_result(article: ExtractedArticle, result: Any) -> None:
    for field in (
        "page_role", "page_type", "content_type", "candidate_disposition",
        "special_candidate_type", "source_relationship", "original_publisher",
        "original_url", "wire_service", "source_action", "duplicate_type",
        "content_cluster_id",
    ):
        setattr(article, field, getattr(result, field))
    article.classification_confidence = result.confidence
    article.classification_version = CLASSIFICATION_VERSION
    article.classification_reason = result.reason
    article.eligible_for_editor = result.eligible_for_editor
    article.reject_reason = "" if result.eligible_for_editor else result.reason
    if result.original_publisher:
        article.canonical_source = result.original_publisher


def _article_from_cache(row: dict[str, Any]) -> tuple[DiscoveredURL, ExtractedArticle]:
    try:
        metadata = json.loads(str(row.get("metadata_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    markdown = str(row.get("content_markdown") or "")
    title = str(row.get("title") or "")
    identity = evaluate_content_identity(
        title=title,
        markdown=markdown,
        discovered_title=title,
    )
    title = identity.resolved_title or title
    discovered = DiscoveredURL(
        url=str(row.get("url") or row.get("url_canonical") or ""),
        title=title,
        description=str(row.get("description") or ""),
        published_at=str(row.get("published_at") or ""),
        language=str(row.get("language") or ""),
        metadata={},
    )
    raw_author = str(row.get("author") or "")
    article = ExtractedArticle(
        article_id=str(row.get("article_id") or ""),
        url=discovered.url,
        url_canonical=str(row.get("url_canonical") or discovered.url),
        domain=str(row.get("domain") or ""),
        title=title,
        author=sanitize_author_v056l(raw_author),
        published_at=str(row.get("published_at") or ""),
        language=str(row.get("language") or ""),
        canonical_source=str(row.get("canonical_source") or ""),
        hosting_source=str(row.get("hosting_source") or ""),
        description=str(row.get("description") or ""),
        extractor_used=str(row.get("extractor_used") or ""),
        extraction_status=str(row.get("extraction_status") or ""),
        verification_level=str(row.get("verification_level") or ""),
        content_markdown=markdown,
        content_chars=int(row.get("content_chars") or len(markdown)),
        metadata=metadata if isinstance(metadata, dict) else {},
        classification_version=CLASSIFICATION_VERSION,
    )
    article.metadata["content_identity"] = identity.as_dict()
    article.metadata["content_metrics"] = {
        "body_prose_chars": identity.body_prose_chars,
        "raw_markdown_chars": identity.raw_markdown_chars,
        "heading_count": identity.heading_count,
    }
    result = classify_candidate_v056l(
        url=article.url,
        title=article.title,
        description=article.description,
        author=article.author,
        markdown=article.content_markdown,
        published_at=article.published_at,
        verification_level=article.verification_level,
        content_chars=identity.body_prose_chars,
    )
    _apply_result(article, result)
    apply_post_extraction_gates_v056l(
        discovered,
        article,
        now=datetime(2026, 8, 6, 4, 50, 23, tzinfo=BJ),
        body_date_extractor=extract_body_publication_date_v056l,
    )
    return discovered, article


def run(spreadsheet_id: str, credentials_file: Path) -> dict[str, Any]:
    credentials = Credentials.from_service_account_file(
        str(credentials_file), scopes=SCOPES
    )
    book = gspread.authorize(credentials).open_by_key(spreadsheet_id)
    review_values = book.worksheet("collector_shadow_review_items").get_all_values()
    reviews = [
        _record(REVIEW_HEADERS, row)
        for row in review_values[1:]
        if row and row[0] == AUDIT_ID and len(row) > 2 and row[2] == RUN_ID
    ]
    if len(reviews) != 32:
        raise RuntimeError(f"expected 32 review rows, got {len(reviews)}")

    cache_ws = book.worksheet("article_cache")
    cache_values = cache_ws.get_all_values()
    cache_headers = cache_values[0]
    historical_rows = [_record(cache_headers, row) for row in cache_values[1:]]

    evaluated: list[tuple[dict[str, Any], ExtractedArticle]] = []
    for review in reviews:
        row_number = int(str(review["cache_row"]))
        cache_row = _record(cache_headers, cache_ws.row_values(row_number))
        discovered, article = _article_from_cache(cache_row)
        apply_historical_primary_document_dedupe(
            [(discovered, article)], historical_rows
        )
        evaluated.append((review, article))

    fields = {
        "disposition": ("expected_disposition", "candidate_disposition"),
        "page_type": ("expected_page_type", "page_type"),
        "source_relationship": ("expected_source_relationship", "source_relationship"),
        "duplicate_type": ("expected_duplicate_type", "duplicate_type"),
        "source_action": ("expected_source_action", "source_action"),
    }
    totals: dict[str, int] = {}
    differences: list[dict[str, Any]] = []
    for label, (expected_key, actual_field) in fields.items():
        correct = 0
        for review, article in evaluated:
            expected = str(review.get(expected_key) or "")
            actual = str(getattr(article, actual_field) or "")
            if expected == actual:
                correct += 1
            else:
                differences.append(
                    {
                        "article_id": review["article_id"],
                        "title": review["title"],
                        "field": label,
                        "expected": expected,
                        "actual": actual,
                        "reason": article.classification_reason,
                        "reject_reason": article.reject_reason,
                    }
                )
        totals[label] = correct

    disposition_counts = Counter(
        article.candidate_disposition for _, article in evaluated
    )
    report = {
        "audit_id": AUDIT_ID,
        "run_id": RUN_ID,
        "evaluated": len(evaluated),
        "correct": totals,
        "disposition_counts": dict(disposition_counts),
        "differences": differences,
        "passed": all(value == 32 for value in totals.values()),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.spreadsheet_id, args.credentials_file)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
