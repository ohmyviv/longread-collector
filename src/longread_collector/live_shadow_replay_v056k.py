"""Replay the reviewed Aug 5 production cache against final v0.5.6k policy.

This module is intentionally validation-only. It reads the review and cache
sheets, writes a JSON evidence artifact, and exits non-zero unless every
available reviewed body matches both expected disposition and source
relationship.
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread

from .classification_v056k_final import classify_candidate_v056k_final
from .content_identity_v056j import evaluate_content_identity
from .models import DiscoveredURL, ExtractedArticle
from .pipeline_v056d import _apply_classification
from . import post_extraction_gates_v056k as post_gates
from .publication_date_v056k_final import extract_body_publication_date_final

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 5, 22, 0, tzinfo=BJ)
EXPECTED_EVALUABLE = 55
TARGET_BATCHES = {
    "V056J-DAY1-20260805-BLOCKER4",
    "V056J-DAY1-20260805-PREREPORT-CANDIDATES",
    "V056J-DAY1-20260805-ZH-MIDDAY-CANDIDATES",
    "V056J-DAY1-20260805-ZH-MIDDAY-REJECTS",
}


def _pad(row: list[str], size: int) -> list[str]:
    return row + [""] * max(0, size - len(row))


def run_replay(*, sheet_id: str, credentials_file: str) -> dict[str, object]:
    post_gates.extract_body_publication_date = extract_body_publication_date_final

    client = gspread.service_account(filename=credentials_file)
    book = client.open_by_key(sheet_id)
    reviews = book.worksheet("collector_shadow_review_items").get("A313:X369")

    latest: dict[str, list[str]] = {}
    for raw in reviews:
        row = _pad(raw, 24)
        review_article_id = row[4].strip()
        if review_article_id and row[20].strip() in TARGET_BATCHES:
            latest[review_article_id] = row

    cache = book.worksheet("article_cache")
    ordered: list[tuple[str, list[str], int]] = []
    ranges: list[str] = []
    for review_article_id, review in latest.items():
        try:
            cache_row = int(float(review[3]))
        except ValueError:
            continue
        ordered.append((review_article_id, review, cache_row))
        ranges.append(f"A{cache_row}:AV{cache_row}")

    payloads = cache.batch_get(ranges)
    results: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for (review_article_id, review, cache_row), payload in zip(
        ordered,
        payloads,
        strict=True,
    ):
        values = _pad(payload[0] if payload else [], 48)
        cache_article_id = values[0].strip()
        extraction_status = values[16].strip()
        markdown = values[20]
        # Human review established that a substantial recovered body remains
        # evaluable even when the extraction terminal status is "rejected".
        # Only genuinely missing/short bodies are excluded.
        if len(markdown.strip()) < 500:
            skipped.append(
                {
                    "review_article_id": review_article_id,
                    "cache_article_id": cache_article_id,
                    "cache_article_id_mismatch": cache_article_id
                    != review_article_id,
                    "cache_row": cache_row,
                    "title": values[8],
                    "reason": "body_not_evaluable",
                    "extraction_status": extraction_status,
                    "markdown_chars": len(markdown.strip()),
                }
            )
            continue

        try:
            metadata = json.loads(values[22] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        discovery_meta = dict(metadata.get("discovery") or {})
        discovery_meta["discovery"] = metadata.get("discovery") or {}

        discovered = DiscoveredURL(
            url=values[6] or values[5],
            title=values[8],
            description=values[14],
            published_at=values[10],
            discovery_method=values[3],
            query_or_source=values[4],
            language=values[11],
            metadata=discovery_meta,
        )
        identity = evaluate_content_identity(
            title=values[8],
            markdown=markdown,
            discovered_title=values[8],
        )
        classified = classify_candidate_v056k_final(
            url=values[6] or values[5],
            title=values[8],
            description=values[14],
            author=values[9],
            markdown=markdown,
            published_at=values[10],
            verification_level=values[17],
            content_chars=identity.body_prose_chars,
        )
        article = ExtractedArticle(
            article_id=review_article_id,
            url=values[5],
            url_canonical=values[6] or values[5],
            domain=values[7],
            title=values[8],
            author=values[9],
            published_at=values[10],
            language=values[11],
            canonical_source=values[12],
            hosting_source=values[13],
            description=values[14],
            extractor_used=values[15],
            extraction_status=extraction_status,
            verification_level=values[17],
            content_markdown=markdown,
            content_chars=int(float(values[18] or 0)),
            classification_version="collector-v0.5.6k",
            metadata={"content_identity": identity.as_dict()},
        )
        _apply_classification(article, classified)
        post_gates.apply_post_extraction_gates_v056k(
            discovered,
            article,
            now=NOW,
        )

        expected_disposition = review[10].strip()
        expected_relationship = review[11].strip()
        disposition_ok = article.candidate_disposition == expected_disposition
        relationship_ok = (
            not expected_relationship
            or article.source_relationship == expected_relationship
        )
        results.append(
            {
                "review_article_id": review_article_id,
                "cache_article_id": cache_article_id,
                "cache_article_id_mismatch": cache_article_id
                != review_article_id,
                "cache_row": cache_row,
                "title": values[8],
                "expected_disposition": expected_disposition,
                "actual_disposition": article.candidate_disposition,
                "expected_source_relationship": expected_relationship,
                "actual_source_relationship": article.source_relationship,
                "disposition_ok": disposition_ok,
                "relationship_ok": relationship_ok,
                "classification_reason": article.classification_reason,
                "reject_reason": article.reject_reason,
                "published_at": article.published_at,
                "published_at_source": article.metadata.get("freshness", {}).get(
                    "published_at_source",
                    "",
                ),
                "body_prose_chars": identity.body_prose_chars,
            }
        )

    disposition_correct = sum(bool(item["disposition_ok"]) for item in results)
    relationship_correct = sum(bool(item["relationship_ok"]) for item in results)
    return {
        "version": "collector-v0.5.6k-final",
        "reviewed_unique": len(latest),
        "evaluable": len(results),
        "expected_evaluable": EXPECTED_EVALUABLE,
        "skipped": skipped,
        "cache_article_id_mismatches": sum(
            bool(item["cache_article_id_mismatch"]) for item in results
        ),
        "disposition_correct": disposition_correct,
        "disposition_accuracy": disposition_correct / len(results) if results else 0,
        "source_relationship_correct": relationship_correct,
        "source_relationship_accuracy": (
            relationship_correct / len(results) if results else 0
        ),
        "mismatches": [
            item
            for item in results
            if not item["disposition_ok"] or not item["relationship_ok"]
        ],
        "items": results,
    }


def main() -> None:
    report = run_replay(
        sheet_id=os.environ["GOOGLE_SHEET_ID"],
        credentials_file=os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"],
    )
    output = Path(
        os.environ.get(
            "V056K_REPLAY_OUTPUT",
            "artifacts/v056k-live-shadow-replay.json",
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {key: value for key, value in report.items() if key != "items"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        Path(step_summary).write_text(
            "## v0.5.6k final live shadow replay\n\n```json\n"
            + json.dumps(summary, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )

    if (
        report["evaluable"] != report["expected_evaluable"]
        or report["disposition_accuracy"] < 1.0
        or report["source_relationship_accuracy"] < 1.0
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
