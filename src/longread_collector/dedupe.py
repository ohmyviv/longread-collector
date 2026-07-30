from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Iterable

from .classification import wire_title_fingerprint
from .models import ExtractedArticle

ORIGINAL_WIRE_DOMAINS = {
    "apnews.com",
    "reuters.com",
}
LONG_QUOTED_SEGMENT = re.compile(
    r"(?:'[^']{10,}'|\"[^\"]{10,}\"|“[^”]{10,}”)",
    re.IGNORECASE,
)


def batch_headline_fingerprint(title: str) -> str:
    """Normalize outlet suffixes and variable quoted attribution tails."""
    return wire_title_fingerprint(LONG_QUOTED_SEGMENT.sub(" ", title or ""))


def headline_cluster_id(title: str) -> str:
    fingerprint = batch_headline_fingerprint(title)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"headline-{digest}"


def apply_batch_duplicate_clusters(
    articles: Iterable[ExtractedArticle],
) -> dict[str, list[str]]:
    """Assign cross-site clusters using generic normalized headline evidence.

    Two-domain matches are recorded as near duplicates. Three or more domains
    with the same stable headline fingerprint are treated as syndicated or
    heavily republished content. The function never uses fixture IDs.
    """

    items = list(articles)
    groups: dict[str, list[ExtractedArticle]] = defaultdict(list)
    for article in items:
        if article.page_type != "article":
            continue
        fingerprint = batch_headline_fingerprint(article.title)
        if len(fingerprint.split()) < 4:
            continue
        groups[fingerprint].append(article)

    applied: dict[str, list[str]] = {}
    for fingerprint, group in groups.items():
        domains = {article.domain for article in group if article.domain}
        if len(domains) < 2:
            continue
        cluster_id = headline_cluster_id(group[0].title)
        wire_service = next(
            (article.wire_service for article in group if article.wire_service),
            "",
        )
        syndicated = bool(wire_service) or len(domains) >= 3
        has_original_wire_domain = any(
            article.domain in ORIGINAL_WIRE_DOMAINS for article in group
        )
        for article in group:
            article.content_cluster_id = cluster_id
            article.duplicate_type = (
                "cross_site_same_wire" if syndicated else "near_duplicate"
            )
            if wire_service and not article.wire_service:
                article.wire_service = wire_service
            if syndicated:
                article.content_type = "syndicated_wire"
                article.source_relationship = "wire_republish"
                if wire_service == "AP" and not article.original_publisher:
                    article.original_publisher = "Associated Press"
                elif wire_service == "Reuters" and not article.original_publisher:
                    article.original_publisher = "Reuters"
                if (
                    not has_original_wire_domain
                    and article.candidate_disposition == "formal_candidate"
                ):
                    article.candidate_disposition = "reject"
                    article.eligible_for_editor = False
                    article.reject_reason = "cross_site_republish_cluster"
                    article.classification_reason = "cross_site_republish_cluster"
            article.metadata.setdefault("dedupe", {})
            article.metadata["dedupe"].update(
                {
                    "cluster_id": cluster_id,
                    "fingerprint": fingerprint,
                    "domains": sorted(domains),
                    "batch_cluster_size": len(group),
                    "duplicate_type": article.duplicate_type,
                }
            )
        applied[cluster_id] = [article.article_id for article in group]
    return applied
