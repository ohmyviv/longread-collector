"""Source-chase queries aligned to v0.5.6d relationship decisions."""

from __future__ import annotations

import re

from .models import ExtractedArticle
from .source_chase import SourceChaseQuery
from .source_chase_v055 import build_source_chase_queries_v055

SOURCE_CHASE_VERSION = "relationship-aware-v0.5.6d"


def _clean(value: str, limit: int = 240) -> str:
    text = re.sub(r"https?://\S+", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip(" -|:")
    return text[:limit]


def _promote_domain(domains: list[str], domain: str) -> None:
    domains[:] = [item for item in domains if item != domain]
    domains.insert(0, domain)


def build_source_chase_queries_v056(
    articles: list[ExtractedArticle],
    registry: list[dict[str, object]],
    *,
    limit: int = 3,
) -> list[SourceChaseQuery]:
    base = build_source_chase_queries_v055(articles, registry, limit=limit)
    by_id = {article.article_id: article for article in articles}
    result: list[SourceChaseQuery] = []

    for query in base:
        article = by_id.get(query.parent_article_id)
        if article is None:
            result.append(query)
            continue

        domains = list(query.include_domains)
        reason = str(article.classification_reason or "")
        query_text = query.query

        if reason == "academic_summary_requires_original_v056":
            seed = _clean(article.title or article.description)
            doi_match = re.search(
                r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+",
                article.content_markdown or "",
                re.I,
            )
            if doi_match:
                query_text = f'"{doi_match.group(0)}" original journal article'
                _promote_domain(domains, "doi.org")
            else:
                query_text = f'"{seed}" original paper DOI journal'
        elif reason.startswith("reuters_strong_wire_"):
            query_text = f'"{_clean(article.title)}" site:reuters.com'
            _promote_domain(domains, "reuters.com")
        elif reason.startswith("ap_strong_wire_"):
            query_text = f'"{_clean(article.title)}" site:apnews.com'
            _promote_domain(domains, "apnews.com")

        result.append(
            SourceChaseQuery(
                parent_article_id=query.parent_article_id,
                query=query_text,
                include_domains=domains[:3],
                language=query.language,
            )
        )
    return result


__all__ = ["SOURCE_CHASE_VERSION", "build_source_chase_queries_v056"]
