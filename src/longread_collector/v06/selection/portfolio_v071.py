"""PR-7.1 freshness safety boundary around the PR-4 portfolio selector."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
import hashlib
from typing import Iterable

from ..contracts import (
    AssetClass,
    Evidence,
    EditorialVerdict,
    PolicyAction,
    RunContext,
    SelectionDecision,
    SelectionTrack,
    SourceAction,
    StageName,
)
from .portfolio import (
    PolicyPortfolioSelector as _BasePolicyPortfolioSelector,
    PortfolioSelectionResult,
    SelectionCandidate,
)

PORTFOLIO_VERSION = "portfolio-selector-v0.6-pr7.1"

_SOURCE_CHASE_ACTIONS = {
    SourceAction.FIND_ORIGINAL_ARTICLE,
    SourceAction.FIND_PRIMARY_DOCUMENT,
    SourceAction.REPLACE_WITH_ORIGINAL,
}


class PolicyPortfolioSelector:
    """Apply a hard freshness boundary before bounded expected-utility selection.

    Ordinary written longreads:
    - known age <= 7 days: normal PR-4 portfolio path;
    - 8-14 days: only a high-quality deep-read exception, max two per run,
      and only when it beats the weakest timely standard selection;
    - >14 days: policy reject;
    - missing/conflicting publication evidence: defer, not neutral selection.

    Primary documents and academic papers remain on their separate tracks.
    """

    stage_version = PORTFOLIO_VERSION

    def __init__(self) -> None:
        self._base = _BasePolicyPortfolioSelector()

    def select(
        self,
        context: RunContext,
        candidates: Iterable[SelectionCandidate],
        *,
        max_selected: int = 10,
        min_standard_utility: float = 0.20,
        min_special_utility: float = 0.16,
        soft_source_cap: int = 3,
    ) -> PortfolioSelectionResult:
        items = tuple(candidates)
        normal: list[SelectionCandidate] = []
        deep_read: list[SelectionCandidate] = []
        excluded: dict[str, SelectionDecision] = {}

        for item in items:
            article = item.article
            if _bypass_standard_freshness(article):
                normal.append(item)
                continue

            conflict = bool(article.freshness_facts.get("publication_conflict", False))
            age = _freshness_age_days(context, article)
            if conflict:
                excluded[article.item_id] = _freshness_decision(
                    context,
                    item,
                    PolicyAction.DEFER,
                    "publication_evidence_conflict_defer",
                    age,
                )
                continue
            if age is None or not article.published_at or article.published_at_confidence < 0.60:
                excluded[article.item_id] = _freshness_decision(
                    context,
                    item,
                    PolicyAction.DEFER,
                    "publication_date_unknown_defer",
                    age,
                )
                continue
            if age > 14:
                excluded[article.item_id] = _freshness_decision(
                    context,
                    item,
                    PolicyAction.REJECT,
                    "standard_longread_stale_over_14d",
                    age,
                )
                continue
            if age >= 8:
                if _deep_read_quality_floor(item):
                    deep_read.append(item)
                else:
                    excluded[article.item_id] = _freshness_decision(
                        context,
                        item,
                        PolicyAction.REJECT,
                        "deep_read_8_14d_quality_floor_not_met",
                        age,
                    )
                continue
            normal.append(item)

        baseline = self._base.select(
            context,
            normal,
            max_selected=max_selected,
            min_standard_utility=min_standard_utility,
            min_special_utility=min_special_utility,
            soft_source_cap=soft_source_cap,
        )

        eligible_deep: list[SelectionCandidate] = []
        if deep_read:
            weakest_timely = min(
                (
                    decision.marginal_utility
                    for decision in baseline.decisions
                    if decision.selected
                    and decision.selection_track is SelectionTrack.STANDARD_LONGREAD
                ),
                default=min_standard_utility,
            )
            scored: list[tuple[float, str, SelectionCandidate]] = []
            for item in deep_read:
                single = self._base.select(
                    context,
                    [item],
                    max_selected=1,
                    min_standard_utility=min_standard_utility,
                    min_special_utility=min_special_utility,
                    soft_source_cap=soft_source_cap,
                )
                decision = single.decisions[0]
                scored.append((decision.marginal_utility, item.article.item_id, item))
            scored.sort(key=lambda row: (-row[0], row[1]))

            for marginal, _, item in scored:
                if marginal <= weakest_timely:
                    excluded[item.article.item_id] = _freshness_decision(
                        context,
                        item,
                        PolicyAction.DEFER,
                        "deep_read_exception_not_better_than_weakest_timely",
                        _freshness_age_days(context, item.article),
                    )
                elif len(eligible_deep) >= 2:
                    excluded[item.article.item_id] = _freshness_decision(
                        context,
                        item,
                        PolicyAction.DEFER,
                        "deep_read_exception_daily_cap",
                        _freshness_age_days(context, item.article),
                    )
                else:
                    eligible_deep.append(item)

        final = baseline
        if eligible_deep:
            final = self._base.select(
                context,
                [*normal, *eligible_deep],
                max_selected=max_selected,
                min_standard_utility=min_standard_utility,
                min_special_utility=min_special_utility,
                soft_source_cap=soft_source_cap,
            )

        final_by_id = {decision.item_id: decision for decision in final.decisions}
        ordered = tuple(
            excluded.get(item.article.item_id)
            or _retag(final_by_id[item.article.item_id])
            for item in items
        )
        selected_ids = tuple(
            decision.item_id
            for decision in sorted(
                (decision for decision in ordered if decision.selected),
                key=lambda decision: decision.selection_rank or 10**6,
            )
        )
        source_chase_ids = tuple(
            decision.item_id
            for decision in ordered
            if decision.policy_action is PolicyAction.SOURCE_CHASE
        )
        total_utility = round(
            sum(decision.marginal_utility for decision in ordered if decision.selected),
            6,
        )
        return PortfolioSelectionResult(
            schema_version=context.schema_version,
            stage_version=PORTFOLIO_VERSION,
            run_id=context.run_id,
            decisions=ordered,
            selected_item_ids=selected_ids,
            source_chase_item_ids=source_chase_ids,
            total_marginal_utility=total_utility,
        )


def _bypass_standard_freshness(article) -> bool:
    if article.asset_class in {AssetClass.PRIMARY_DOCUMENT, AssetClass.ACADEMIC_PAPER}:
        return True
    if article.source_action in _SOURCE_CHASE_ACTIONS:
        return True
    return False


def _deep_read_quality_floor(item: SelectionCandidate) -> bool:
    assessment = item.assessment
    if assessment.verdict is not EditorialVerdict.RECOMMEND:
        return False
    if assessment.substance_score < 0.88:
        return False
    overall = (
        0.40 * assessment.substance_score
        + 0.22 * assessment.reader_value_score
        + 0.18 * assessment.analysis_score
        + 0.20 * assessment.evidence_density_score
    )
    if overall < 0.85:
        return False
    return max(
        assessment.promotional_risk,
        assessment.event_risk,
        assessment.transcript_risk,
        assessment.template_risk,
    ) < 0.45


def _freshness_age_days(context: RunContext, article) -> int | None:
    stored = article.freshness_facts.get("resolved_freshness_age_days")
    if isinstance(stored, (int, float)):
        return max(0, int(stored))
    published = _parse_datetime(article.published_at)
    run_time = _parse_datetime(context.started_at_bj or context.scheduled_at_bj)
    if published is None or run_time is None:
        return None
    return max(0, (run_time.date() - published.date()).days)


def _parse_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def _freshness_decision(
    context: RunContext,
    item: SelectionCandidate,
    action: PolicyAction,
    reason: str,
    age_days: int | None,
) -> SelectionDecision:
    evidence = (
        _evidence(item.article.item_id, "policy_action", action.value, reason),
        _evidence(
            item.article.item_id,
            "selection_track",
            SelectionTrack.STANDARD_LONGREAD.value,
            reason,
        ),
        _evidence(item.article.item_id, "freshness_age_days", age_days, reason),
    )
    return SelectionDecision(
        schema_version=context.schema_version,
        stage_version=PORTFOLIO_VERSION,
        run_id=context.run_id,
        item_id=item.article.item_id,
        policy_action=action,
        selection_track=SelectionTrack.STANDARD_LONGREAD,
        selected=False,
        selection_rank=None,
        marginal_utility=0.0,
        risk_penalty=0.0,
        diversity_penalty=0.0,
        freshness_penalty=1.0 if action is PolicyAction.REJECT else 0.0,
        cost_penalty=0.0,
        reason_code=reason,
        evidence=evidence,
    )


def _retag(decision: SelectionDecision) -> SelectionDecision:
    # Base PR-4 decisions remain semantically unchanged; stage_version only marks
    # that the PR-7.1 freshness boundary was evaluated before portfolio ranking.
    from dataclasses import replace

    return replace(decision, stage_version=PORTFOLIO_VERSION)


def _evidence(item_id: str, field: str, value: object, reason: str) -> Evidence:
    seed = f"{item_id}|{PORTFOLIO_VERSION}|{field}|{value}|{reason}"
    return Evidence(
        evidence_id=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20],
        evidence_type="selection_freshness_boundary",
        source_stage=StageName.SELECTION,
        field=field,
        value=value,
        confidence=0.98,
        excerpt=reason,
        extractor=PORTFOLIO_VERSION,
    )


__all__ = [
    "PORTFOLIO_VERSION",
    "PolicyPortfolioSelector",
    "PortfolioSelectionResult",
    "SelectionCandidate",
]
