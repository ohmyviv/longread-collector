"""Full parallel shadow components for v0.6 PR-7.

The pure runner consumes already-produced legacy discovery and acquisition
facts. The runtime pipeline wrapper is intentionally imported lazily by the CLI
so importing :mod:`longread_collector.v06` still cannot activate legacy code.
"""

from .comparison import PARALLEL_SHADOW_VERSION, ParallelShadowReport
from .runner import FullParallelShadowRunner
from .shared import SHARED_ACQUISITION_VERSION, SharedAcquisition, share_control_acquisition

__all__ = [
    "PARALLEL_SHADOW_VERSION",
    "SHARED_ACQUISITION_VERSION",
    "FullParallelShadowRunner",
    "ParallelShadowReport",
    "SharedAcquisition",
    "share_control_acquisition",
]
