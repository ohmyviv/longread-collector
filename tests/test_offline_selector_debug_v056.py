from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.freshness_policy_v056 import evaluate_freshness_policy
from longread_collector.models import DiscoveredURL
from longread_collector.page_gate_policy_v056 import evaluate_page_gate_policy
from longread_collector.ranked_freshness_v056 import install_ranked_freshness
from longread_collector.ranked_selection_v056 import filter_discovered

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 1, 19, 6, 55, tzinfo=BJ)


def candidate(url: str, title: str, source_id: str) -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        description="A complete reported article.",
        published_at="2026-08-01",
        query_id="query-a",
        discovery_method="rss",
        rank_score=1,
        metadata={
            "purpose": "native_source_scan",
            "source_id": source_id,
            "native_method": "rss",
        },
    )


def test_low_level_selector_returns_two_candidates() -> None:
    values = [
        candidate(
            "https://www.propublica.org/article/procurement-investigation",
            "Investigation reveals procurement failures",
            "propublica",
        ),
        candidate(
            "https://www.quantamagazine.org/climate-adaptation-feature-20260801/",
            "A reported feature on climate adaptation",
            "quanta",
        ),
    ]
    for value in values:
        assert evaluate_page_gate_policy(value).rejected is False
        freshness = evaluate_freshness_policy(value, phase="prefilter", now=NOW)
        assert freshness.allowed is True, {
            "freshness": freshness,
            "metadata": value.metadata,
        }
    install_ranked_freshness()
    selected, rejected = filter_discovered(values, max_urls=2, max_per_domain=2)
    assert len(selected) == 2, {
        "rejected": rejected,
        "metadata": [value.metadata for value in values],
    }
