from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import ExtractedArticle

PUBLISHER_DOMAIN_HINTS = {
    "Associated Press": "apnews.com",
    "Reuters": "reuters.com",
    "Foreign Policy": "foreignpolicy.com",
}
GENERIC_TITLES = {
    "instagram",
    "facebook",
    "threads",
    "statecollege.com",
    "403 forbidden",
    "just a moment...",
}


@dataclass(slots=True)
class SourceChaseQuery:
    parent_article_id: str
    query: str
    include_domains: list[str]
    language: str


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _clean_query_text(value: str, limit: int = 220) -> str:
    value = re.sub(r"https?://\S+", " ", value or "")
    value = re.sub(r"\s+", " ", value).strip(" -|:")
    return value[:limit]


def _registry_domain_hints(
    sample: str,
    registry: list[dict[str, object]],
) -> list[str]:
    lower = sample.lower()
    result: list[str] = []
    for source in registry:
        source_id = str(source.get("source_id", "")).strip().lower()
        source_name = str(source.get("source_name", "")).strip().lower()
        homepage = str(source.get("homepage_url", "")).strip()
        if not homepage:
            continue
        if (source_id and source_id in lower) or (source_name and source_name in lower):
            domain = _domain(homepage)
            if domain and domain not in result:
                result.append(domain)
    return result


def build_source_chase_query(
    article: ExtractedArticle,
    registry: list[dict[str, object]],
) -> SourceChaseQuery:
    sample = " ".join(
        value
        for value in (
            article.title,
            article.description,
            article.original_publisher,
        )
        if value
    )
    title = _clean_query_text(article.title)
    if title.lower() in GENERIC_TITLES or len(title) < 12:
        title = _clean_query_text(article.description)
    if not title:
        title = _clean_query_text(article.content_markdown[:600])

    include_domains: list[str] = []
    publisher_domain = PUBLISHER_DOMAIN_HINTS.get(article.original_publisher)
    if publisher_domain:
        include_domains.append(publisher_domain)
    for domain in _registry_domain_hints(sample, registry):
        if domain not in include_domains:
            include_domains.append(domain)

    publisher = _clean_query_text(article.original_publisher, limit=80)
    query_parts = [f'"{title}"' if title else ""]
    if publisher:
        query_parts.append(publisher)
    if article.source_action == "find_primary_document":
        query_parts.append("official full document")
    elif article.content_type in {"reported_longread", "reported_article"}:
        query_parts.append("original investigation article")
    else:
        query_parts.append("original source")
    return SourceChaseQuery(
        parent_article_id=article.article_id,
        query=" ".join(part for part in query_parts if part),
        include_domains=include_domains[:2],
        language=article.language,
    )


def build_source_chase_queries(
    articles: list[ExtractedArticle],
    registry: list[dict[str, object]],
    *,
    limit: int = 3,
) -> list[SourceChaseQuery]:
    leads = [
        article
        for article in articles
        if article.candidate_disposition == "original_source_required"
    ]
    ranked = sorted(
        leads,
        key=lambda article: (
            0 if article.original_publisher else 1,
            0 if article.classification_confidence == "high" else 1,
            -article.content_chars,
            article.article_id,
        ),
    )
    return [
        build_source_chase_query(article, registry)
        for article in ranked[: max(0, limit)]
    ]
