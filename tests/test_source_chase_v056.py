from __future__ import annotations

from longread_collector.models import ExtractedArticle
from longread_collector.source_chase_v056 import build_source_chase_queries_v056


def lead(
    *,
    article_id: str,
    title: str,
    reason: str,
    original_publisher: str = "",
    markdown: str = "",
) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url="https://example.com/source-lead.html",
        url_canonical="https://example.com/source-lead.html",
        domain="example.com",
        title=title,
        language="en",
        original_publisher=original_publisher,
        source_relationship="secondary_summary",
        page_role="discovery_lead",
        page_type="article",
        content_type="academic_summary" if "academic" in reason else "syndicated_wire",
        candidate_disposition="original_source_required",
        source_action="find_original_article",
        classification_confidence="high",
        classification_version="collector-v0.5.6d",
        classification_reason=reason,
        content_markdown=markdown,
        content_chars=max(3000, len(markdown)),
    )


def test_academic_summary_uses_doi_when_available() -> None:
    article = lead(
        article_id="academic-1",
        title="Study reveals new patterns in urban migration",
        reason="academic_summary_requires_original_v056",
        markdown="The original paper is available at DOI 10.1234/example.2026.001.",
    )
    query = build_source_chase_queries_v056([article], [], limit=3)[0]
    assert "10.1234/example.2026.001" in query.query
    assert "doi.org" in query.include_domains


def test_reuters_wire_query_targets_reuters_domain() -> None:
    article = lead(
        article_id="reuters-1",
        title="Governments agree on a new climate framework",
        reason="reuters_strong_wire_structured_author_v056",
        original_publisher="Reuters",
    )
    query = build_source_chase_queries_v056([article], [], limit=3)[0]
    assert "site:reuters.com" in query.query
    assert query.include_domains[0] == "reuters.com"


def test_ap_wire_query_targets_apnews_domain() -> None:
    article = lead(
        article_id="ap-1",
        title="Court ruling reshapes voting access",
        reason="ap_strong_wire_structured_author_v056",
        original_publisher="Associated Press",
    )
    query = build_source_chase_queries_v056([article], [], limit=3)[0]
    assert "site:apnews.com" in query.query
    assert query.include_domains[0] == "apnews.com"
