"""Collector v0.5.1 entrypoint with validated known-source repairs.

The base v0.5 pipeline remains unchanged for auditability. Importing this module
binds the repaired scheduler and discovery implementation before exposing the
same pipeline class.
"""

from . import pipeline_v05 as _pipeline_v05
from .known_source_fixes import (
    KnownFallbackAwareDiscovery,
    select_sources_for_run,
)

_pipeline_v05.NativeSourceDiscovery = KnownFallbackAwareDiscovery
_pipeline_v05.select_sources_for_run = select_sources_for_run

NativeCollectorPipeline = _pipeline_v05.NativeCollectorPipeline
