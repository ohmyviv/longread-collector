"""Conservative S3 fixed-32 utility bounds.

This proof layer consumes an already-produced outcome-aware S3 replay.  It does
not perform Discovery, acquisition, networking, Sheet I/O, or production
mutation.  Unknown Treatment bodies are pessimistically worth zero for the
lower bound.  Unknown displaced Control bodies are pessimistically counted as
Standard Longreads for that same lower bound.

Per-run minima are summed even though this may choose mutually inconsistent
outcomes for the same unresolved identity across dates.  That deliberate
relaxation can only make the aggregate lower bound more conservative.  If the
result remains positive, unresolved evidence cannot flip the aggregate sign.
"""
from __future__ import annotations

from typing import Any, Mapping

from .zh_route_shadow_s3_fixed32_v12 import (
    MAX_ATTEMPTS,
    OUTCOME_CENSORED,
    OUTCOME_UNRESOLVED,
    OUTCOME_UNUSABLE,
    OUTCOME_USABLE,
)

DECISION_SUPPORTS = "SUPPORTS_S4_SHADOW_SELECTION_REVIEW"
DECISION_NO_CLEAR = "NO_CLEAR_FIXED32_GAIN"
DECISION_NEGATIVE = "DOES_NOT_SUPPORT_S4"
DECISION_NOT_EVALUABLE = "NOT_EVALUABLE"

SIGN_POSITIVE = "POSITIVE"
SIGN_NON_POSITIVE = "NON_POSITIVE_OR_MIXED"
SIGN_NEGATIVE = "NEGATIVE"
SIGN_INDETERMINATE = "INDETERMINATE"


def _control_count_bounds(
    urls: list[str],
    outcomes: Mapping[str, str],
) -> tuple[int, int]:
    """Return (minimum Standard count, maximum Standard count)."""
    minimum = 0
    maximum = 0
    for url in urls:
        state = outcomes.get(url, OUTCOME_UNRESOLVED)
        if state == OUTCOME_USABLE:
            minimum += 1
            maximum += 1
        elif state == OUTCOME_UNUSABLE:
            continue
        else:
            maximum += 1
    return minimum, maximum


def _scenario_bound(
    run: Mapping[str, Any],
    *,
    unresolved_first_stage_usable: bool,
    control_outcomes: Mapping[str, str],
) -> dict[str, Any]:
    states = dict(run.get("treatment_body_outcomes", {}))
    unresolved_attempts = {
        url
        for url, state in states.items()
        if state in {OUTCOME_UNRESOLVED, OUTCOME_CENSORED}
    }
    unresolved_first = set(run.get("unknown_treatment_first_stage_urls", []))
    known_usable = {url for url, state in states.items() if state == OUTCOME_USABLE}
    unresolved_non_first = unresolved_attempts - unresolved_first

    # The structural replay's usable/failed scenario fixes the outcome only for
    # unresolved first-stage identities because those outcomes determine stage
    # two scheduling.  Later unresolved Treatment attempts cannot change the
    # schedule, so they are 0..1 utility in either scenario.
    first_stage_credit = len(unresolved_first) if unresolved_first_stage_usable else 0
    treatment_lower = len(known_usable) + first_stage_credit
    treatment_upper = treatment_lower + len(unresolved_non_first)

    displaced_key = (
        "control_displaced_if_unknown_usable"
        if unresolved_first_stage_usable
        else "control_displaced_if_unknown_failed"
    )
    displaced = list(run.get(displaced_key, []))
    control_lower, control_upper = _control_count_bounds(displaced, control_outcomes)

    return {
        "scenario": "unresolved_first_stage_usable" if unresolved_first_stage_usable else "unresolved_first_stage_failed",
        "treatment_standard_lower": treatment_lower,
        "treatment_standard_upper": treatment_upper,
        "displaced_control_standard_lower": control_lower,
        "displaced_control_standard_upper": control_upper,
        "delta_lower": treatment_lower - control_upper,
        "delta_upper": treatment_upper - control_lower,
        "unresolved_first_stage_urls": sorted(unresolved_first),
        "unresolved_non_first_stage_urls": sorted(unresolved_non_first),
        "displaced_control_urls": displaced,
        "unknown_displaced_control_urls": sorted(
            url for url in displaced if url not in control_outcomes
        ),
    }


def conservative_fixed32_utility_bounds(
    replay_result: Mapping[str, Any],
    *,
    control_outcomes: Mapping[str, str],
) -> dict[str, Any]:
    """Prove an aggregate utility sign without imputing unresolved bodies."""
    per_run: list[dict[str, Any]] = []
    for run in replay_result.get("runs", []):
        usable = _scenario_bound(
            run,
            unresolved_first_stage_usable=True,
            control_outcomes=control_outcomes,
        )
        failed = _scenario_bound(
            run,
            unresolved_first_stage_usable=False,
            control_outcomes=control_outcomes,
        )
        lower = min(usable["delta_lower"], failed["delta_lower"])
        upper = max(usable["delta_upper"], failed["delta_upper"])
        per_run.append(
            {
                "run_id": run.get("run_id"),
                "delta_lower": lower,
                "delta_upper": upper,
                "scenarios": [usable, failed],
            }
        )

    aggregate_lower = sum(value["delta_lower"] for value in per_run)
    aggregate_upper = sum(value["delta_upper"] for value in per_run)
    if aggregate_lower > 0:
        sign = SIGN_POSITIVE
    elif aggregate_upper < 0:
        sign = SIGN_NEGATIVE
    elif aggregate_lower == aggregate_upper == 0:
        sign = SIGN_NON_POSITIVE
    else:
        sign = SIGN_INDETERMINATE

    control_pass = bool(replay_result.get("control_replays")) and all(
        bool(value.get("pass")) for value in replay_result.get("control_replays", [])
    )
    treatment_dates = list(replay_result.get("treatment_entry_intended_dates", []))
    caps_pass = all(
        int(run.get("attempt_count_if_unknown_usable", 0)) <= MAX_ATTEMPTS
        and int(run.get("attempt_count_if_unknown_failed", 0)) <= MAX_ATTEMPTS
        for run in replay_result.get("runs", [])
    )

    if not control_pass:
        decision = DECISION_NOT_EVALUABLE
    elif len(treatment_dates) < 2 or not caps_pass:
        decision = DECISION_NOT_EVALUABLE
    elif sign == SIGN_POSITIVE:
        decision = DECISION_SUPPORTS
    elif sign == SIGN_NEGATIVE:
        decision = DECISION_NEGATIVE
    elif sign in {SIGN_NON_POSITIVE, SIGN_INDETERMINATE}:
        decision = DECISION_NO_CLEAR if aggregate_lower == aggregate_upper else DECISION_NOT_EVALUABLE
    else:
        decision = DECISION_NOT_EVALUABLE

    return {
        "method": "conservative_fixed32_utility_bound_v1",
        "aggregate_delta_lower_bound": aggregate_lower,
        "aggregate_delta_upper_bound": aggregate_upper,
        "aggregate_sign": sign,
        "remaining_unknowns_can_flip_sign": not (aggregate_lower > 0 or aggregate_upper < 0),
        "control_replay_pass": control_pass,
        "treatment_entry_intended_dates": treatment_dates,
        "treatment_entry_min_two_dates": len(treatment_dates) >= 2,
        "max_attempts": MAX_ATTEMPTS,
        "caps_pass": caps_pass,
        "decision": decision,
        "per_run": per_run,
        "lower_bound_policy": {
            "unknown_treatment": "count_as_0",
            "unknown_displaced_control": "count_as_standard_longread",
            "cross_run_unknown_correlation": "relaxed_by_summing_per_run_minima",
        },
    }


__all__ = [
    "DECISION_NEGATIVE",
    "DECISION_NOT_EVALUABLE",
    "DECISION_NO_CLEAR",
    "DECISION_SUPPORTS",
    "conservative_fixed32_utility_bounds",
]
