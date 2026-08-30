"""S3 fixed-32 replay v1.1 with raw-runtime URL preservation.

v1 remains immutable evidence.  v1.1 changes only Control reconstruction:
selection semantics operate on the persisted raw discovery URL, while canonical
URLs remain identity/dedup/comparison keys.  All frozen cohort, scoring, caps,
thresholds and staged-reserve semantics are inherited unchanged from v1.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Mapping

from . import offline_replay_v056 as replay_base
from . import zh_route_shadow_s3_fixed32_v1 as v1
from .models import DiscoveredURL

S3_VERSION = "zh-route-shadow-s3-jiemian-fixed32-v1.1-raw-url"
ROOT_CAUSE = "offline_replay_reconstruction_raw_url_semantics"

FROZEN_RUN_IDS = v1.FROZEN_RUN_IDS
FROZEN_SOURCE_ID = v1.FROZEN_SOURCE_ID
FROZEN_PLAUSIBLE_COUNT = v1.FROZEN_PLAUSIBLE_COUNT
MAX_ATTEMPTS = v1.MAX_ATTEMPTS

STATUS_NO_EFFECT = v1.STATUS_NO_EFFECT
STATUS_COMPLETE = v1.STATUS_COMPLETE
STATUS_NEEDS_EVIDENCE = v1.STATUS_NEEDS_EVIDENCE
STATUS_CONTROL_MISMATCH = v1.STATUS_CONTROL_MISMATCH


def _control_items_raw_runtime_url(
    rows: Iterable[Mapping[str, Any]], run_id: str
) -> list[DiscoveredURL]:
    """Reconstruct Control with the exact persisted runtime URL representation.

    ``url`` is the discovery/runtime URL. ``url_canonical`` is an identity key.
    The v1 replay passed the canonical form into URL-sensitive page/freshness
    policy, which is not semantics-preserving for every path shape.
    """
    items: list[DiscoveredURL] = []
    for raw in rows:
        row = v1._normalize_snapshot_row(raw)
        if row["run_id"] != run_id:
            continue
        runtime_url = v1._text(raw.get("url") or raw.get("original_url"))
        canonical_url = v1._text(raw.get("url_canonical"))
        reconstructed = dict(row)
        reconstructed["url_canonical"] = runtime_url or canonical_url
        reconstructed["url"] = runtime_url or canonical_url
        item = replay_base._snapshot_item(reconstructed)
        item.metadata.setdefault("s3_replay", {}).update(
            {
                "version": S3_VERSION,
                "runtime_url_preserved": bool(runtime_url),
                "raw_runtime_url": runtime_url,
                "canonical_identity_url": v1._canonical(canonical_url or runtime_url),
                "root_cause_correction": ROOT_CAUSE,
            }
        )
        items.append(item)
    return items


@contextmanager
def _install_v11_reconstruction() -> Iterator[None]:
    original_control_items = v1._control_items
    original_version = v1.S3_VERSION
    v1._control_items = _control_items_raw_runtime_url
    v1.S3_VERSION = S3_VERSION
    try:
        yield
    finally:
        v1._control_items = original_control_items
        v1.S3_VERSION = original_version


def replay_control_run(
    *, run_id: str, snapshot_rows: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    with _install_v11_reconstruction():
        result = v1.replay_control_run(run_id=run_id, snapshot_rows=snapshot_rows)
    result["version"] = S3_VERSION
    result["reconstruction"] = ROOT_CAUSE
    return result


def replay_s3_run(
    *,
    run_id: str,
    snapshot_rows: Iterable[Mapping[str, Any]],
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    with _install_v11_reconstruction():
        result = v1.replay_s3_run(
            run_id=run_id,
            snapshot_rows=snapshot_rows,
            route_rows=route_rows,
            cohort_rows=cohort_rows,
            reviewed_rows=reviewed_rows,
        )
    result["version"] = S3_VERSION
    result["reconstruction"] = ROOT_CAUSE
    return result


def replay_s3_cohort(
    *,
    snapshot_rows: Iterable[Mapping[str, Any]],
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    snapshot = list(snapshot_rows)
    route = list(route_rows)
    cohort = list(cohort_rows)
    reviewed = list(reviewed_rows)
    with _install_v11_reconstruction():
        result = v1.replay_s3_cohort(
            snapshot_rows=snapshot,
            route_rows=route,
            cohort_rows=cohort,
            reviewed_rows=reviewed,
        )
    result["version"] = S3_VERSION
    result["reconstruction"] = ROOT_CAUSE
    result["v1_result_preserved"] = "NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH"
    return result


__all__ = [
    "FROZEN_PLAUSIBLE_COUNT",
    "FROZEN_RUN_IDS",
    "FROZEN_SOURCE_ID",
    "MAX_ATTEMPTS",
    "ROOT_CAUSE",
    "S3_VERSION",
    "STATUS_COMPLETE",
    "STATUS_CONTROL_MISMATCH",
    "STATUS_NEEDS_EVIDENCE",
    "STATUS_NO_EFFECT",
    "replay_control_run",
    "replay_s3_cohort",
    "replay_s3_run",
]
