"""Explicit legacy compatibility adapters.

Importing this package loads legacy models by design. The v0.6 root package does
not import it, preserving the PR-0 import-isolation boundary.
"""

from .adapter_v0731 import (
    LEGACY_ADAPTER_VERSION,
    PUBLICATION_EVIDENCE_BRIDGE_VERSION,
    LegacyAdaptedItem,
    LegacyAdaptedRun,
    LegacyV056mAdapter,
)

__all__ = [
    "LEGACY_ADAPTER_VERSION",
    "PUBLICATION_EVIDENCE_BRIDGE_VERSION",
    "LegacyAdaptedItem",
    "LegacyAdaptedRun",
    "LegacyV056mAdapter",
]
