from __future__ import annotations

import re
from urllib.parse import urlsplit

from .models import ExtractedArticle
from .source_chase import SourceChaseQuery, build_source_chase_queries as _base_build_queries

PUBLISHER_HINTS = {
    "新华社": "xinhuanet.com",
    "商务部": "mofcom.gov.cn",
    "中央原始发布": "gov.cn",
}
TAKEAWAY_PREFIX_RE = re.compile(
    r"^(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+takeaways?\s+from\s+"
    r"(?:the\s+)?(?:times\s+)?(?:investigation\s+into\s+)?",
    re.IGNORECASE,
)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _clean(value: str, limit: int = 220) -> str:
    text = re.sub(r"https?://\S+", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip(" -|:")
    return text[:limit]


def build_source_chase_queries_v055(
    articles: list[ExtractedArticle],
    registry: list[dict[str, object]],
    *,
    limit: int = 3,
) -> list[SourceChaseQuery]:
    base = _base_build_queries(articles, registry, limit=limit)
    by_id = {article.article_id: article for article in articles}
    result: list[SourceChaseQuery] = []

    for query in base:
        article = by_id.get(query.parent_article_id)
        if article is None:
            result.append(query)
            continue

        include_domains = list(query.include_domains)
        current_domain = _domain(article.url)
        if current_domain and current_domain not in include_domains:
            include_domains.insert(0, current_domain)

        original_hint = PUBLISHER_HINTS.get(article.original_publisher)
        if original_hint and original_hint not in include_domains:
            include_domains.insert(0, original_hint)

        reason = article.classification_reason
        query_text = query.query
        if reason == "takeaways_requires_main_article":
            core = TAKEAWAY_PREFIX_RE.sub("", article.title).strip()
            core = _clean(core or article.description or article.title)
            query_text = f'"{core}" full investigation original article'
        elif reason == "investigation_project_requires_article":
            seed = _clean(article.description or article.content_markdown[:500] or article.title)
            query_text = f'"{seed}" latest investigation article'
        elif reason == "article_promotion_requires_original":
            seed = _clean(article.description or article.title)
            query_text = f'"{seed}" original article investigation'
        elif reason == "government_republish_requires_original":
            query_text = f'"{_clean(article.title)}" official original'

        result.append(
            SourceChaseQuery(
                parent_article_id=query.parent_article_id,
                query=query_text,
                include_domains=include_domains[:3],
                language=query.language,
            )
        )
    return result


__all__ = ["build_source_chase_queries_v055"]
