"""Narrow narrative-profile priority adjustment for v0.5.6g.

The general editorial scorer already recognizes profiles and obituaries. This
adapter raises strongly signalled narrative profiles to a minimum profile
signal so an older, substantive portrait is not displaced by a routine item
from the same source solely because of a small freshness-score difference.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from . import ranked_freshness_v056 as _freshness
from . import ranked_selection_v056 as _ranked
from .models import DiscoveredURL

PROFILE_PRIORITY_VERSION = "narrative-profile-priority-v0.5.6g"
MIN_NARRATIVE_PROFILE_SIGNAL = 24

_NARRATIVE_PROFILE_RE = re.compile(
    r"^(?:逝者(?:[｜|:：]|\s)|人物特稿|人物志|口述史)|"
    r"\b(?:obituary|profile|portrait)\b",
    re.I,
)
_PROFILE_PATH_RE = re.compile(r"/(?:obituaries?|profiles?|portraits?)(?:/|$)", re.I)


def _strong_narrative_profile(item: DiscoveredURL) -> bool:
    title = str(item.title or "").strip()
    path = urlsplit(item.url).path or "/"
    return bool(_NARRATIVE_PROFILE_RE.search(title) or _PROFILE_PATH_RE.search(path))


def install_profile_priority() -> None:
    """Install an idempotent adapter that survives later scorer reinstalls."""
    current_score = _freshness.score_with_resolved_freshness
    if getattr(current_score, "_profile_priority_version", "") == PROFILE_PRIORITY_VERSION:
        _ranked._score = current_score
        return

    def score_with_profile_priority(
        item: DiscoveredURL,
        original_index: int,
    ) -> tuple[tuple[int, ...], dict[str, int]]:
        score, components = current_score(item, original_index)
        components = dict(components)
        adjustment = 0
        if _strong_narrative_profile(item):
            existing = int(components.get("profile_signal", 0))
            adjustment = max(0, MIN_NARRATIVE_PROFILE_SIGNAL - existing)
            if adjustment:
                components["profile_signal"] = existing + adjustment
                components["editorial_priority"] = int(
                    components.get("editorial_priority", 0)
                ) + adjustment
        components["profile_priority_adjustment"] = adjustment
        item.metadata.setdefault("selection", {})["profile_priority_version"] = (
            PROFILE_PRIORITY_VERSION
        )
        if adjustment:
            score = (components["editorial_priority"], *score[1:])
        return score, components

    setattr(score_with_profile_priority, "_profile_priority_version", PROFILE_PRIORITY_VERSION)
    # ``install_ranked_freshness`` resolves this module global at call time, so
    # replacing it here keeps the profile adjustment active in offline replays
    # that reinstall the base scorer before every run.
    _freshness.score_with_resolved_freshness = score_with_profile_priority
    _ranked._score = score_with_profile_priority


__all__ = [
    "MIN_NARRATIVE_PROFILE_SIGNAL",
    "PROFILE_PRIORITY_VERSION",
    "install_profile_priority",
]
