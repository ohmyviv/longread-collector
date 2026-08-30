from __future__ import annotations

from longread_collector.freshness_policy_v056f import is_special_document
from longread_collector.normalization import canonicalize_url
from longread_collector import zh_route_shadow_s3_fixed32_v1 as v1
from longread_collector.zh_route_shadow_s3_fixed32_v11 import (
    ROOT_CAUSE,
    S3_VERSION,
    _control_items_raw_runtime_url,
)


def _initium_snapshot_row() -> dict[str, object]:
    return {
        "collector_run_id": "COL-20260828-040117-BJT-zh_evening",
        "query_or_source": "source:initium",
        "source_id": "initium",
        "discovery_method": "sitemap",
        "url": "https://theinitium.com/journal/",
        "url_canonical": "https://theinitium.com/journal",
        "title": "",
        "description": "",
        "published_at": "2026-08-26T12:32:25.000Z",
        "discovered_rank": "24",
        "metadata_json": (
            '{"purpose":"native_source_scan","source_id":"initium",'
            '"source_name":"端传媒","native_method":"sitemap",'
            '"native_endpoint":"https://theinitium.com/sitemap-pages.xml",'
            '"priority_tier":"explore"}'
        ),
    }


def test_v11_identity_and_root_cause_are_explicit() -> None:
    assert S3_VERSION == "zh-route-shadow-s3-jiemian-fixed32-v1.1-raw-url"
    assert ROOT_CAUSE == "offline_replay_reconstruction_raw_url_semantics"


def test_v1_canonical_reconstruction_loses_path_semantics() -> None:
    row = _initium_snapshot_row()
    item = v1._control_items([row], str(row["collector_run_id"]))[0]
    assert item.url == "https://theinitium.com/journal"
    assert is_special_document(item) is False


def test_v11_preserves_runtime_url_but_keeps_canonical_identity() -> None:
    row = _initium_snapshot_row()
    item = _control_items_raw_runtime_url([row], str(row["collector_run_id"]))[0]
    assert item.url == "https://theinitium.com/journal/"
    assert canonicalize_url(item.url) == "https://theinitium.com/journal"
    assert is_special_document(item) is True
    replay = item.metadata["s3_replay"]
    assert replay["runtime_url_preserved"] is True
    assert replay["raw_runtime_url"] == "https://theinitium.com/journal/"
    assert replay["canonical_identity_url"] == "https://theinitium.com/journal"
