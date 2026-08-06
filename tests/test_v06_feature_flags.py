import pytest

from longread_collector.v06.feature_flags import (
    DEFAULT_V06_FEATURE_FLAGS,
    PipelineEngine,
    V06FeatureFlags,
    V06WriteMode,
)


def test_pr0_defaults_are_fail_closed() -> None:
    flags = DEFAULT_V06_FEATURE_FLAGS
    assert flags.pipeline_engine is PipelineEngine.LEGACY_V056M
    assert flags.write_mode is V06WriteMode.EVENTS_ONLY
    assert flags.v06_shadow_enabled is False
    assert flags.v06_primary_enabled is False
    assert flags.auto_promote_when_ready is False
    assert flags.editor_0735_connected is False


@pytest.mark.parametrize(
    "flags",
    [
        V06FeatureFlags(auto_promote_when_ready=True),
        V06FeatureFlags(editor_0735_connected=True),
        V06FeatureFlags(pipeline_engine=PipelineEngine.V06_SHADOW),
        V06FeatureFlags(
            pipeline_engine=PipelineEngine.V06_PRIMARY,
            v06_primary_enabled=True,
            write_mode=V06WriteMode.EVENTS_ONLY,
        ),
        V06FeatureFlags(write_mode=V06WriteMode.PRIMARY_CACHE),
    ],
)
def test_unsafe_states_are_rejected(flags: V06FeatureFlags) -> None:
    with pytest.raises(ValueError):
        flags.validate()


def test_future_shadow_state_can_be_parsed_explicitly() -> None:
    flags = V06FeatureFlags.from_mapping(
        {
            "pipeline_engine": "v06_shadow",
            "v06_write_mode": "shadow_tables",
            "v06_shadow_enabled": "TRUE",
        }
    )
    assert flags.pipeline_engine is PipelineEngine.V06_SHADOW
    assert flags.write_mode is V06WriteMode.SHADOW_TABLES
    assert flags.v06_shadow_enabled is True
