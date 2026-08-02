from __future__ import annotations

from longread_collector import ranked_freshness_v056 as freshness
from longread_collector import ranked_selection_v056 as ranked
from longread_collector.models import DiscoveredURL
from longread_collector.profile_priority_v056g import (
    MIN_NARRATIVE_PROFILE_SIGNAL,
    PROFILE_PRIORITY_VERSION,
    install_profile_priority,
)


def item(title: str) -> DiscoveredURL:
    return DiscoveredURL(
        url="https://example.com/2026/08/01/article.html",
        title=title,
        description="A reported narrative with interviews and documentary evidence.",
        published_at="2026-08-01",
        discovery_method="section_scan",
        query_or_source="source:example",
        metadata={
            "purpose": "native_source_scan",
            "source_id": "example",
            "source_name": "Example",
        },
    )


def test_narrative_profile_signal_survives_base_scorer_reinstall() -> None:
    install_profile_priority()
    # Offline replay reinstalls the scorer at the start of every run. The
    # profile adapter must remain part of the module-global scorer it installs.
    freshness.install_ranked_freshness()

    profile = item("逝者｜改道去灾区，他的最后一次重装徒步")
    _, profile_components = ranked._score(profile, 0)
    assert profile_components["profile_signal"] >= MIN_NARRATIVE_PROFILE_SIGNAL
    assert profile_components["profile_priority_adjustment"] == 4
    assert profile.metadata["selection"]["profile_priority_version"] == (
        PROFILE_PRIORITY_VERSION
    )

    routine = item("一位大学老师的绝笔信")
    _, routine_components = ranked._score(routine, 1)
    assert routine_components["profile_priority_adjustment"] == 0
    assert routine_components.get("profile_signal", 0) == 0
