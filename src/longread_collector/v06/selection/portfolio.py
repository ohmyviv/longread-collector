"""Expected-utility portfolio selection for v0.6 PR-4."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from ..contracts import (
    CanonicalArticle,
    EditorialAssessment,
    Evidence,
    PolicyAction,
    RunContext,
    SelectionDecision,
    SelectionTrack,
    StageName,
)
from .policy import PolicyEvaluation, evaluate_policy

PORTFOLIO_VERSION = "portfolio-selector-v0.6-pr4"


@dataclass(frozen=True, slots=True)
class SelectionCandidate:
    article: CanonicalArticle
    assessment: EditorialAssessment
    estimated_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class PortfolioSelectionResult:
    schema_version: str
    stage_version: str
    run_id: str
    decisions: tuple[SelectionDecision, ...]
    selected_item_ids: tuple[str, ...]
    source_chase_item_ids: tuple[str, ...]
    total_marginal_utility: float


class PolicyPortfolioSelector:
    """Apply policy actions, then greedily optimize a bounded daily portfolio."""

    stage_version = PORTFOLIO_VERSION

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
        if max_selected < 0:
            raise ValueError("max_selected must be >= 0")
        if soft_source_cap < 1:
            raise ValueError("soft_source_cap must be >= 1")

        evaluations = {
            item.article.item_id: evaluate_policy(
                item.article,
                item.assessment,
                estimated_cost=item.estimated_cost,
            )
            for item in items
        }

        final_decisions: dict[str, SelectionDecision] = {}
        selectable: list[SelectionCandidate] = []
        source_chase_ids: list[str] = []

        for item in items:
            item_id = item.article.item_id
            evaluation = evaluations[item_id]
            if evaluation.provisional_action in {
                PolicyAction.SELECT_STANDARD,
                PolicyAction.SELECT_SPECIAL,
            }:
                selectable.append(item)
                continue
            if evaluation.provisional_action is PolicyAction.SOURCE_CHASE:
                source_chase_ids.append(item_id)
            final_decisions[item_id] = _terminal_decision(context, item, evaluation)

        selected: list[SelectionCandidate] = []
        selected_scores: dict[str, tuple[float, float, float, str]] = {}
        source_counts: dict[str, int] = {}
        genre_counts: dict[str, int] = {}
        selected_duplicate_clusters: set[str] = set()

        remaining = list(selectable)
        while remaining and len(selected) < max_selected:
            ranked: list[tuple[float, str, SelectionCandidate, float, float, str]] = []
            for item in remaining:
                evaluation = evaluations[item.article.item_id]
                diversity_penalty = _diversity_penalty(
                    item.article,
                    source_counts,
                    genre_counts,
                    soft_source_cap=soft_source_cap,
                )
                redundancy_penalty, redundancy_reason = _redundancy_penalty(
                    item.article,
                    selected_duplicate_clusters,
                )
                marginal = evaluation.pre_diversity_utility - diversity_penalty - redundancy_penalty
                ranked.append((
                    marginal,
                    item.article.item_id,
                    item,
                    diversity_penalty,
                    redundancy_penalty,
                    redundancy_reason,
                ))

            ranked.sort(key=lambda row: (-row[0], row[1]))
            marginal, _, best, diversity_penalty, redundancy_penalty, redundancy_reason = ranked[0]
            evaluation = evaluations[best.article.item_id]
            threshold = (
                min_special_utility
                if evaluation.track in {SelectionTrack.SPECIAL_DOCUMENT, SelectionTrack.ACADEMIC}
                else min_standard_utility
            )
            if marginal < threshold:
                break

            selected.append(best)
            selected_scores[best.article.item_id] = (
                marginal,
                diversity_penalty,
                redundancy_penalty,
                redundancy_reason,
            )
            source = _source_key(best.article)
            source_counts[source] = source_counts.get(source, 0) + 1
            genre = best.article.editorial_genre.value
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
            if best.article.duplicate_cluster_id:
                selected_duplicate_clusters.add(best.article.duplicate_cluster_id)
            remaining = [
                item for item in remaining if item.article.item_id != best.article.item_id
            ]

        rank_by_id = {
            item.article.item_id: rank
            for rank, item in enumerate(selected, start=1)
        }
        for item in selected:
            item_id = item.article.item_id
            evaluation = evaluations[item_id]
            marginal, diversity_penalty, redundancy_penalty, redundancy_reason = selected_scores[item_id]
            final_decisions[item_id] = _selected_decision(
                context,
                item,
                evaluation,
                rank=rank_by_id[item_id],
                marginal=marginal,
                diversity_penalty=diversity_penalty,
                redundancy_penalty=redundancy_penalty,
                redundancy_reason=redundancy_reason,
            )

        selected_ids = set(rank_by_id)
        for item in selectable:
            item_id = item.article.item_id
            if item_id in selected_ids:
                continue
            evaluation = evaluations[item_id]
            diversity_penalty = _diversity_penalty(
                item.article,
                source_counts,
                genre_counts,
                soft_source_cap=soft_source_cap,
            )
            redundancy_penalty, redundancy_reason = _redundancy_penalty(
                item.article,
                selected_duplicate_clusters,
            )
            marginal = evaluation.pre_diversity_utility - diversity_penalty - redundancy_penalty
            threshold = (
                min_special_utility
                if evaluation.track in {SelectionTrack.SPECIAL_DOCUMENT, SelectionTrack.ACADEMIC}
                else min_standard_utility
            )
            if redundancy_penalty >= 0.90:
                reason = redundancy_reason or "portfolio_duplicate"
            elif len(selected) >= max_selected:
                reason = "portfolio_capacity"
            elif marginal < threshold:
                reason = "below_portfolio_utility_threshold"
            else:
                reason = "portfolio_defer"
            final_decisions[item_id] = _deferred_selectable_decision(
                context,
                item,
                evaluation,
                marginal=marginal,
                diversity_penalty=diversity_penalty,
                reason=reason,
            )

        ordered_decisions = tuple(final_decisions[item.article.item_id] for item in items)
        selected_item_ids = tuple(
            item.article.item_id
            for item in sorted(selected, key=lambda row: rank_by_id[row.article.item_id])
        )
        total_utility = sum(
            final_decisions[item_id].marginal_utility
            for item_id in selected_item_ids
        )
        return PortfolioSelectionResult(
            schema_version=context.schema_version,
            stage_version=PORTFOLIO_VERSION,
            run_id=context.run_id,
            decisions=ordered_decisions,
            selected_item_ids=selected_item_ids,
            source_chase_item_ids=tuple(source_chase_ids),
            total_marginal_utility=round(total_utility, 6),
        )


def _terminal_decision(
    context: RunContext,
    item: SelectionCandidate,
    evaluation: PolicyEvaluation,
) -> SelectionDecision:
    marginal = evaluation.pre_diversity_utility
    return SelectionDecision(
        schema_version=context.schema_version,
        stage_version=PORTFOLIO_VERSION,
        run_id=context.run_id,
        item_id=item.article.item_id,
        policy_action=evaluation.provisional_action,
        selection_track=evaluation.track,
        selected=False,
        selection_rank=None,
        marginal_utility=round(marginal, 6),
        risk_penalty=round(evaluation.risk_penalty, 6),
        diversity_penalty=0.0,
        freshness_penalty=round(evaluation.freshness_penalty, 6),
        cost_penalty=round(evaluation.cost_penalty, 6),
        reason_code=evaluation.reason_code,
        evidence=_selection_evidence(
            item.article.item_id,
            evaluation.provisional_action,
            evaluation.track,
            marginal=marginal,
            risk_penalty=evaluation.risk_penalty,
            diversity_penalty=0.0,
            freshness_penalty=evaluation.freshness_penalty,
            cost_penalty=evaluation.cost_penalty,
            reason=evaluation.reason_code,
        ),
    )


def _selected_decision(
    context: RunContext,
    item: SelectionCandidate,
    evaluation: PolicyEvaluation,
    *,
    rank: int,
    marginal: float,
    diversity_penalty: float,
    redundancy_penalty: float,
    redundancy_reason: str,
) -> SelectionDecision:
    reason = "selected_by_expected_utility"
    if redundancy_penalty:
        reason = redundancy_reason or reason
    return SelectionDecision(
        schema_version=context.schema_version,
        stage_version=PORTFOLIO_VERSION,
        run_id=context.run_id,
        item_id=item.article.item_id,
        policy_action=evaluation.provisional_action,
        selection_track=evaluation.track,
        selected=True,
        selection_rank=rank,
        marginal_utility=round(marginal, 6),
        risk_penalty=round(evaluation.risk_penalty, 6),
        diversity_penalty=round(diversity_penalty, 6),
        freshness_penalty=round(evaluation.freshness_penalty, 6),
        cost_penalty=round(evaluation.cost_penalty, 6),
        reason_code=reason,
        evidence=_selection_evidence(
            item.article.item_id,
            evaluation.provisional_action,
            evaluation.track,
            marginal=marginal,
            risk_penalty=evaluation.risk_penalty,
            diversity_penalty=diversity_penalty,
            freshness_penalty=evaluation.freshness_penalty,
            cost_penalty=evaluation.cost_penalty,
            reason=reason,
        ),
    )


def _deferred_selectable_decision(
    context: RunContext,
    item: SelectionCandidate,
    evaluation: PolicyEvaluation,
    *,
    marginal: float,
    diversity_penalty: float,
    reason: str,
) -> SelectionDecision:
    return SelectionDecision(
        schema_version=context.schema_version,
        stage_version=PORTFOLIO_VERSION,
        run_id=context.run_id,
        item_id=item.article.item_id,
        policy_action=PolicyAction.DEFER,
        selection_track=evaluation.track,
        selected=False,
        selection_rank=None,
        marginal_utility=round(marginal, 6),
        risk_penalty=round(evaluation.risk_penalty, 6),
        diversity_penalty=round(diversity_penalty, 6),
        freshness_penalty=round(evaluation.freshness_penalty, 6),
        cost_penalty=round(evaluation.cost_penalty, 6),
        reason_code=reason,
        evidence=_selection_evidence(
            item.article.item_id,
            PolicyAction.DEFER,
            evaluation.track,
            marginal=marginal,
            risk_penalty=evaluation.risk_penalty,
            diversity_penalty=diversity_penalty,
            freshness_penalty=evaluation.freshness_penalty,
            cost_penalty=evaluation.cost_penalty,
            reason=reason,
        ),
    )


def _diversity_penalty(
    article: CanonicalArticle,
    source_counts: dict[str, int],
    genre_counts: dict[str, int],
    *,
    soft_source_cap: int,
) -> float:
    source_count = source_counts.get(_source_key(article), 0)
    genre_count = genre_counts.get(article.editorial_genre.value, 0)
    source_penalty = 0.045 * source_count
    if source_count >= soft_source_cap:
        source_penalty += 0.12
    genre_penalty = 0.018 * max(0, genre_count - 1)
    return min(0.32, source_penalty + genre_penalty)


def _redundancy_penalty(
    article: CanonicalArticle,
    selected_duplicate_clusters: set[str],
) -> tuple[float, str]:
    cluster = article.duplicate_cluster_id.strip()
    if cluster and cluster in selected_duplicate_clusters:
        return 1.0, "duplicate_cluster_already_selected"
    return 0.0, ""


def _source_key(article: CanonicalArticle) -> str:
    return (
        article.canonical_source
        or article.publisher
        or article.hosting_source
        or article.display_url
        or article.item_id
    ).strip().lower()


def _selection_evidence(
    item_id: str,
    action: PolicyAction,
    track: SelectionTrack,
    *,
    marginal: float,
    risk_penalty: float,
    diversity_penalty: float,
    freshness_penalty: float,
    cost_penalty: float,
    reason: str,
) -> tuple[Evidence, ...]:
    rows = (
        ("policy_action", action.value),
        ("selection_track", track.value),
        ("marginal_utility", round(marginal, 6)),
        ("risk_penalty", round(risk_penalty, 6)),
        ("diversity_penalty", round(diversity_penalty, 6)),
        ("freshness_penalty", round(freshness_penalty, 6)),
        ("cost_penalty", round(cost_penalty, 6)),
    )
    return tuple(
        _make_evidence(
            item_id,
            field,
            value,
            excerpt=reason if field == "policy_action" else "",
        )
        for field, value in rows
    )


def _make_evidence(
    item_id: str,
    field: str,
    value: object,
    *,
    excerpt: str = "",
) -> Evidence:
    seed = f"{item_id}|{PORTFOLIO_VERSION}|{field}|{value}"
    return Evidence(
        evidence_id=hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20],
        evidence_type="selection_decision",
        source_stage=StageName.SELECTION,
        field=field,
        value=value,
        confidence=0.90,
        excerpt=excerpt[:500],
        extractor=PORTFOLIO_VERSION,
    )


__all__ = [
    "PORTFOLIO_VERSION",
    "PolicyPortfolioSelector",
    "PortfolioSelectionResult",
    "SelectionCandidate",
]