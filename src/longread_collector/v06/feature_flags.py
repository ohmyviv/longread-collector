"""Fail-closed feature flags for the v0.6 migration.

PR-0 does not connect this module to the active runtime loader.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, TypeVar


class PipelineEngine(StrEnum):
    LEGACY_V056M = "legacy_v056m"
    V06_SHADOW = "v06_shadow"
    V06_PRIMARY = "v06_primary"


class V06WriteMode(StrEnum):
    EVENTS_ONLY = "events_only"
    SHADOW_TABLES = "shadow_tables"
    PRIMARY_CACHE = "primary_cache"


@dataclass(frozen=True, slots=True)
class V06FeatureFlags:
    pipeline_engine: PipelineEngine = PipelineEngine.LEGACY_V056M
    write_mode: V06WriteMode = V06WriteMode.EVENTS_ONLY
    v06_shadow_enabled: bool = False
    v06_primary_enabled: bool = False
    legacy_v056m_shadow_enabled: bool = False
    auto_promote_when_ready: bool = False
    editor_0735_connected: bool = False

    def validate(self) -> None:
        """Reject unsafe or internally inconsistent migration states."""
        if self.auto_promote_when_ready:
            raise ValueError("v0.6 automatic promotion is forbidden")
        if self.editor_0735_connected:
            raise ValueError("the 07:35 editor must remain disconnected in PR-0")
        if self.pipeline_engine is PipelineEngine.V06_SHADOW and not self.v06_shadow_enabled:
            raise ValueError("v06_shadow engine requires v06_shadow_enabled")
        if self.pipeline_engine is PipelineEngine.V06_PRIMARY:
            if not self.v06_primary_enabled:
                raise ValueError("v06_primary engine requires v06_primary_enabled")
            if self.write_mode is not V06WriteMode.PRIMARY_CACHE:
                raise ValueError("v06_primary engine requires primary_cache write mode")
        if self.write_mode is V06WriteMode.PRIMARY_CACHE and not self.v06_primary_enabled:
            raise ValueError("primary_cache write mode requires v06_primary_enabled")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "V06FeatureFlags":
        """Parse future configuration while preserving fail-closed defaults."""
        flags = cls(
            pipeline_engine=_enum_value(
                PipelineEngine,
                values.get("pipeline_engine"),
                PipelineEngine.LEGACY_V056M,
            ),
            write_mode=_enum_value(
                V06WriteMode,
                values.get("v06_write_mode"),
                V06WriteMode.EVENTS_ONLY,
            ),
            v06_shadow_enabled=_as_bool(values.get("v06_shadow_enabled"), False),
            v06_primary_enabled=_as_bool(values.get("v06_primary_enabled"), False),
            legacy_v056m_shadow_enabled=_as_bool(
                values.get("legacy_v056m_shadow_enabled"), False
            ),
            auto_promote_when_ready=_as_bool(
                values.get("auto_promote_when_ready"), False
            ),
            editor_0735_connected=_as_bool(
                values.get("editor_0735_connected"), False
            ),
        )
        flags.validate()
        return flags


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().upper()
    if normalized in {"TRUE", "1", "YES", "Y"}:
        return True
    if normalized in {"FALSE", "0", "NO", "N"}:
        return False
    return default


TStrEnum = TypeVar("TStrEnum", bound=StrEnum)


def _enum_value(
    enum_type: type[TStrEnum],
    value: Any,
    default: TStrEnum,
) -> TStrEnum:
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default


DEFAULT_V06_FEATURE_FLAGS = V06FeatureFlags()
DEFAULT_V06_FEATURE_FLAGS.validate()


__all__ = [
    "DEFAULT_V06_FEATURE_FLAGS",
    "PipelineEngine",
    "V06FeatureFlags",
    "V06WriteMode",
]
