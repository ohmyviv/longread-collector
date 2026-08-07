from copy import deepcopy

from longread_collector.models import DiscoveredURL
from longread_collector.v06.contracts import RunContext, StageEventType, StageName
from longread_collector.v06.discovery import DiscoveryAdapter


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="run-pr6",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-07 17:50:00",
        started_at_bj="2026-08-07 17:50:04",
        collector_version="collector-v0.5.6m",
    )


def test_discovery_adapter_preserves_native_route_evidence_without_mutation():
    item = DiscoveredURL(
        url="https://example.com/news/deep-report.html?utm_source=rss",
        title="A deep reported article",
        description="Long investigation description",
        published_at="2026-08-07T09:00:00+08:00",
        discovery_method="rss",
        query_or_source="source:example",
        rank=3,
        metadata={
            "purpose": "native_source_scan",
            "source_id": "example",
            "source_name": "Example News",
            "native_method": "rss",
            "native_endpoint": "https://example.com/feed.xml",
            "priority_tier": "rotate",
            "external_link": "https://original.example.org/story",
        },
    )
    before = deepcopy(item.metadata)

    result = DiscoveryAdapter().adapt(_context(), item, ordinal=3)
    record = result.record

    assert item.metadata == before
    assert record.source_id == "example"
    assert record.discovery_method == "rss"
    assert record.query_or_section == "source:example"
    assert record.rank == 3
    assert record.external_link_hint == "https://original.example.org/story"
    assert record.published_at_hints == ("2026-08-07T09:00:00+08:00",)
    date_evidence = [e for e in record.evidence if e.field == "published_at_hint"]
    assert len(date_evidence) == 1
    assert date_evidence[0].confidence >= 0.92
    assert record.raw_metadata["native_endpoint"] == "https://example.com/feed.xml"
    assert result.event.event_type is StageEventType.DISCOVERY_RESULT
    assert result.event.stage is StageName.DISCOVERY


def test_discovery_adapter_deep_freezes_metadata_and_is_deterministic():
    metadata = {"nested": {"routes": ["rss", "section_scan"]}}
    item = {
        "url": "https://example.com/article/1",
        "title": "Article",
        "published_at": "",
        "discovery_method": "section_scan",
        "query_or_source": "source:example",
        "rank": 1,
        "metadata": metadata,
    }
    adapter = DiscoveryAdapter()
    first = adapter.adapt(_context(), item, ordinal=1)
    second = adapter.adapt(_context(), item, ordinal=1)

    metadata["nested"]["routes"].append("firecrawl_search")
    assert first.record.raw_metadata["nested"]["routes"] == ("rss", "section_scan")
    assert first.record.item_id == second.record.item_id
    assert first.record.discovery_id == second.record.discovery_id


def test_search_route_date_hint_remains_low_confidence():
    item = DiscoveredURL(
        url="https://example.com/article/unknown",
        title="Potential longread",
        published_at="2026-07-01",
        discovery_method="firecrawl_search",
        query_or_source="query:test",
    )
    record = DiscoveryAdapter().adapt(_context(), item).record
    evidence = next(e for e in record.evidence if e.field == "published_at_hint")
    assert evidence.confidence < 0.92
