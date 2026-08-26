from __future__ import annotations

from longread_collector.effective_route_extensions_v056 import JIEMIAN_EFFECTIVE_ROUTES
from longread_collector.zh_route_shadow_experiment import (
    RouteObservation,
    rank_observations,
    routes_for,
)


def test_shadow_routes_do_not_mutate_current_jiemian_production_routes() -> None:
    shadow_urls = {r.url for r in routes_for("jiemian-depth")}
    assert "https://www.jiemian.com/lists/472.html" in shadow_urls
    assert "https://www.jiemian.com/lists/472.html" not in JIEMIAN_EFFECTIVE_ROUTES
    assert "https://www.jiemian.com/lists/854.html" not in JIEMIAN_EFFECTIVE_ROUTES
    assert "https://www.jiemian.com/lists/441.html" not in JIEMIAN_EFFECTIVE_ROUTES


def test_negative_controls_are_explicit_and_optional() -> None:
    yicai_all = routes_for("yicai")
    assert any(route.role == "negative_control" for route in yicai_all)
    assert all(route.role != "negative_control" for route in routes_for("yicai", include_negative_controls=False))


def test_route_ranking_rewards_known_miss_recovery_and_low_noise() -> None:
    useful = RouteObservation(
        route_id="useful", total_items=20, known_miss_hits=1,
        timestamped_items=18, high_value_items=10, noise_items=2,
    )
    noisy = RouteObservation(
        route_id="noisy", total_items=20, known_miss_hits=0,
        timestamped_items=20, high_value_items=2, noise_items=16,
    )
    assert rank_observations([noisy, useful])[0].route_id == "useful"
