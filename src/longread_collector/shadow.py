from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable

from .models import ExtractedArticle

CRITICAL_NON_CONTENT_PAGE_TYPES = {
    "job_or_career",
    "login_or_auth",
    "homepage",
    "channel_or_listing",
    "spam_or_malicious",
}


def technical_eligible_before(article: ExtractedArticle) -> bool:
    classification = article.metadata.get("classification", {})
    if not isinstance(classification, dict):
        return False
    return bool(classification.get("technical_eligible_before", False))


def build_shadow_row(
    *,
    run_id: str,
    completed_at_bj: str,
    query_group: str,
    articles: Iterable[ExtractedArticle],
) -> list[object]:
    items = list(articles)
    dispositions = Counter(item.candidate_disposition for item in items)
    v03_eligible = sum(technical_eligible_before(item) for item in items)
    disagreement_count = sum(
        technical_eligible_before(item)
        != (item.candidate_disposition == "formal_candidate")
        for item in items
    )
    critical_false_accepts = sum(
        item.candidate_disposition == "formal_candidate"
        and item.page_type in CRITICAL_NON_CONTENT_PAGE_TYPES
        for item in items
    )
    unique_hosting_sources = {
        item.hosting_source for item in items if item.hosting_source
    }
    unique_canonical_sources = {
        item.canonical_source
        for item in items
        if item.canonical_source and item.candidate_disposition != "reject"
    }
    duplicate_clusters = {
        item.content_cluster_id for item in items if item.content_cluster_id
    }
    return [
        run_id,
        completed_at_bj,
        query_group,
        len(items),
        v03_eligible,
        dispositions.get("formal_candidate", 0),
        dispositions.get("special_candidate", 0),
        dispositions.get("original_source_required", 0),
        dispositions.get("reject", 0),
        disagreement_count,
        critical_false_accepts,
        len(unique_hosting_sources),
        len(unique_canonical_sources),
        len(duplicate_clusters),
        "pending",
        "",
        "",
        "classification_version=collector-v0.4.0",
    ]


def append_shadow_ab(
    store: object,
    *,
    run_id: str,
    query_group: str,
    articles: Iterable[ExtractedArticle],
    completed_at: datetime,
) -> None:
    """Append one shadow comparison row through an existing Sheet store.

    ``store`` intentionally uses a structural interface so this module remains
    independently testable: it only requires ``store.book.worksheet``.
    """

    row = build_shadow_row(
        run_id=run_id,
        completed_at_bj=completed_at.strftime("%Y-%m-%d %H:%M:%S"),
        query_group=query_group,
        articles=articles,
    )
    worksheet = store.book.worksheet("collector_shadow_ab")
    worksheet.append_row(row, value_input_option="USER_ENTERED")
