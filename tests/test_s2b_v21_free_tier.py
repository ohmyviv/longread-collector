from __future__ import annotations

import inspect

from longread_collector.zh_route_shadow_s2b_track_v21 import (
    ACQUISITION_VERSION,
    FREE_TIER_DOCUMENTED_RPM,
    FREE_TIER_MIN_INTERVAL_SECONDS,
    run_track_v_free_tier,
)


def test_free_tier_pacing_is_strictly_below_documented_rpm() -> None:
    assert FREE_TIER_DOCUMENTED_RPM == 20
    assert FREE_TIER_MIN_INTERVAL_SECONDS > 60 / FREE_TIER_DOCUMENTED_RPM


def test_free_tier_acquisition_version_is_explicit_and_distinct() -> None:
    assert ACQUISITION_VERSION == "zh-route-shadow-s2b-body-observability-v2.1-free-tier"


def test_runner_explicitly_ignores_configured_jina_key() -> None:
    source = inspect.getsource(run_track_v_free_tier)
    assert "api_key=None" in source
    assert '"jina_authorization_header_sent": False' in source
    assert '"production_equivalent": False' in source
    assert '"live_sheet_writes": 0' in source
    assert '"article_cache_writes": 0' in source
    assert '"editor_writes": 0' in source
