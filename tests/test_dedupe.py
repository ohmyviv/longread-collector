from __future__ import annotations

from longread_collector.dedupe import apply_batch_duplicate_clusters
from longread_collector.models import ExtractedArticle


def make_article(article_id: str, domain: str, title: str) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url=f"https://{domain}/story/{article_id}",
        url_canonical=f"https://{domain}/story/{article_id}",
        domain=domain,
        title=title,
        verification_level="B",
        content_chars=8000,
        content_markdown="substantive body " * 600,
        eligible_for_editor=True,
    )


def test_three_domain_republish_cluster_is_one_source_cluster() -> None:
    articles = [
        make_article(
            "a",
            "fortune.example",
            "Trump administration admits it canceled $7.6 billion in clean energy projects based solely on political identity | Fortune",
        ),
        make_article(
            "b",
            "regional-reporter.example",
            "Trump administration admits grants for clean energy were canceled based on politics – RegionalReporter",
        ),
        make_article(
            "c",
            "daily-news.example",
            "Trump administration admits grants for clean energy were canceled based on politics",
        ),
    ]
    clusters = apply_batch_duplicate_clusters(articles)
    assert len(clusters) == 1
    assert len({article.content_cluster_id for article in articles}) == 1
    assert {article.duplicate_type for article in articles} == {
        "cross_site_same_wire"
    }
    assert {article.candidate_disposition for article in articles} == {"reject"}
    assert all(article.eligible_for_editor is False for article in articles)


def test_two_domain_match_is_recorded_without_forcing_rejection() -> None:
    articles = [
        make_article("a", "one.example", "A detailed investigation into city water use"),
        make_article("b", "two.example", "A detailed investigation into city water use"),
    ]
    apply_batch_duplicate_clusters(articles)
    assert {article.duplicate_type for article in articles} == {"near_duplicate"}
    assert {article.candidate_disposition for article in articles} == {
        "formal_candidate"
    }
