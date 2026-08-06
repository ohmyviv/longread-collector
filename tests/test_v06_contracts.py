from dataclasses import FrozenInstanceError

import pytest

from longread_collector.v06.contracts import (
    DiscoveryRecord,
    Evidence,
    StageName,
    TechnicalStatus,
)


def test_v06_stage_contracts_are_frozen() -> None:
    evidence = Evidence(
        evidence_id="e-1",
        evidence_type="title_hint",
        source_stage=StageName.DISCOVERY,
        field="title",
        value="Example",
        confidence=0.8,
    )
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="discovery-v0",
        run_id="run-1",
        item_id="item-1",
        discovery_id="discovery-1",
        url="https://example.com/article",
        title_hint="Example",
        route_status=TechnicalStatus.SUCCESS,
        evidence=(evidence,),
    )

    with pytest.raises(FrozenInstanceError):
        record.title_hint = "mutated"  # type: ignore[misc]


def test_v06_child_collections_are_tuples() -> None:
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="discovery-v0",
        run_id="run-1",
        item_id="item-1",
        discovery_id="discovery-1",
        url="https://example.com/article",
    )
    assert isinstance(record.published_at_hints, tuple)
    assert isinstance(record.evidence, tuple)


def test_v06_nested_metadata_is_deeply_frozen() -> None:
    raw = {"route": {"attempts": ["rss", "html"]}}
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="discovery-v0",
        run_id="run-1",
        item_id="item-1",
        discovery_id="discovery-1",
        url="https://example.com/article",
        raw_metadata=raw,
    )

    raw["route"]["attempts"].append("firecrawl")
    assert record.raw_metadata["route"]["attempts"] == ("rss", "html")

    with pytest.raises(TypeError):
        record.raw_metadata["new"] = "value"  # type: ignore[index]
