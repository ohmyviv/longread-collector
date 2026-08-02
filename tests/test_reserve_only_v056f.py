from __future__ import annotations

from longread_collector.models import DiscoveredURL
from longread_collector.prefilter_v056c import filter_discovered
from longread_collector.selection_plan_v056 import (
    clear_selection_plan,
    current_selection_plan,
)


def test_unknown_native_fallback_is_reserve_only_not_initial_selection() -> None:
    clear_selection_plan()
    fallback = DiscoveredURL(
        url="https://example.com/article/62a9e903-c859-4b82-81dd-d0ee1d4adbb0",
        title="Company chairman faces investigation",
        description="A short search summary without publication metadata.",
        discovery_method="firecrawl_search",
        query_or_source="source:example",
        metadata={
            "purpose": "native_source_scan",
            "source_id": "example",
            "source_name": "Example Source",
            "native_method": "firecrawl_search",
        },
    )
    current = DiscoveredURL(
        url="https://news.example.com/article/2026/08/02/current-analysis.html",
        title="Current analysis of industrial policy",
        description="A complete reported analysis with current evidence.",
        published_at="2026-08-02",
        discovery_method="rss",
        query_or_source="source:current",
        metadata={
            "purpose": "native_source_scan",
            "source_id": "current",
            "source_name": "Current Source",
            "native_method": "rss",
        },
    )

    accepted, rejected = filter_discovered([fallback, current], max_urls=1)

    assert rejected == []
    assert [item.url for item in accepted] == [current.url]
    assert fallback.metadata["selection"]["selection_status"] == (
        "evidence_reserve_only"
    )
    assert fallback.metadata["selection"]["selection_force_reserve_only"] is True

    plan = current_selection_plan()
    assert plan is not None
    assert [item.url for item in plan.selected] == [current.url]
    assert fallback.url in [item.url for item in plan.reserves]
