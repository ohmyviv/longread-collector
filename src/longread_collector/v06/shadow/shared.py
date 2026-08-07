"""Zero-request sharing of legacy acquisition evidence into the v0.6 shadow."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib

from ..audit.events import make_stage_event
from ..contracts import (
    AcquisitionBundle,
    Evidence,
    FlowStatus,
    GateAction,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)

SHARED_ACQUISITION_VERSION = "shared-control-acquisition-v0.6-pr7"


@dataclass(frozen=True, slots=True)
class SharedAcquisition:
    bundle: AcquisitionBundle
    event: StageEvent
    body_sha256: str
    control_attempt_count: int
    control_request_count: int
    control_firecrawl_request_count: int


def body_fingerprint(bundle: AcquisitionBundle) -> str:
    body = bundle.body_markdown or bundle.body_text or ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _flow_for_gate(action: GateAction) -> FlowStatus:
    if action is GateAction.HARD_REJECT:
        return FlowStatus.REJECT
    if action is GateAction.DEFER:
        return FlowStatus.DEFER
    return FlowStatus.PASS


def share_control_acquisition(
    control: AcquisitionBundle,
    *,
    shadow_item_id: str,
    gate_action: GateAction,
    created_at_bj: str,
    parent_event_id: str,
) -> SharedAcquisition:
    """Copy facts from a completed control acquisition without replaying requests.

    Control attempts remain provenance only. They are deliberately omitted from
    the shadow bundle so StageEvent request metrics cannot double-count network
    traffic already paid for by v0.5.6m.
    """

    control_requests = sum(bool(attempt.request_sent) for attempt in control.attempts)
    control_firecrawl = sum(
        bool(attempt.request_sent) and attempt.extractor.lower() == "firecrawl"
        for attempt in control.attempts
    )
    fingerprint = body_fingerprint(control)
    evidence = (
        Evidence(
            evidence_id=f"{shadow_item_id}-shared-control-body",
            evidence_type="shared_control_acquisition",
            source_stage=StageName.ACQUISITION,
            field="body_sha256",
            value={
                "sha256": fingerprint,
                "control_item_id": control.item_id,
                "control_attempt_count": len(control.attempts),
                "control_request_count": control_requests,
                "control_firecrawl_request_count": control_firecrawl,
                "shadow_request_count": 0,
                "shadow_firecrawl_request_count": 0,
            },
            confidence=1.0,
            extractor=SHARED_ACQUISITION_VERSION,
        ),
    )
    shared = replace(
        control,
        stage_version=SHARED_ACQUISITION_VERSION,
        item_id=shadow_item_id,
        attempts=(),
        best_attempt_id="",
        total_cost=0.0,
        total_latency_ms=0,
        evidence=evidence,
    )
    event = make_stage_event(
        run_id=shared.run_id,
        item_id=shadow_item_id,
        stage=StageName.ACQUISITION,
        event_type=StageEventType.ACQUISITION_RESULT,
        stage_version=SHARED_ACQUISITION_VERSION,
        technical_status=control.status,
        flow_status=_flow_for_gate(gate_action),
        reason_code=(
            "shared_control_evidence"
            if gate_action is GateAction.ACQUIRE
            else f"shared_control_evidence_diagnostic_after_{gate_action.value}"
        ),
        created_at_bj=created_at_bj,
        parent_event_id=parent_event_id,
        attributes={
            "shared_from_control": True,
            "incremental_network_requests": 0,
            "incremental_firecrawl_requests": 0,
            "incremental_cost": 0.0,
            "control_attempt_count": len(control.attempts),
            "control_request_count": control_requests,
            "control_firecrawl_request_count": control_firecrawl,
            "body_sha256": fingerprint,
            "body_chars": shared.content_length,
            "prose_chars": shared.prose_length,
            "gate_action": gate_action.value,
        },
        evidence=evidence,
    )
    return SharedAcquisition(
        bundle=shared,
        event=event,
        body_sha256=fingerprint,
        control_attempt_count=len(control.attempts),
        control_request_count=control_requests,
        control_firecrawl_request_count=control_firecrawl,
    )


__all__ = [
    "SHARED_ACQUISITION_VERSION",
    "SharedAcquisition",
    "body_fingerprint",
    "share_control_acquisition",
]
