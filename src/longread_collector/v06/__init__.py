"""Longread Collector v0.6 architecture contracts.

Importing this package does not alter the active legacy collector pipeline or
runtime configuration. Legacy compatibility adapters require an explicit
``longread_collector.v06.legacy`` import.
"""

from .contracts import (
    AcquisitionAttempt,
    AcquisitionBundle,
    CanonicalArticle,
    DiscoveryRecord,
    EditorialAssessment,
    Evidence,
    FinalProjection,
    GateDecision,
    RunContext,
    SelectionDecision,
    StageEvent,
    StageEventType,
)
from .feature_flags import (
    DEFAULT_V06_FEATURE_FLAGS,
    PipelineEngine,
    V06FeatureFlags,
    V06WriteMode,
)
from .manifest import DEFAULT_V06_MANIFEST, V06Manifest

__all__ = [
    "AcquisitionAttempt",
    "AcquisitionBundle",
    "CanonicalArticle",
    "DEFAULT_V06_FEATURE_FLAGS",
    "DEFAULT_V06_MANIFEST",
    "DiscoveryRecord",
    "EditorialAssessment",
    "Evidence",
    "FinalProjection",
    "GateDecision",
    "PipelineEngine",
    "RunContext",
    "SelectionDecision",
    "StageEvent",
    "StageEventType",
    "V06FeatureFlags",
    "V06Manifest",
    "V06WriteMode",
]
