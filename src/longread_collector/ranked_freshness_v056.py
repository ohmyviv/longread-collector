"""Patch the PR-B reserve selector to rank by resolved publication evidence."""

from __future__ import annotations

from . import ranked_selection_v056 as _ranked
from .freshness_policy_v056 import evaluate_freshness_policy
from .models import DiscoveredURL
from .ranked_selection_v055 import _score as _legacy_score

RANKING_FRESHNESS_VERSION = "resolved-publication-ranking-v0.5.6c"


def score_with_resolved_freshness(
    item: DiscoveredURL,
    original_index: int,
) -> tuple[tuple[int, ...], dict[str, int]]:
    _, components = _legacy_score(item, original_index)
    decision = evaluate_freshness_policy(item, phase="prefilter")
    components = dict(components)
    components["quality"] = int(components.get("quality", 0)) + int(
        decision.score_penalty
    )
    components["freshness_ordinal"] = int(decision.score_ordinal)
    components["freshness_penalty"] = int(decision.score_penalty)
    item.metadata.setdefault("selection", {})["ranking_freshness_version"] = (
        RANKING_FRESHNESS_VERSION
    )
    score = (
        components["quality"],
        components["article_confidence"],
        components["depth"],
        components["freshness_ordinal"],
        components["title_richness"],
        components["description_richness"],
        components["rank_score"],
    )
    return score, components


def install_ranked_freshness() -> None:
    _ranked._score = score_with_resolved_freshness


__all__ = [
    "RANKING_FRESHNESS_VERSION",
    "install_ranked_freshness",
    "score_with_resolved_freshness",
]
