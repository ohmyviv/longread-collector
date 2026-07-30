from __future__ import annotations

from longread_collector.models import ExtractedArticle
from longread_collector.source_chase import (
    build_source_chase_queries,
    build_source_chase_query,
)


def article(**overrides: object) -> ExtractedArticle:
    values: dict[str, object] = {
        "article_id": "lead-1",
        "url": "https://secondary.example/story",
        "url_canonical": "https://secondary.example/story",
        "domain": "secondary.example",
        "title": "Reuters editor warns AI threatens journalism's future",
        "description": "A report about a Reuters public lecture.",
        "language": "en",
        "content_chars": 5000,
        "candidate_disposition": "original_source_required",
        "source_action": "replace_with_original_source",
        "original_publisher": "Reuters",
        "classification_version": "test",
    }
    values.update(overrides)
    return ExtractedArticle(**values)


def test_known_publisher_constrains_source_chase_domain() -> None:
    query = build_source_chase_query(article(), registry=[])
    assert query.parent_article_id == "lead-1"
    assert query.include_domains == ["reuters.com"]
    assert "Reuters" in query.query
    assert "original source" in query.query


def test_registry_name_can_supply_domain_hint() -> None:
    lead = article(
        original_publisher="",
        title="A new investigation from ProPublica",
        description="ProPublica examines the infrastructure behind the project.",
        content_type="reported_longread",
        source_action="find_original_article",
    )
    query = build_source_chase_query(
        lead,
        registry=[
            {
                "source_id": "propublica",
                "source_name": "ProPublica",
                "homepage_url": "https://www.propublica.org/",
            }
        ],
    )
    assert query.include_domains == ["propublica.org"]
    assert "original investigation article" in query.query


def test_source_chase_is_bounded_and_prefers_named_publishers() -> None:
    unnamed = article(
        article_id="unnamed",
        original_publisher="",
        classification_confidence="medium",
    )
    named = article(article_id="named", original_publisher="Reuters")
    rejected = article(
        article_id="rejected",
        candidate_disposition="reject",
    )
    queries = build_source_chase_queries(
        [unnamed, rejected, named],
        registry=[],
        limit=1,
    )
    assert len(queries) == 1
    assert queries[0].parent_article_id == "named"
