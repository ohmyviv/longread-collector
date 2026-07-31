"""Collector v0.5.4 entrypoint with ranked, source-aware URL selection."""

from __future__ import annotations

# Patch the v0.5 module before importing v0.5.3. The latter installs immutable
# recall-snapshot hooks at import time and therefore must capture this ranked
# filter rather than the legacy first-seen filter.
from . import pipeline_v05 as _pipeline_v05
from .ranked_selection import filter_discovered as ranked_filter_discovered

_pipeline_v05.filter_discovered = ranked_filter_discovered

from .pipeline_v051 import NativeCollectorPipeline  # noqa: E402,F401

__all__ = ["NativeCollectorPipeline"]
