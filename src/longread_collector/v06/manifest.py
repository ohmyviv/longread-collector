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


DEFAULT_V06_MANIFEST = V06Manifest(
    architecture_version="collector-v0.6-pr4",
    schema_version="v06-contracts-v1",
    migration_phase="pr4_policy_portfolio",
    legacy_control_version="collector-v0.5.6m",
    production_behavior_changed=False,
    active_entrypoint_changed=False,
    runtime_config_integrated=False,
    network_requests_added=False,
    primary_cache_enabled=False,
    editor_0735_connected=False,
    auto_promote_when_ready=False,
)


__all__ = ["DEFAULT_V06_MANIFEST", "V06Manifest"]
