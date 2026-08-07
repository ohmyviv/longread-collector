"""Run v0.6 deterministically on discovery/body evidence produced by control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from ...normalization import canonicalize_url
from ..audit.events import make_stage_event
from ..canonical import CanonicalArticleResolver
from ..contracts import (
    CanonicalArticle,
    EditorialAssessment,
    FlowStatus,
    GateAction,
    GateDecision,
    PolicyAction,
    RunContext,
    SelectionDecision,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)
from ..discovery import DiscoveryAdapter
from ..editorial import EditorialJudge
from ..gates import AcquisitionGateService, GateContext
from ..legacy import LegacyAdaptedItem, LegacyV056mAdapter
from ..selection import PolicyPortfolioSelector, SelectionCandidate
from .comparison import ParallelShadowReport, ShadowItemComparison, difference_tags
from .shared import SharedAcquisition, body_fingerprint, share_control_acquisition

FULL_PARALLEL_RUNNER_VERSION = "parallel-shadow-runner-v0.6-pr7"


@dataclass(slots=True)
class _Entry:
    record: Any
    gate: GateDecision
    prefilter_status: str
    prefilter_reason: str
    gate_event: StageEvent
    control_discovered: Any
    control_article: Any | None = None
    legacy: LegacyAdaptedItem | None = None
    shared: SharedAcquisition | None = None
    canonical: CanonicalArticle | None = None
    editorial: EditorialAssessment | None = None
    canonical_event: StageEvent | None = None
    editorial_event: StageEvent | None = None


class FullParallelShadowRunner:
    """Evaluate v0.6 without discovery or extraction I/O.

    The full discovery snapshot receives Discovery + Gate decisions. Only items
    for which the legacy control already acquired a body continue through the
    diagnostic Canonical/Editorial path. Effective portfolio selection uses the
    subset whose v0.6 Gate action is ACQUIRE and whose body is therefore already
    observable at zero incremental request cost.
    """

    stage_version = FULL_PARALLEL_RUNNER_VERSION

    def __init__(self) -> None:
        self.discovery = DiscoveryAdapter()
        self.gate = AcquisitionGateService()
        self.canonical = CanonicalArticleResolver()
        self.editorial = EditorialJudge()
        self.portfolio = PolicyPortfolioSelector()
        self.legacy = LegacyV056mAdapter()

    def run(
        self,
        context: RunContext,
        *,
        captured_discoveries: Iterable[Any],
        acquired_pairs: Iterable[tuple[Any, Any]],
        now_bj: datetime,
        max_selected: int = 10,
    ) -> ParallelShadowReport:
        captured = tuple(captured_discoveries)
        pairs = tuple(acquired_pairs)
        entries: list[_Entry] = []
        events: list[StageEvent] = []
        by_object_id: dict[int, _Entry] = {}
        by_canonical: dict[str, list[_Entry]] = {}
        gate_context = GateContext(now_bj=now_bj, known_duplicate_urls=frozenset())

        for ordinal, captured_item in enumerate(captured, start=1):
            item = getattr(captured_item, "item", captured_item)
            prefilter_status = str(
                getattr(captured_item, "prefilter_status", "unknown") or "unknown"
            )
            prefilter_reason = str(
                getattr(captured_item, "prefilter_reject_reason", "") or ""
            )
            adaptation = self.discovery.adapt(
                context,
                item,
                ordinal=ordinal,
                created_at_bj=context.started_at_bj,
            )
            gate_run = self.gate.decide(
                adaptation.record,
                gate_context,
                parent_event_id=adaptation.event.event_id,
                created_at_bj=context.started_at_bj,
            )
            entry = _Entry(
                record=adaptation.record,
                gate=gate_run.decision,
                prefilter_status=prefilter_status,
                prefilter_reason=prefilter_reason,
                gate_event=gate_run.event,
                control_discovered=item,
            )
            entries.append(entry)
            events.extend((adaptation.event, gate_run.event))
            by_object_id[id(item)] = entry
            by_canonical.setdefault(canonicalize_url(str(item.url)), []).append(entry)

        next_ordinal = len(entries) + 1
        used_entries: set[str] = set()
        fingerprint_mismatches = 0
        shared_body_count = 0

        for discovered, article in pairs:
            entry = by_object_id.get(id(discovered))
            if entry is None:
                canonical = canonicalize_url(str(discovered.url))
                entry = next(
                    (
                        candidate
                        for candidate in by_canonical.get(canonical, ())
                        if candidate.record.item_id not in used_entries
                    ),
                    None,
                )
            if entry is None:
                adaptation = self.discovery.adapt(
                    context,
                    discovered,
                    ordinal=next_ordinal,
                    created_at_bj=context.started_at_bj,
                )
                next_ordinal += 1
                gate_run = self.gate.decide(
                    adaptation.record,
                    gate_context,
                    parent_event_id=adaptation.event.event_id,
                    created_at_bj=context.started_at_bj,
                )
                entry = _Entry(
                    record=adaptation.record,
                    gate=gate_run.decision,
                    prefilter_status="acquired_without_snapshot_row",
                    prefilter_reason="capture_gap",
                    gate_event=gate_run.event,
                    control_discovered=discovered,
                )
                entries.append(entry)
                events.extend((adaptation.event, gate_run.event))
                by_object_id[id(discovered)] = entry
                by_canonical.setdefault(
                    canonicalize_url(str(discovered.url)), []
                ).append(entry)

            used_entries.add(entry.record.item_id)
            legacy_item = self.legacy.adapt_item(
                context=context,
                discovered=discovered,
                article=article,
                created_at_bj=context.started_at_bj,
            )
            shared = share_control_acquisition(
                legacy_item.acquisition,
                shadow_item_id=entry.record.item_id,
                gate_action=entry.gate.action,
                created_at_bj=context.started_at_bj,
                parent_event_id=entry.gate_event.event_id,
            )
            if shared.body_sha256 != body_fingerprint(legacy_item.acquisition):
                fingerprint_mismatches += 1
            if shared.bundle.body_markdown or shared.bundle.body_text:
                shared_body_count += 1

            canonical_article = self.canonical.canonicalize(
                context,
                entry.record,
                shared.bundle,
            )
            editorial_assessment = self.editorial.assess(
                context,
                canonical_article,
                shared.bundle,
            )
            diagnostic_only = entry.gate.action is not GateAction.ACQUIRE
            canonical_event = _canonical_event(
                context,
                canonical_article,
                parent_event_id=shared.event.event_id,
                diagnostic_only=diagnostic_only,
            )
            editorial_event = _editorial_event(
                context,
                editorial_assessment,
                parent_event_id=canonical_event.event_id,
                diagnostic_only=diagnostic_only,
            )
            entry.control_article = article
            entry.legacy = legacy_item
            entry.shared = shared
            entry.canonical = canonical_article
            entry.editorial = editorial_assessment
            entry.canonical_event = canonical_event
            entry.editorial_event = editorial_event
            events.extend((shared.event, canonical_event, editorial_event))

        selection_candidates = tuple(
            SelectionCandidate(
                article=entry.canonical,
                assessment=entry.editorial,
                estimated_cost=0.0,
            )
            for entry in entries
            if entry.gate.action is GateAction.ACQUIRE
            and entry.canonical is not None
            and entry.editorial is not None
        )
        portfolio = self.portfolio.select(
            context,
            selection_candidates,
            max_selected=max_selected,
        )
        decisions = {decision.item_id: decision for decision in portfolio.decisions}

        comparisons: list[ShadowItemComparison] = []
        for entry in entries:
            decision = decisions.get(entry.record.item_id)
            if entry.gate.action is GateAction.HARD_REJECT:
                effective_action = PolicyAction.REJECT.value
                effective_reason = f"gate:{entry.gate.reason_code}"
                selected = False
                rank = None
            elif entry.gate.action is GateAction.DEFER:
                effective_action = PolicyAction.DEFER.value
                effective_reason = f"gate:{entry.gate.reason_code}"
                selected = False
                rank = None
            elif decision is None:
                effective_action = PolicyAction.DEFER.value
                effective_reason = "body_not_observed_in_control"
                selected = False
                rank = None
            else:
                effective_action = decision.policy_action.value
                effective_reason = decision.reason_code
                selected = bool(decision.selected)
                rank = decision.selection_rank

            legacy_disposition = (
                str(entry.control_article.candidate_disposition)
                if entry.control_article is not None
                else ""
            )
            legacy_policy_action = (
                entry.legacy.selection.policy_action.value if entry.legacy is not None else ""
            )
            v06_verdict = entry.editorial.verdict.value if entry.editorial is not None else ""
            tags = difference_tags(
                gate_action=entry.gate.action.value,
                legacy_disposition=legacy_disposition,
                legacy_policy_action=legacy_policy_action,
                v06_policy_action=effective_action,
                legacy_canonical=(entry.legacy.canonical if entry.legacy is not None else None),
                v06_canonical=entry.canonical,
                legacy_editorial=(entry.legacy.editorial if entry.legacy is not None else None),
                v06_editorial=entry.editorial,
            )
            if entry.gate.action is GateAction.ACQUIRE and entry.control_article is None:
                tags = (*tags, "control_did_not_acquire_gate_pass")
            selection_event = _selection_event(
                context,
                item_id=entry.record.item_id,
                action=effective_action,
                reason=effective_reason,
                selected=selected,
                rank=rank,
                parent_event_id=(
                    entry.editorial_event.event_id
                    if entry.editorial_event is not None
                    else entry.gate_event.event_id
                ),
                observed_body=entry.control_article is not None,
            )
            events.append(selection_event)
            comparisons.append(
                ShadowItemComparison(
                    item_id=entry.record.item_id,
                    url=entry.record.url,
                    prefilter_status=entry.prefilter_status,
                    prefilter_reason=entry.prefilter_reason,
                    acquired_by_control=entry.control_article is not None,
                    gate_action=entry.gate.action.value,
                    gate_reason=entry.gate.reason_code,
                    legacy_disposition=legacy_disposition,
                    legacy_policy_action=legacy_policy_action,
                    v06_editorial_verdict=v06_verdict,
                    v06_policy_action=effective_action,
                    v06_selected=selected,
                    v06_selection_rank=rank,
                    diagnostic_only=(
                        entry.control_article is not None
                        and entry.gate.action is not GateAction.ACQUIRE
                    ),
                    body_sha256=(entry.shared.body_sha256 if entry.shared is not None else ""),
                    difference_tags=tags,
                )
            )

        return ParallelShadowReport(
            run_id=context.run_id,
            group_id=context.group_id,
            items=tuple(comparisons),
            events=tuple(events),
            control_acquired_count=len(pairs),
            shared_body_count=shared_body_count,
            shadow_request_count=0,
            shadow_firecrawl_request_count=0,
            shadow_incremental_cost=0.0,
            body_fingerprint_mismatches=fingerprint_mismatches,
            selected_item_ids=portfolio.selected_item_ids,
            source_chase_item_ids=portfolio.source_chase_item_ids,
        )


def _canonical_event(
    context: RunContext,
    article: CanonicalArticle,
    *,
    parent_event_id: str,
    diagnostic_only: bool,
) -> StageEvent:
    return make_stage_event(
        run_id=context.run_id,
        item_id=article.item_id,
        stage=StageName.CANONICAL,
        event_type=StageEventType.CANONICAL_RESULT,
        stage_version=article.stage_version,
        technical_status=TechnicalStatus.SUCCESS,
        flow_status=FlowStatus.PASS,
        reason_code=("canonical_diagnostic_only" if diagnostic_only else "canonical_resolved"),
        created_at_bj=context.started_at_bj,
        parent_event_id=parent_event_id,
        attributes={
            "diagnostic_only": diagnostic_only,
            "page_surface": article.page_surface.value,
            "main_content_medium": article.main_content_medium.value,
            "editorial_genre": article.editorial_genre.value,
            "asset_class": article.asset_class.value,
            "published_at": article.published_at,
            "published_at_confidence": article.published_at_confidence,
            "source_relationship": article.source_relationship.value,
            "source_action": article.source_action.value,
            "canonical_source": article.canonical_source,
        },
        evidence=article.evidence,
    )


def _editorial_event(
    context: RunContext,
    assessment: EditorialAssessment,
    *,
    parent_event_id: str,
    diagnostic_only: bool,
) -> StageEvent:
    return make_stage_event(
        run_id=context.run_id,
        item_id=assessment.item_id,
        stage=StageName.EDITORIAL,
        event_type=StageEventType.EDITORIAL_RESULT,
        stage_version=assessment.stage_version,
        technical_status=TechnicalStatus.SUCCESS,
        flow_status=FlowStatus.PASS,
        reason_code=("editorial_diagnostic_only" if diagnostic_only else "editorial_assessed"),
        created_at_bj=context.started_at_bj,
        parent_event_id=parent_event_id,
        attributes={
            "diagnostic_only": diagnostic_only,
            "verdict": assessment.verdict.value,
            "confidence": assessment.confidence,
            "substance": assessment.substance_score,
            "original_reporting": assessment.original_reporting_score,
            "analysis": assessment.analysis_score,
            "argument": assessment.argument_score,
            "evidence_density": assessment.evidence_density_score,
            "reader_value": assessment.reader_value_score,
            "timeliness_relevance": assessment.timeliness_relevance_score,
            "promotional_risk": assessment.promotional_risk,
            "event_risk": assessment.event_risk,
            "transcript_risk": assessment.transcript_risk,
            "template_risk": assessment.template_risk,
        },
        evidence=assessment.evidence,
    )


def _selection_event(
    context: RunContext,
    *,
    item_id: str,
    action: str,
    reason: str,
    selected: bool,
    rank: int | None,
    parent_event_id: str,
    observed_body: bool,
) -> StageEvent:
    if action in {PolicyAction.SELECT_STANDARD.value, PolicyAction.SELECT_SPECIAL.value}:
        flow = FlowStatus.PASS
    elif action == PolicyAction.SOURCE_CHASE.value:
        flow = FlowStatus.ACTION_REQUIRED
    elif action == PolicyAction.REJECT.value:
        flow = FlowStatus.REJECT
    else:
        flow = FlowStatus.DEFER
    return make_stage_event(
        run_id=context.run_id,
        item_id=item_id,
        stage=StageName.SELECTION,
        event_type=StageEventType.SELECTION_RESULT,
        stage_version=FULL_PARALLEL_RUNNER_VERSION,
        technical_status=(TechnicalStatus.SUCCESS if observed_body else TechnicalStatus.PARTIAL),
        flow_status=flow,
        reason_code=reason,
        created_at_bj=context.started_at_bj,
        parent_event_id=parent_event_id,
        attributes={
            "policy_action": action,
            "selected": selected,
            "selection_rank": rank,
            "observed_control_body": observed_body,
            "portfolio_scope": "shared_control_body_subset",
        },
    )


__all__ = ["FULL_PARALLEL_RUNNER_VERSION", "FullParallelShadowRunner"]
