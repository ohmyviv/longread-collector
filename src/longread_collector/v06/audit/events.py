"""Deterministic StageEvent construction for v0.6 audit streams."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from ..contracts import (
    Evidence,
    FlowStatus,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)

STAGE_EVENT_SCHEMA_VERSION = "v06-stage-events-v1"


def deterministic_event_id(
    *,
    run_id: str,
    item_id: str,
    event_type: StageEventType,
    ordinal: int = 0,
) -> str:
    seed = f"{run_id}|{item_id}|{event_type.value}|{int(ordinal)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def make_stage_event(
    *,
    run_id: str,
    item_id: str,
    stage: StageName,
    event_type: StageEventType,
    stage_version: str,
    technical_status: TechnicalStatus,
    flow_status: FlowStatus,
    reason_code: str,
    created_at_bj: str,
    parent_event_id: str = "",
    ordinal: int = 0,
    cost: float = 0.0,
    attributes: Mapping[str, Any] | None = None,
    evidence: tuple[Evidence, ...] = (),
) -> StageEvent:
    return StageEvent(
        schema_version=STAGE_EVENT_SCHEMA_VERSION,
        event_id=deterministic_event_id(
            run_id=run_id,
            item_id=item_id,
            event_type=event_type,
            ordinal=ordinal,
        ),
        run_id=run_id,
        item_id=item_id,
        stage=stage,
        event_type=event_type,
        stage_version=stage_version,
        technical_status=technical_status,
        flow_status=flow_status,
        reason_code=reason_code,
        created_at_bj=created_at_bj,
        parent_event_id=parent_event_id,
        cost=float(cost or 0.0),
        attributes=attributes or {},
        evidence=evidence,
    )


__all__ = [
    "STAGE_EVENT_SCHEMA_VERSION",
    "deterministic_event_id",
    "make_stage_event",
]
