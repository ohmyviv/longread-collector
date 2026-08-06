"""Longread Collector v0.6 architecture contracts.

PR-0 is intentionally inert: importing this package must not alter the active
legacy collector pipeline or runtime configuration.
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
    "V06FeatureFlags",
    "V06Manifest",
    "V06WriteMode",
]
