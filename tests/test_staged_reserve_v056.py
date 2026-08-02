from __future__ import annotations

import asyncio
from types import SimpleNamespace

from longread_collector.extraction import FallbackBudget
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.normalization import canonicalize_url, domain_from_url
from longread_collector.pipeline_v056b import (
    NativeCollectorPipeline,
    filter_discovered,
)
from longread_collector.selection_plan_v056 import (
    clear_selection_plan,
    current_selection_plan,
)
from longread_collector.staged_reserve_v056 import (
    build_second_stage,
    split_first_stage,
)


def native(source_id: str, index: int) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://{source_id}.example.com/2026/08/02/report-{index}.html",
        title=f"Investigation report {source_id} {index}",
        description="A detailed reported feature with evidence and analysis.",
        published_at="2026-08-02",
        rank=index,
        discovery_method="rss",
        query_or_source=f"source:{source_id}",
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "source_name": source_id,
        },
    )


def open_item(index: int) -> DiscoveredURL:
    return DiscoveredURL(
        url=f"https://open{index}.example.org/2026/08/02/analysis.html",
        title=f"Open analysis report {index}",
        description="Independent analysis with sufficient article metadata.",
        published_at="2026-08-02",
        rank=1,
        discovery_method="firecrawl_search",
        query_or_source="open-query",
    )


def article(item: DiscoveredURL, *, reject: bool = False) -> ExtractedArticle:
    canonical = canonicalize_url(item.url)
    return ExtractedArticle(
        article_id=f"article-{abs(hash(canonical))}",
        url=item.url,
        url_canonical=canonical,
        domain=domain_from_url(canonical),
        title=item.title,
        extraction_status="success",
        extractor_used="jina",
        candidate_disposition="reject" if reject else "formal_candidate",
        eligible_for_editor=not reject,
        reject_reason="test_reject" if reject else "",
        classification_version="test-v056",
    )


def discovered_fixture() -> list[DiscoveredURL]:
    items = [native("bjnews", index) for index in range(1, 7)]
    items.extend(
        native(f"native{source_index}", article_index)
        for source_index in range(1, 8)
        for article_index in range(1, 3)
    )
    items.extend(open_item(index) for index in range(20))
    return items


def test_second_stage_uses_same_source_reserve_before_deferred_open() -> None:
    clear_selection_plan()
    accepted, rejected = filter_discovered(
        discovered_fixture(), max_urls=32, max_per_domain=2
    )
    plan = current_selection_plan()
    assert plan is not None
    assert rejected == []
    assert len(accepted) == 32

    first, deferred = split_first_stage(accepted, max_attempts=32)
    assert len(first) == 24
    assert len(deferred) == 8
    assert all(
        item.metadata["selection"]["selection_bucket"] == "open"
        for item in deferred
    )

    failed = next(
        item
        for item in first
        if item.metadata["selection"]["selection_group"] == "source:bjnews"
    )
    first_articles = [article(item, reject=item is failed) for item in first]
    decision = build_second_stage(
        plan=plan,
        first_stage=first,
        deferred=deferred,
        first_articles=first_articles,
        max_attempts=32,
    )

    assert len(decision.second_stage) == 8
    assert len(first) + len(decision.second_stage) == 32
    assert len(decision.promoted_reserves) == 1
    promoted = decision.promoted_reserves[0]
    assert promoted.metadata["selection"]["selection_group"] == "source:bjnews"
    assert promoted.metadata["selection"]["reserve_promoted"] is True
    assert promoted.metadata["selection"]["reserve_replacement_for"] == canonicalize_url(
        failed.url
    )
    assert len(decision.deferred_not_extracted) == 1


class FakePipeline(NativeCollectorPipeline):
    def __init__(self, failed_url: str) -> None:
        self.settings = SimpleNamespace(max_urls_per_run=32)
        self.failed_url = canonicalize_url(failed_url)
        self.batches: list[list[str]] = []
        self._primary_selection_extracted = False

    async def _extract_batch(self, discovered, fallback_budget):
        self.batches.append([canonicalize_url(item.url) for item in discovered])
        return [
            article(item, reject=canonicalize_url(item.url) == self.failed_url)
            for item in discovered
        ]


def test_pipeline_replacement_stays_within_32_attempts() -> None:
    clear_selection_plan()
    accepted, _ = filter_discovered(
        discovered_fixture(), max_urls=32, max_per_domain=2
    )
    failed = next(
        item
        for item in accepted
        if item.metadata["selection"]["selection_group"] == "source:bjnews"
    )
    pipeline = FakePipeline(failed.url)
    articles = asyncio.run(
        pipeline._extract_all(accepted, FallbackBudget(remaining=0))
    )

    assert [len(batch) for batch in pipeline.batches] == [24, 8]
    assert sum(len(batch) for batch in pipeline.batches) == 32
    assert len(accepted) == 32
    assert len(articles) == 32
    promoted = [
        item
        for item in accepted
        if item.metadata.get("selection", {}).get("reserve_promoted")
    ]
    assert len(promoted) == 1
    assert promoted[0].metadata["selection"]["selection_group"] == "source:bjnews"
    assert canonicalize_url(promoted[0].url) in pipeline.batches[1]
