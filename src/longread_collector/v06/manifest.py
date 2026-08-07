"""Migration manifest for the v0.6 architecture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class V06Manifest:
    architecture_version: str
    schema_version: str
    migration_phase: str
    legacy_control_version: str
    production_behavior_changed: bool
    active_entrypoint_changed: bool
    runtime_config_integrated: bool
    network_requests_added: bool
    primary_cache_enabled: bool
    editor_0735_connected: bool
    auto_promote_when_ready: bool
    shadow_runtime_integrated: bool = False
    shadow_entrypoint_wrapped: bool = False
    shadow_artifact_enabled: bool = False


DEFAULT_V06_MANIFEST = V06Manifest(
    architecture_version="collector-v0.6-pr7",
    schema_version="v06-contracts-v1",
    migration_phase="pr7_full_parallel_shadow",
    legacy_control_version="collector-v0.5.6m",
    # These three fields describe production authority. The authoritative
    # collector remains v0.5.6m; PR-7 only activates a fail-open sidecar.
    production_behavior_changed=False,
    active_entrypoint_changed=False,
    runtime_config_integrated=False,
    network_requests_added=False,
    primary_cache_enabled=False,
    editor_0735_connected=False,
    auto_promote_when_ready=False,
    # Shadow-only runtime integration is tracked separately so the production
    # safety contract stays semantically stable through the migration.
    shadow_runtime_integrated=True,
    shadow_entrypoint_wrapped=True,
    shadow_artifact_enabled=True,
)


__all__ = ["DEFAULT_V06_MANIFEST", "V06Manifest"]
