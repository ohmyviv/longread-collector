from longread_collector.classification_v055 import classify_candidate_v055
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.ranked_selection_v055 import filter_discovered
from longread_collector.source_chase_v055 import build_source_chase_queries_v055


def _native(source_id: str, index: int, title: str | None = None) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://{source_id}.example.com/2026/08/01/article-{index}.html",
        title=title or f"Investigation article {source_id} {index}",
        description="A detailed reported feature with original evidence and analysis.",
        published_at="2026-08-01",
        rank=index,
        discovery_method="rss",
        query_or_source=f"source:{source_id}",
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_id,
        },
    )


def _open(domain_index: int) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://open{domain_index}.example.org/2026/08/01/story.html",
        title=f"Open analysis story {domain_index}",
        description="Independent analysis with enough metadata for ranking.",
        published_at="2026-08-01",
        rank=1,
        discovery_method="firecrawl_search",
        query_or_source="en_ai_fresh",
    )


def test_deterministic_hard_gates_and_special_routes() -> None:
    correction = classify_candidate_v055(
        url="https://nature.com/articles/s1",
        title="Author Correction: Important membrane paper",
    )
    assert correction.candidate_disposition == "reject"
    assert correction.page_type == "correction_notice"

    press = classify_candidate_v055(
        url="https://www.prnewswire.com/news-releases/report.html",
        title="Generative AI Market worth $1,658 billion by 2033",
    )
    assert press.candidate_disposition == "reject"
    assert press.page_type == "press_release"

    paper = classify_candidate_v055(
        url="https://www.sciencedirect.com/science/article/pii/S123",
        title="A peer reviewed research article",
        markdown="doi 10.1000/example",
    )
    assert paper.candidate_disposition == "special_candidate"
    assert paper.special_candidate_type == "academic"

    takeaways = classify_candidate_v055(
        url="https://www.nytimes.com/2026/07/31/magazine/takeaways-ai.html",
        title="Five Takeaways From the Times Investigation Into Larry Ellison's A.I. Gamble",
    )
    assert takeaways.candidate_disposition == "original_source_required"
    assert takeaways.source_action == "find_original_article"


def test_bucketed_selection_reserves_sixteen_native_and_sixteen_open() -> None:
    discovered = []
    for source_index in range(8):
        for article_index in range(1, 4):
            discovered.append(_native(f"source{source_index}", article_index))
    discovered.extend(_open(index) for index in range(20))

    accepted, _ = filter_discovered(discovered, max_urls=32, max_per_domain=2)
    native = [item for item in accepted if item.metadata.get("purpose") == "native_source_scan"]
    open_items = [item for item in accepted if item.metadata.get("purpose") != "native_source_scan"]

    assert len(native) == 16
    assert len(open_items) == 16
    assert all(item.metadata["selection"]["version"] == "ranked-bucketed-v0.5.5" for item in accepted)
    assert [item.metadata["selection"]["selected_order"] for item in accepted] == list(range(1, 33))


def test_main_article_outranks_takeaways_within_native_source() -> None:
    items = [
        _native(
            "nyt",
            1,
            "Five Takeaways From the Times Investigation Into Larry Ellison's A.I. Gamble",
        ),
        _native(
            "nyt",
            2,
            "Larry Ellison Bet It All on the A.I. Boom. Will He Be the Face of the A.I. Bubble?",
        ),
    ]
    accepted, _ = filter_discovered(items, max_urls=1, max_per_domain=2)
    assert len(accepted) == 1
    assert accepted[0].title.startswith("Larry Ellison Bet It All")


def test_source_chase_uses_same_domain_for_takeaways() -> None:
    article = ExtractedArticle(
        article_id="a1",
        url="https://www.nytimes.com/2026/07/31/magazine/takeaways-ai.html",
        url_canonical="https://nytimes.com/2026/07/31/magazine/takeaways-ai.html",
        domain="nytimes.com",
        title="Five Takeaways From the Times Investigation Into Larry Ellison's A.I. Gamble",
        description="The billionaire's company took on debt to build data centers.",
        language="en",
        candidate_disposition="original_source_required",
        source_action="find_original_article",
        content_type="reported_longread",
        classification_reason="takeaways_requires_main_article",
        classification_version="collector-v0.5.5",
    )
    queries = build_source_chase_queries_v055([article], [], limit=3)
    assert len(queries) == 1
    assert "nytimes.com" in queries[0].include_domains
    assert "full investigation original article" in queries[0].query
    assert "Five Takeaways" not in queries[0].query
