"""Explicit sufficiency-aware Acquisition Service for v0.6 PR-5."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Any
from zoneinfo import ZoneInfo

from ..audit.events import make_stage_event
from ..contracts import (
    AcquisitionAttempt,
    AcquisitionBundle,
    DiscoveryRecord,
    FlowStatus,
    GateAction,
    GateDecision,
    RunContext,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)
from .budget import BudgetDecision, BudgetLedger, BudgetSnapshot
from .sufficiency import SufficiencyDecision, assess_sufficiency
from .types import AcquisitionExtractor, ExtractorPayload


ACQUISITION_SERVICE_VERSION = "acquisition-service-v0.6-pr5"
_BJ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class AcquisitionRun:
    bundle: AcquisitionBundle
    events: tuple[StageEvent, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    payload: ExtractorPayload
    sufficiency: SufficiencyDecision
    attempt: AcquisitionAttempt


class AcquisitionService:
    """Run an explicit extractor chain and stop when more requests add little value."""

    stage_version = ACQUISITION_SERVICE_VERSION

    def __init__(self, extractors: tuple[AcquisitionExtractor, ...]) -> None:
        if not extractors:
            raise ValueError("AcquisitionService requires at least one extractor")
        names = [str(extractor.name).lower() for extractor in extractors]
        if len(names) != len(set(names)):
            raise ValueError("extractor names must be unique")
        self.extractors = extractors

    async def acquire(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        gate: GateDecision,
        ledger: BudgetLedger,
        *,
        parent_event_id: str = "",
    ) -> AcquisitionRun:
        events: list[StageEvent] = []
        candidates: list[_Candidate] = []
        attempts: list[AcquisitionAttempt] = []

        if gate.action is not GateAction.ACQUIRE:
            return _skipped_run(
                context,
                record,
                reason_code=f"gate_{gate.action.value}",
                parent_event_id=parent_event_id,
            )

        item_budget = await ledger.reserve_item(record.item_id)
        if not item_budget.allowed:
            return _skipped_run(
                context,
                record,
                reason_code=item_budget.reason_code,
                parent_event_id=parent_event_id,
            )

        previous_event_id = parent_event_id
        prior_sufficiency: SufficiencyDecision | None = None

        for ordinal, extractor in enumerate(self.extractors, start=1):
            extractor_name = str(extractor.name).lower()
            fallback_reason = _fallback_reason(ordinal, prior_sufficiency)
            expected_information_gain = _expected_information_gain(
                ordinal,
                prior_sufficiency,
            )
            budget_decision: BudgetDecision | None = None

            if extractor_name == "firecrawl":
                budget_decision = await ledger.reserve_firecrawl(context.group_id)
                if not budget_decision.allowed:
                    now = _now_bj()
                    attempt = AcquisitionAttempt(
                        attempt_id=_attempt_id(context.run_id, record.item_id, extractor_name, ordinal),
                        extractor=extractor_name,
                        status=TechnicalStatus.SKIPPED,
                        request_sent=False,
                        started_at_bj=now,
                        completed_at_bj=now,
                        reason_code=budget_decision.reason_code,
                    )
                    attempts.append(attempt)
                    event = _attempt_event(
                        context=context,
                        record=record,
                        attempt=attempt,
                        ordinal=ordinal,
                        parent_event_id=previous_event_id,
                        request_outcome=budget_decision.reason_code,
                        fallback_reason=fallback_reason,
                        expected_information_gain=expected_information_gain,
                        budget_decision=budget_decision,
                    )
                    events.append(event)
                    previous_event_id = event.event_id
                    break

            started_at = _now_bj()
            try:
                payload = await extractor.extract(record)
                completed_at = _now_bj()
                sufficiency = assess_sufficiency(record, payload)
                attempt = AcquisitionAttempt(
                    attempt_id=_attempt_id(context.run_id, record.item_id, extractor_name, ordinal),
                    extractor=extractor_name,
                    status=TechnicalStatus.SUCCESS if payload.body else TechnicalStatus.PARTIAL,
                    request_sent=True,
                    started_at_bj=started_at,
                    completed_at_bj=completed_at,
                    body_chars=len(payload.body),
                    prose_chars=sufficiency.prose_chars,
                    credits_used=float(payload.credits_used or 0.0),
                    latency_ms=int(payload.latency_ms or 0),
                    reason_code=sufficiency.reason_code,
                    evidence=sufficiency.evidence,
                )
                attempts.append(attempt)
                candidate = _Candidate(payload, sufficiency, attempt)
                candidates.append(candidate)
                event = _attempt_event(
                    context=context,
                    record=record,
                    attempt=attempt,
                    ordinal=ordinal,
                    parent_event_id=previous_event_id,
                    request_outcome="request_succeeded",
                    fallback_reason=fallback_reason,
                    expected_information_gain=expected_information_gain,
                    budget_decision=budget_decision,
                    payload=payload,
                    sufficiency=sufficiency,
                )
                events.append(event)
                previous_event_id = event.event_id
                prior_sufficiency = sufficiency
                if sufficiency.should_stop:
                    break
            except Exception as exc:  # extractor failures are stage data, not control-flow leaks
                completed_at = _now_bj()
                attempt = AcquisitionAttempt(
                    attempt_id=_attempt_id(context.run_id, record.item_id, extractor_name, ordinal),
                    extractor=extractor_name,
                    status=TechnicalStatus.FAILED,
                    request_sent=True,
                    started_at_bj=started_at,
                    completed_at_bj=completed_at,
                    reason_code="request_failed",
                    error_type=type(exc).__name__,
                )
                attempts.append(attempt)
                event = _attempt_event(
                    context=context,
                    record=record,
                    attempt=attempt,
                    ordinal=ordinal,
                    parent_event_id=previous_event_id,
                    request_outcome="request_failed",
                    fallback_reason=fallback_reason,
                    expected_information_gain=expected_information_gain,
                    budget_decision=budget_decision,
                    error_message=str(exc)[:500],
                )
                events.append(event)
                previous_event_id = event.event_id
                prior_sufficiency = None

        best = max(candidates, key=_candidate_score, default=None)
        bundle = _bundle_from_best(context, record, attempts, best)
        result_event = make_stage_event(
            run_id=context.run_id,
            item_id=record.item_id,
            stage=StageName.ACQUISITION,
            event_type=StageEventType.ACQUISITION_RESULT,
            stage_version=ACQUISITION_SERVICE_VERSION,
            technical_status=bundle.status,
            flow_status=(
                FlowStatus.PASS
                if bundle.status is TechnicalStatus.SUCCESS
                else FlowStatus.DEFER
                if bundle.status is TechnicalStatus.PARTIAL
                else FlowStatus.ERROR
            ),
            reason_code=_bundle_reason(bundle),
            created_at_bj=_now_bj(),
            parent_event_id=previous_event_id,
            ordinal=0,
            cost=0.0,
            attributes={
                "extraction_status": (
                    "success"
                    if bundle.status is TechnicalStatus.SUCCESS
                    else "partial"
                    if bundle.status is TechnicalStatus.PARTIAL
                    else "failed"
                ),
                "best_extractor": _best_extractor(bundle),
                "best_attempt_id": bundle.best_attempt_id,
                "attempt_count": len(bundle.attempts),
                "sufficient_for_canonicalization": bundle.sufficient_for_canonicalization,
                "sufficient_for_editorial_judgment": bundle.sufficient_for_editorial_judgment,
                "sufficient_for_source_chase": bundle.sufficient_for_source_chase,
                "total_cost": bundle.total_cost,
                "total_latency_ms": bundle.total_latency_ms,
            },
            evidence=bundle.evidence,
        )
        events.append(result_event)
        return AcquisitionRun(bundle=bundle, events=tuple(events))


def _candidate_score(candidate: _Candidate) -> tuple[int, int, int, int, int, int]:
    payload = candidate.payload
    suff = candidate.sufficiency
    metadata_score = sum(bool(value) for value in (payload.title, payload.author, payload.published_at))
    return (
        int(suff.editorial_judgment),
        int(suff.source_chase),
        int(suff.canonicalization),
        metadata_score,
        suff.prose_chars,
        len(payload.body),
    )


def _bundle_from_best(
    context: RunContext,
    record: DiscoveryRecord,
    attempts: list[AcquisitionAttempt],
    best: _Candidate | None,
) -> AcquisitionBundle:
    total_cost = round(sum(float(item.credits_used or 0.0) for item in attempts), 6)
    total_latency = sum(max(0, int(item.latency_ms or 0)) for item in attempts)
    if best is None:
        return AcquisitionBundle(
            schema_version=context.schema_version,
            stage_version=ACQUISITION_SERVICE_VERSION,
            run_id=context.run_id,
            item_id=record.item_id,
            status=TechnicalStatus.FAILED,
            attempts=tuple(attempts),
            total_cost=total_cost,
            total_latency_ms=total_latency,
        )

    payload = best.payload
    suff = best.sufficiency
    status = (
        TechnicalStatus.SUCCESS
        if suff.canonicalization and (suff.editorial_judgment or suff.source_chase)
        else TechnicalStatus.PARTIAL
        if payload.body or suff.canonicalization
        else TechnicalStatus.FAILED
    )
    metadata = payload.metadata
    template_length = _safe_int(metadata.get("template_length"))
    image_count = _safe_int(metadata.get("image_count"))
    video_count = _safe_int(metadata.get("video_count"))
    return AcquisitionBundle(
        schema_version=context.schema_version,
        stage_version=ACQUISITION_SERVICE_VERSION,
        run_id=context.run_id,
        item_id=record.item_id,
        status=status,
        attempts=tuple(attempts),
        best_attempt_id=best.attempt.attempt_id,
        body_text=payload.text or payload.markdown,
        body_markdown=payload.markdown or payload.text,
        raw_title=payload.title or record.title_hint,
        raw_author=payload.author,
        raw_dates=tuple(value for value in (payload.published_at, *record.published_at_hints) if value),
        raw_canonical_links=payload.canonical_links,
        outbound_links=payload.outbound_links,
        content_length=len(payload.body),
        prose_length=suff.prose_chars,
        template_length=template_length,
        image_count=image_count,
        video_count=video_count,
        sufficient_for_canonicalization=suff.canonicalization,
        sufficient_for_editorial_judgment=suff.editorial_judgment,
        sufficient_for_source_chase=suff.source_chase,
        total_cost=total_cost,
        total_latency_ms=total_latency,
        evidence=suff.evidence,
    )


def _skipped_run(
    context: RunContext,
    record: DiscoveryRecord,
    *,
    reason_code: str,
    parent_event_id: str,
) -> AcquisitionRun:
    bundle = AcquisitionBundle(
        schema_version=context.schema_version,
        stage_version=ACQUISITION_SERVICE_VERSION,
        run_id=context.run_id,
        item_id=record.item_id,
        status=TechnicalStatus.SKIPPED,
    )
    event = make_stage_event(
        run_id=context.run_id,
        item_id=record.item_id,
        stage=StageName.ACQUISITION,
        event_type=StageEventType.ACQUISITION_RESULT,
        stage_version=ACQUISITION_SERVICE_VERSION,
        technical_status=TechnicalStatus.SKIPPED,
        flow_status=FlowStatus.DEFER,
        reason_code=reason_code,
        created_at_bj=_now_bj(),
        parent_event_id=parent_event_id,
        attributes={"extraction_status": "skipped", "best_extractor": ""},
    )
    return AcquisitionRun(bundle=bundle, events=(event,))


def _attempt_event(
    *,
    context: RunContext,
    record: DiscoveryRecord,
    attempt: AcquisitionAttempt,
    ordinal: int,
    parent_event_id: str,
    request_outcome: str,
    fallback_reason: str,
    expected_information_gain: float,
    budget_decision: BudgetDecision | None,
    payload: ExtractorPayload | None = None,
    sufficiency: SufficiencyDecision | None = None,
    error_message: str = "",
) -> StageEvent:
    before = budget_decision.before if budget_decision else None
    after = budget_decision.after if budget_decision else None
    attrs: dict[str, Any] = {
        "extractor": attempt.extractor,
        "request_sent": attempt.request_sent,
        "request_outcome": request_outcome,
        "body_chars": attempt.body_chars,
        "prose_chars": attempt.prose_chars,
        "latency_ms": attempt.latency_ms,
        "credits_used": attempt.credits_used,
        "fallback_reason": fallback_reason,
        "expected_information_gain": round(float(expected_information_gain), 3),
        "budget_before": _budget_dict(before),
        "budget_after": _budget_dict(after),
    }
    if payload is not None:
        attrs["http_status"] = payload.http_status
    if sufficiency is not None:
        attrs.update(
            {
                "sufficient_for_canonicalization": sufficiency.canonicalization,
                "sufficient_for_editorial_judgment": sufficiency.editorial_judgment,
                "sufficient_for_source_chase": sufficiency.source_chase,
                "stop_reason": sufficiency.reason_code,
            }
        )
    if error_message:
        attrs["error_message"] = error_message

    return make_stage_event(
        run_id=context.run_id,
        item_id=record.item_id,
        stage=StageName.ACQUISITION,
        event_type=StageEventType.EXTRACTOR_ATTEMPT,
        stage_version=ACQUISITION_SERVICE_VERSION,
        technical_status=attempt.status,
        flow_status=(
            FlowStatus.PASS
            if request_outcome == "request_succeeded"
            else FlowStatus.DEFER
            if request_outcome.startswith("skipped_")
            else FlowStatus.ERROR
        ),
        reason_code=request_outcome,
        created_at_bj=attempt.completed_at_bj or _now_bj(),
        parent_event_id=parent_event_id,
        ordinal=ordinal,
        cost=float(attempt.credits_used or 0.0),
        attributes=attrs,
        evidence=attempt.evidence,
    )


def _fallback_reason(ordinal: int, prior: SufficiencyDecision | None) -> str:
    if ordinal == 1:
        return "initial_acquisition"
    if prior is None:
        return "prior_extractor_failed"
    return prior.reason_code


def _expected_information_gain(ordinal: int, prior: SufficiencyDecision | None) -> float:
    if ordinal == 1:
        return 1.0
    if prior is None:
        return 0.90
    if not prior.canonicalization:
        return 0.90
    if prior.source_chase or prior.editorial_judgment:
        return 0.0
    return 0.65


def _bundle_reason(bundle: AcquisitionBundle) -> str:
    if bundle.sufficient_for_editorial_judgment:
        return "sufficient_for_editorial_judgment"
    if bundle.sufficient_for_source_chase:
        return "sufficient_for_source_chase"
    if bundle.sufficient_for_canonicalization:
        return "partial_canonical_evidence"
    if bundle.content_length:
        return "partial_body_insufficient"
    return "acquisition_failed"


def _best_extractor(bundle: AcquisitionBundle) -> str:
    for attempt in bundle.attempts:
        if attempt.attempt_id == bundle.best_attempt_id:
            return attempt.extractor
    return ""


def _attempt_id(run_id: str, item_id: str, extractor: str, ordinal: int) -> str:
    seed = f"{run_id}|{item_id}|{extractor}|{ordinal}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _now_bj() -> str:
    return datetime.now(_BJ).isoformat(timespec="seconds")


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _budget_dict(value: BudgetSnapshot | None) -> dict[str, Any]:
    if value is None:
        return {}
    return {
        "acquisition_items_started": value.acquisition_items_started,
        "acquisition_item_limit": value.acquisition_item_limit,
        "firecrawl_requests_reserved": value.firecrawl_requests_reserved,
        "firecrawl_daily_limit": value.firecrawl_daily_limit,
        "firecrawl_group_reserved": dict(value.firecrawl_group_reserved),
        "firecrawl_group_limits": dict(value.firecrawl_group_limits),
    }


__all__ = ["ACQUISITION_SERVICE_VERSION", "AcquisitionRun", "AcquisitionService"]
