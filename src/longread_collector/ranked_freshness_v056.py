"""Compatibility alias for the v0.5.6 freshness-aware reserve score."""

from __future__ import annotations

from .ranked_selection_v056c import SELECTION_VERSION

RANKING_FRESHNESS_VERSION = SELECTION_VERSION


def install_ranked_freshness() -> None:
    """Retained for compatibility; ranked_selection_v056c is already active."""


__all__ = ["RANKING_FRESHNESS_VERSION", "install_ranked_freshness"]
