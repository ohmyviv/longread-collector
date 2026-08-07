from __future__ import annotations

import pytest


_ENV_KEYS = (
    "PIPELINE_ENGINE",
    "V06_WRITE_MODE",
    "V06_SHADOW_ENABLED",
    "V06_PRIMARY_ENABLED",
    "AUTO_PROMOTE_WHEN_READY",
    "EDITOR_0735_CONNECTED",
)


def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_default_runtime_stays_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector import cli

    _clear(monkeypatch)
    assert cli._collector_pipeline_class() is cli.LegacyCollectorPipeline


def test_explicit_shadow_flags_select_sidecar(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector import cli

    _clear(monkeypatch)
    monkeypatch.setenv("PIPELINE_ENGINE", "v06_shadow")
    monkeypatch.setenv("V06_SHADOW_ENABLED", "true")
    monkeypatch.setenv("V06_WRITE_MODE", "events_only")

    pipeline_cls = cli._collector_pipeline_class()
    assert pipeline_cls.__name__ == "ParallelShadowCollectorPipeline"


def test_pr7_still_forbids_primary_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from longread_collector import cli

    _clear(monkeypatch)
    monkeypatch.setenv("PIPELINE_ENGINE", "v06_primary")
    monkeypatch.setenv("V06_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("V06_WRITE_MODE", "primary_cache")

    with pytest.raises(ValueError, match="PR-8"):
        cli._collector_pipeline_class()
