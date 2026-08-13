from __future__ import annotations

import asyncio
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from longread_collector.models import DiscoveredURL
from longread_collector.recall_instrumentation import (
    CapturedDiscovery,
    begin_snapshot_capture,
    current_snapshot_capture,
    end_snapshot_capture,
)


def _captured(index: int) -> CapturedDiscovery:
    return CapturedDiscovery(
        item=DiscoveredURL(
            url=f"https://example.com/story/{index}",
            title=f"Story {index}",
            discovery_method="rss",
        ),
        prefilter_status=(
            "accepted_for_extraction" if index == 1 else "not_selected_capacity"
        ),
        prefilter_reject_reason=("" if index == 1 else "source_initial_cap_reserve"),
    )


def test_same_group_nested_snapshot_capture_reuses_outer_state() -> None:
    outer = begin_snapshot_capture("pre_report")
    try:
        outer_state = current_snapshot_capture()
        assert outer_state is not None

        inner = begin_snapshot_capture("pre_report")
        try:
            assert current_snapshot_capture() is outer_state
            outer_state.discoveries.extend((_captured(1), _captured(2), _captured(3)))
        finally:
            end_snapshot_capture(inner)

        assert current_snapshot_capture() is outer_state
        assert len(outer_state.discoveries) == 3
    finally:
        end_snapshot_capture(outer)

    assert current_snapshot_capture() is None


def test_different_group_nested_snapshot_capture_remains_isolated() -> None:
    outer = begin_snapshot_capture("pre_report")
    try:
        outer_state = current_snapshot_capture()
        assert outer_state is not None
        outer_state.discoveries.append(_captured(1))

        inner = begin_snapshot_capture("zh_midday")
        try:
            inner_state = current_snapshot_capture()
            assert inner_state is not None
            assert inner_state is not outer_state
            assert inner_state.discoveries == []
            inner_state.discoveries.append(_captured(2))
        finally:
            end_snapshot_capture(inner)

        assert current_snapshot_capture() is outer_state
        assert len(outer_state.discoveries) == 1
    finally:
        end_snapshot_capture(outer)


class _FakeReport:
    def __init__(self, captured_count: int) -> None:
        self.captured_count = captured_count

    def as_dict(self) -> dict[str, object]:
        return {
            "version": "full-parallel-shadow-v0.6-pr7",
            "status": "success",
            "discovery_snapshot_count": self.captured_count,
            "items": [
                {
                    "prefilter_status": "accepted_for_extraction"
                    if index == 0
                    else "not_selected_capacity"
                }
                for index in range(self.captured_count)
            ],
            "shadow_request_count": 0,
            "shadow_firecrawl_request_count": 0,
            "shadow_incremental_cost": 0.0,
            "body_fingerprint_mismatches": 0,
        }


class _FakeRunner:
    def __init__(self) -> None:
        self.captured_count = -1

    def run(self, context, *, captured_discoveries, acquired_pairs, now_bj):
        self.captured_count = len(tuple(captured_discoveries))
        return _FakeReport(self.captured_count)


def test_sidecar_observes_inner_legacy_full_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector import pipeline_v056f
    from longread_collector.v06.shadow.pipeline import ParallelShadowCollectorPipeline

    async def fake_control_collect(self, group_id=None, query_file=None):
        token = begin_snapshot_capture(str(group_id or "all"))
        try:
            state = current_snapshot_capture()
            assert state is not None
            state.discoveries.extend((_captured(1), _captured(2), _captured(3)))
            return {
                "collector_run_id": "COL-PR7-FULL-SNAPSHOT",
                "started_at_bj": "2026-08-08 04:25:10",
                "scheduled_at_bj": "2026-08-08 03:57:00",
                "final_status": "success",
                "discovery_snapshot_rows": 3,
                "discovery_snapshot_persisted_rows": 3,
                "discovery_snapshot_readback_performed": True,
                "discovery_snapshot_status": "success",
            }
        finally:
            end_snapshot_capture(token)

    monkeypatch.setattr(
        pipeline_v056f.NativeCollectorPipeline,
        "collect",
        fake_control_collect,
    )

    pipeline = ParallelShadowCollectorPipeline.__new__(ParallelShadowCollectorPipeline)
    pipeline.settings = SimpleNamespace(
        max_urls_per_run=32,
        firecrawl_fallback_daily_limit=3,
    )
    pipeline.tz = ZoneInfo("Asia/Shanghai")
    pipeline._v06_acquired_pairs = []
    runner = _FakeRunner()
    pipeline._v06_runner = runner

    result = asyncio.run(pipeline.collect(group_id="pre_report"))
    shadow = result["v06_shadow"]

    assert runner.captured_count == 3
    assert shadow["discovery_snapshot_count"] == 3
    assert shadow["control_discovery_snapshot_count"] == 3
    assert shadow["persisted_discovery_snapshot_count"] == 3
    assert shadow["snapshot_readback_performed"] is True
    assert shadow["capture_gap_count"] == 0
    assert shadow["full_snapshot_invariant"] is True


def test_snapshot_count_mismatch_cannot_pass_integrity(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector import pipeline_v056f
    from longread_collector.v06.shadow.pipeline import ParallelShadowCollectorPipeline

    async def fake_control_collect(self, group_id=None, query_file=None):
        return {
            "collector_run_id": "COL-PR7-MISMATCH",
            "started_at_bj": "2026-08-08 04:25:10",
            "scheduled_at_bj": "2026-08-08 03:57:00",
            "final_status": "success",
            "discovery_snapshot_rows": 4,
            "discovery_snapshot_persisted_rows": 4,
            "discovery_snapshot_readback_performed": True,
            "discovery_snapshot_status": "success",
        }

    monkeypatch.setattr(
        pipeline_v056f.NativeCollectorPipeline,
        "collect",
        fake_control_collect,
    )

    pipeline = ParallelShadowCollectorPipeline.__new__(ParallelShadowCollectorPipeline)
    pipeline.settings = SimpleNamespace(
        max_urls_per_run=32,
        firecrawl_fallback_daily_limit=3,
    )
    pipeline.tz = ZoneInfo("Asia/Shanghai")
    pipeline._v06_acquired_pairs = []
    pipeline._v06_runner = _FakeRunner()

    result = asyncio.run(pipeline.collect(group_id="pre_report"))
    assert result["v06_shadow"]["discovery_snapshot_count"] == 0
    assert result["v06_shadow"]["control_discovery_snapshot_count"] == 4
    assert result["v06_shadow"]["persisted_discovery_snapshot_count"] == 4
    assert result["v06_shadow"]["full_snapshot_invariant"] is False
