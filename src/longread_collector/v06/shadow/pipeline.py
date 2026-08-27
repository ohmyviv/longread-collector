"""Runtime sidecar that keeps v0.5.6m authoritative and runs v0.6 after it."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ...extraction import FallbackBudget
from ...models import DiscoveredURL, ExtractedArticle
from ...pipeline_phase0b import SOURCE_SELECTION_POLICY_VERSION, Phase0BSourceSelectionHook
from ...pipeline_v056f import NativeCollectorPipeline as LegacyV056mPipeline
from ...recall_instrumentation import (
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
)
from ...zh_route_shadow_discovery_v1 import (
    ROUTE_SHADOW_DISCOVERY_VERSION,
    begin_zh_route_shadow,
    current_zh_route_shadow_state,
    end_zh_route_shadow,
    install_paired_zh_route_shadow_discovery,
)
from ...zh_route_shadow_telemetry_v1 import (
    ROUTE_SHADOW_TELEMETRY_VERSION,
    persist_zh_route_shadow_fail_open,
)
from ..contracts import RunContext
from .comparison import PARALLEL_SHADOW_VERSION
from .run_summary_persistence import (
    SHADOW_RUN_SUMMARY_VERSION,
    persist_shadow_run_summary_from_payload_fail_open,
)
from .runner import FullParallelShadowRunner
from .snapshot_persistence_phase0a import (
    SNAPSHOT_PERSISTENCE_VERSION,
    install_snapshot_persistence_invariant,
)

PARALLEL_SHADOW_PIPELINE_VERSION = "collector-v0.6-pr7.3.10"
LEGACY_CONTROL_VERSION = "collector-v0.5.6m"

install_snapshot_persistence_invariant()
install_paired_zh_route_shadow_discovery()


def _env_true(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


class ParallelShadowCollectorPipeline(LegacyV056mPipeline):
    """Run legacy control once, then evaluate v0.6 on the exact same evidence."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._v06_acquired_pairs: list[tuple[DiscoveredURL, ExtractedArticle]] = []
        self._v06_runner = FullParallelShadowRunner()

    async def _extract_batch(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        articles = await super()._extract_batch(discovered, fallback_budget)
        self._v06_acquired_pairs.extend(zip(discovered, articles, strict=True))
        return articles

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        group = str(group_id or "all")
        self._v06_acquired_pairs = []
        snapshot_token = begin_snapshot_capture(group)
        route_shadow_enabled = _env_true("ZH_ROUTE_SHADOW_ENABLED", default=False)
        route_shadow_token = begin_zh_route_shadow(
            enabled=route_shadow_enabled,
            group_id=group,
        )
        snapshot = current_snapshot_capture()
        if snapshot is not None:
            snapshot.snapshot_readback_required = True
        selection_hook = Phase0BSourceSelectionHook(self, group, query_file)
        try:
            with selection_hook:
                legacy_result = await super().collect(
                    group_id=group_id,
                    query_file=query_file,
                )
            selection_audit = selection_hook.audit
            legacy_result["source_selection_policy_version"] = SOURCE_SELECTION_POLICY_VERSION
            legacy_result["source_selection_audit"] = selection_audit
            legacy_result["source_selection_policy_enabled"] = bool(
                selection_audit.get("enabled")
            )
            legacy_result["freshness_sources_selected"] = sum(
                str(item.get("selection_reason", "")) == "freshness_reserve"
                for item in selection_audit.get("selected", ())
                if isinstance(item, dict)
            )

            snapshot = current_snapshot_capture()
            captured = tuple(snapshot.discoveries) if snapshot is not None else ()
            context = RunContext(
                schema_version="v06-contracts-v1",
                run_id=str(legacy_result.get("collector_run_id", "")),
                group_id=group,
                scheduled_at_bj=str(legacy_result.get("scheduled_at_bj", "")),
                started_at_bj=str(legacy_result.get("started_at_bj", "")),
                collector_version=PARALLEL_SHADOW_PIPELINE_VERSION,
                max_acquisition_attempts=int(self.settings.max_urls_per_run),
                firecrawl_daily_limit=int(self.settings.firecrawl_fallback_daily_limit),
            )
            try:
                report = self._v06_runner.run(
                    context,
                    captured_discoveries=captured,
                    acquired_pairs=tuple(self._v06_acquired_pairs),
                    now_bj=datetime.now(self.tz),
                )
                shadow_payload = report.as_dict()
                expected_snapshot_count = int(
                    legacy_result.get("discovery_snapshot_rows") or 0
                )
                persisted_snapshot_count = int(
                    legacy_result.get("discovery_snapshot_persisted_rows") or 0
                )
                snapshot_readback_performed = bool(
                    legacy_result.get("discovery_snapshot_readback_performed", False)
                )
                actual_snapshot_count = int(
                    shadow_payload.get("discovery_snapshot_count") or 0
                )
                capture_gap_count = sum(
                    str(item.get("prefilter_status", ""))
                    == "acquired_without_snapshot_row"
                    for item in shadow_payload.get("items", ())
                    if isinstance(item, dict)
                )
                snapshot_status = str(
                    legacy_result.get("discovery_snapshot_status", "") or ""
                )
                shadow_payload.update(
                    {
                        "pipeline_version": PARALLEL_SHADOW_PIPELINE_VERSION,
                        "control_version": LEGACY_CONTROL_VERSION,
                        "source_selection_policy_version": SOURCE_SELECTION_POLICY_VERSION,
                        "snapshot_persistence_version": SNAPSHOT_PERSISTENCE_VERSION,
                        "snapshot_capture_error": (
                            snapshot.snapshot_error if snapshot is not None else ""
                        ),
                        "control_discovery_snapshot_count": expected_snapshot_count,
                        "persisted_discovery_snapshot_count": persisted_snapshot_count,
                        "snapshot_readback_performed": snapshot_readback_performed,
                        "capture_gap_count": capture_gap_count,
                        "full_snapshot_invariant": (
                            snapshot_status == "success"
                            and snapshot_readback_performed
                            and expected_snapshot_count > 0
                            and persisted_snapshot_count == expected_snapshot_count
                            and actual_snapshot_count == expected_snapshot_count
                            and capture_gap_count == 0
                        ),
                    }
                )
            except Exception as exc:
                shadow_payload = {
                    "version": PARALLEL_SHADOW_VERSION,
                    "pipeline_version": PARALLEL_SHADOW_PIPELINE_VERSION,
                    "control_version": LEGACY_CONTROL_VERSION,
                    "source_selection_policy_version": SOURCE_SELECTION_POLICY_VERSION,
                    "snapshot_persistence_version": SNAPSHOT_PERSISTENCE_VERSION,
                    "status": "failed_open",
                    "error": f"{type(exc).__name__}: {exc}"[:2000],
                    "shadow_request_count": 0,
                    "shadow_firecrawl_request_count": 0,
                    "shadow_incremental_cost": 0.0,
                    "control_result_preserved": True,
                    "full_snapshot_invariant": False,
                }

            # Persist only a compact run-level projection. This happens after
            # Shadow has finished (or failed open), so persistence cannot alter
            # any Gate/Canonical/Editorial/Selection decision. Missing/unready
            # storage is itself an observability failure and remains fail-open.
            summary_persistence = persist_shadow_run_summary_from_payload_fail_open(
                getattr(self, "store", None),
                shadow_payload,
                collector_run_id=context.run_id,
                query_group=group,
                run_started_at_bj=context.started_at_bj,
                completed_at=datetime.now(self.tz),
            )
            shadow_payload["shadow_run_summary_version"] = SHADOW_RUN_SUMMARY_VERSION
            shadow_payload["shadow_run_summary_persisted"] = bool(
                summary_persistence.get("persisted")
            )
            shadow_payload["shadow_run_summary_error"] = str(
                summary_persistence.get("error", "") or ""
            )

            # Chinese route Treatment is a metadata-only sidecar attached to the
            # exact naturally selected Control sources.  Its discovery ran
            # immediately after native Control discovery and before extraction.
            # Durable rows are written only now, after the authoritative Control
            # run returned successfully, so failed Control runs cannot leave
            # promotion-looking route evidence.
            route_state = current_zh_route_shadow_state()
            route_report = route_state.report if route_state is not None else None
            if not route_shadow_enabled:
                route_payload: dict[str, Any] = {
                    "version": ROUTE_SHADOW_DISCOVERY_VERSION,
                    "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
                    "status": "disabled",
                    "control_result_preserved": True,
                    "body_requests": 0,
                }
                route_persistence = {
                    "persisted": False,
                    "error": "disabled",
                    "route_rows": 0,
                    "item_rows": 0,
                }
            elif not group.startswith("zh_"):
                route_payload = {
                    "version": ROUTE_SHADOW_DISCOVERY_VERSION,
                    "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
                    "status": "non_zh_group_skipped",
                    "control_result_preserved": True,
                    "body_requests": 0,
                }
                route_persistence = {
                    "persisted": False,
                    "error": "non_zh_group_skipped",
                    "route_rows": 0,
                    "item_rows": 0,
                }
            elif route_report is not None:
                route_payload = route_report.as_dict()
                route_payload["telemetry_version"] = ROUTE_SHADOW_TELEMETRY_VERSION
                route_payload["control_result_preserved"] = True
                route_persistence = persist_zh_route_shadow_fail_open(
                    getattr(self, "store", None),
                    route_report,
                    collector_run_id=context.run_id,
                    persisted_at=datetime.now(self.tz),
                )
            else:
                route_payload = {
                    "version": ROUTE_SHADOW_DISCOVERY_VERSION,
                    "telemetry_version": ROUTE_SHADOW_TELEMETRY_VERSION,
                    "status": "failed_open" if route_state and route_state.error else "no_report",
                    "error": route_state.error if route_state else "",
                    "control_result_preserved": True,
                    "body_requests": 0,
                }
                route_persistence = {
                    "persisted": False,
                    "error": str(route_payload.get("error") or "no_report"),
                    "route_rows": 0,
                    "item_rows": 0,
                }

            route_payload["telemetry_persisted"] = bool(
                route_persistence.get("persisted")
            )
            route_payload["telemetry_error"] = str(
                route_persistence.get("error", "") or ""
            )
            route_payload["route_rows_persisted"] = int(
                route_persistence.get("route_rows") or 0
            )
            route_payload["item_rows_persisted"] = int(
                route_persistence.get("item_rows") or 0
            )

            legacy_result["v06_shadow"] = shadow_payload
            legacy_result["v06_shadow_version"] = PARALLEL_SHADOW_PIPELINE_VERSION
            legacy_result["v06_shadow_control_version"] = LEGACY_CONTROL_VERSION
            legacy_result[
                "v06_shadow_source_selection_policy_version"
            ] = SOURCE_SELECTION_POLICY_VERSION
            legacy_result[
                "v06_shadow_snapshot_persistence_version"
            ] = SNAPSHOT_PERSISTENCE_VERSION
            legacy_result["v06_shadow_run_summary_version"] = SHADOW_RUN_SUMMARY_VERSION
            legacy_result["v06_shadow_run_summary_persisted"] = bool(
                summary_persistence.get("persisted")
            )
            legacy_result["v06_shadow_run_summary_error"] = str(
                summary_persistence.get("error", "") or ""
            )
            legacy_result["zh_route_shadow"] = route_payload
            legacy_result["zh_route_shadow_enabled"] = route_shadow_enabled
            legacy_result["zh_route_shadow_version"] = ROUTE_SHADOW_DISCOVERY_VERSION
            legacy_result["zh_route_shadow_telemetry_version"] = (
                ROUTE_SHADOW_TELEMETRY_VERSION
            )
            return legacy_result
        finally:
            end_zh_route_shadow(route_shadow_token)
            end_snapshot_capture(snapshot_token)
            self._v06_acquired_pairs = []


__all__ = [
    "LEGACY_CONTROL_VERSION",
    "PARALLEL_SHADOW_PIPELINE_VERSION",
    "ParallelShadowCollectorPipeline",
]
