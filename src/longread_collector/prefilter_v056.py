"""Compatibility entrypoint for the active v0.5.6 PR-C prefilter."""

from .prefilter_v055 import discovery_hard_gate_reason
from .prefilter_v056c import PREFILTER_VERSION, filter_discovered

__all__ = [
    "PREFILTER_VERSION",
    "discovery_hard_gate_reason",
    "filter_discovered",
]
