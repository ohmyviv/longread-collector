"""Runtime sidecar that keeps v0.5.6m authoritative and runs v0.6 after it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...extraction import FallbackBudget
from ...models import DiscoveredURL, ExtractedArticle
from ...pipeline_v056f import NativeCollectorPipeline as LegacyV056mPipeline
from ...recall_instrumentation import (
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
)
from ..contracts import RunContext
from .comparison import PARALLEL_SHADOW_VERSION
from .runner import FullParallelShadowRunner

PARALLEL_SHADOW_PIPELINE_VERSION = "collector-v0.6-pr7"
LEGACY_CONTROL_VERSION = "collector-v0.5.6m"


class ParallelShadowCollectorPipeline(LegacyV056mPipeline):
    """Run legacy control once, then evaluate v0.6 on the exact same evidence.

    The sidecar never calls a discovery or acquisition client itself. Shadow
    failures are returned as diagnostic data and cannot fail a successful legacy
    collection run.
    """

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
        try:
            legacy_result = await super().collect(group_id=group_id, query_file=query_file)
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
                shadow_payload.update(
                    {
                        "pipeline_version": PARALLEL_SHADOW_PIPELINE_VERSION,
                        "control_version": LEGACY_CONTROL_VERSION,
                        "snapshot_capture_error": (
                            snapshot.snapshot_error if snapshot is not None else ""
                        ),
                    }
                )
            except Exception as exc:  # shadow must never take down control
                shadow_payload = {
                    "version": PARALLEL_SHADOW_VERSION,
                    "pipeline_version": PARALLEL_SHADOW_PIPELINE_VERSION,
                    "control_version": LEGACY_CONTROL_VERSION,
                    "status": "failed_open",
                    "error": f"{type(exc).__name__}: {exc}"[:2000],
                    "shadow_request_count": 0,
                    "shadow_firecrawl_request_count": 0,
                    "shadow_incremental_cost": 0.0,
                    "control_result_preserved": True,
                }
            legacy_result["v06_shadow"] = shadow_payload
            legacy_result["v06_shadow_version"] = PARALLEL_SHADOW_PIPELINE_VERSION
            legacy_result["v06_shadow_control_version"] = LEGACY_CONTROL_VERSION
            return legacy_result
        finally:
            end_snapshot_capture(snapshot_token)
            self._v06_acquired_pairs = []


__all__ = [
    "LEGACY_CONTROL_VERSION",
    "PARALLEL_SHADOW_PIPELINE_VERSION",
    "ParallelShadowCollectorPipeline",
]
