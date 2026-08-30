"""Outcome-aware S3 fixed-32 replay v1.2.

v1 and v1.1 remain immutable historical evidence.  v1.2 changes only the
measurement model for Treatment body outcomes: a reviewed Treatment identity
can be confirmed usable, confirmed unusable, or unresolved.  Confirmed
non-target bodies are never varied as if they were unknown.

This module is offline/read-only.  It performs no Discovery, body acquisition,
network request, Sheet write, Editor wiring, or production mutation.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Mapping

from . import zh_route_shadow_s3_fixed32_v1 as v1
from . import zh_route_shadow_s3_fixed32_v11 as v11
from .models import DiscoveredURL, ExtractedArticle

S3_VERSION = "zh-route-shadow-s3-jiemian-fixed32-v1.2-outcome-aware"
ROOT_CAUSE = "treatment_body_outcome_tristate_measurement"

FROZEN_RUN_IDS = v1.FROZEN_RUN_IDS
FROZEN_SOURCE_ID = v1.FROZEN_SOURCE_ID
FROZEN_PLAUSIBLE_COUNT = v1.FROZEN_PLAUSIBLE_COUNT
MAX_ATTEMPTS = v1.MAX_ATTEMPTS

OUTCOME_USABLE = "usable"
OUTCOME_UNUSABLE = "unusable"
OUTCOME_UNRESOLVED = "unresolved"
OUTCOME_CENSORED = "instrumentation_censored"

UTILITY_COMPLETE = "FIXED32_UTILITY_EVIDENCE_COMPLETE"
UTILITY_NEEDS_EVIDENCE = "FIXED32_UTILITY_NEEDS_EVIDENCE"
UTILITY_CENSORED = "FIXED32_UTILITY_HAS_IRRECOVERABLE_CENSORING"

_USABLE_CLASSES = {"body_confirmed_standard_longread"}
_UNUSABLE_CLASSES = {
    "body_confirmed_non_target",
    "body_borderline_insufficient",
}
_CENSORED_CLASSES = {
    "not_evaluable_instrumentation_censored",
    "not_evaluable_instrumentation_failure_after_network_attempt",
}


def _canonical(row: Mapping[str, Any]) -> str:
    return v1._canonical(row.get("url") or row.get("url_canonical"))


def _review_outcome(row: Mapping[str, Any]) -> str:
    review_class = v1._text(row.get("review_class")).lower()
    evidence_state = v1._text(row.get("evidence_state")).lower()
    if review_class in _USABLE_CLASSES:
        return OUTCOME_USABLE
    if review_class in _UNUSABLE_CLASSES:
        return OUTCOME_UNUSABLE
    if review_class in _CENSORED_CLASSES or evidence_state == OUTCOME_CENSORED:
        return OUTCOME_CENSORED
    return OUTCOME_UNRESOLVED


def review_outcome_map(reviewed_rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Return the frozen human-review outcome per Jiemian primary identity."""
    result: dict[str, str] = {}
    for row in reviewed_rows:
        if v1._text(row.get("source")) != FROZEN_SOURCE_ID:
            continue
        if v1._text(row.get("role")) != "primary_plausible":
            continue
        url = _canonical(row)
        if not url:
            continue
        outcome = _review_outcome(row)
        prior = result.get(url)
        if prior is not None and prior != outcome:
            raise ValueError(f"conflicting human review outcomes for {url}: {prior} vs {outcome}")
        result[url] = outcome
    return result


def _treatment_stub_for_outcome(
    item: DiscoveredURL,
    index: int,
    *,
    outcome: str,
    unresolved_usable: bool,
) -> ExtractedArticle:
    usable = outcome == OUTCOME_USABLE or (
        outcome in {OUTCOME_UNRESOLVED, OUTCOME_CENSORED} and unresolved_usable
    )
    return v1._treatment_stub(item, index, usable=usable)


def _select_and_stage_outcome_aware(
    *,
    run_id: str,
    discovered: list[DiscoveredURL],
    snapshot_by_url: Mapping[str, Mapping[str, Any]],
    treatment_confirmed: set[str],
    unknown_treatment_usable: bool,
) -> dict[str, Any]:
    """Drop-in v1 selector using the installed tri-state outcome map.

    ``treatment_confirmed`` is retained in the signature for compatibility with
    v1.  The v1.2 context installs the full outcome map separately.  A URL that
    is present in the historical confirmed set is treated as usable even if an
    older caller omitted it from the map.
    """
    outcomes = dict(_ACTIVE_OUTCOME_MAP)
    for url in treatment_confirmed:
        outcomes.setdefault(v1._canonical(url), OUTCOME_USABLE)

    v1.clear_selection_plan()
    with v1._run_time_freshness(run_id):
        selected, rejected = v1.filter_discovered_v056m(
            discovered,
            max_urls=MAX_ATTEMPTS,
            max_per_domain=2,
        )
        plan = v1.current_selection_plan()
        if plan is None:
            raise RuntimeError("S3 selection did not publish a reserve plan")
        first_stage, deferred = v1.split_first_stage(selected, max_attempts=MAX_ATTEMPTS)
        first_articles: list[ExtractedArticle] = []
        unresolved_first_stage: list[str] = []
        censored_first_stage: list[str] = []
        for index, item in enumerate(first_stage, start=1):
            url = v1._canonical(item.url)
            if bool(item.metadata.get("s3_treatment")):
                outcome = outcomes.get(url, OUTCOME_UNRESOLVED)
                if outcome in {OUTCOME_UNRESOLVED, OUTCOME_CENSORED}:
                    unresolved_first_stage.append(url)
                if outcome == OUTCOME_CENSORED:
                    censored_first_stage.append(url)
                first_articles.append(
                    _treatment_stub_for_outcome(
                        item,
                        index,
                        outcome=outcome,
                        unresolved_usable=unknown_treatment_usable,
                    )
                )
            else:
                row = snapshot_by_url.get(url)
                if row is None:
                    raise ValueError(f"missing persisted Control outcome for first-stage URL: {url}")
                first_articles.append(v1._historical_stub(item, row, index))
        decision = v1.build_second_stage_v056m(
            plan=plan,
            first_stage=first_stage,
            deferred=deferred,
            first_articles=first_articles,
            max_attempts=MAX_ATTEMPTS,
        )
    attempts = decision.first_stage + decision.second_stage
    attempt_urls = [v1._canonical(item.url) for item in attempts]
    treatment_attempt_urls = [
        v1._canonical(item.url)
        for item in attempts
        if bool(item.metadata.get("s3_treatment"))
    ]
    return {
        "selected": selected,
        "rejected": rejected,
        "first_stage": decision.first_stage,
        "second_stage": decision.second_stage,
        "attempts": attempts,
        "attempt_urls": attempt_urls,
        "first_stage_urls": [v1._canonical(item.url) for item in decision.first_stage],
        "treatment_first_stage_urls": [
            v1._canonical(item.url)
            for item in decision.first_stage
            if bool(item.metadata.get("s3_treatment"))
        ],
        "treatment_attempt_urls": treatment_attempt_urls,
        "unknown_treatment_first_stage_urls": sorted(set(unresolved_first_stage)),
        "censored_treatment_first_stage_urls": sorted(set(censored_first_stage)),
    }


_ACTIVE_OUTCOME_MAP: dict[str, str] = {}


@contextmanager
def _install_v12_outcomes(outcomes: Mapping[str, str]) -> Iterator[None]:
    global _ACTIVE_OUTCOME_MAP
    original_select = v1._select_and_stage
    original_map = _ACTIVE_OUTCOME_MAP
    v1._select_and_stage = _select_and_stage_outcome_aware
    _ACTIVE_OUTCOME_MAP = dict(outcomes)
    try:
        yield
    finally:
        v1._select_and_stage = original_select
        _ACTIVE_OUTCOME_MAP = original_map


def _annotate_utility(result: dict[str, Any], outcomes: Mapping[str, str]) -> dict[str, Any]:
    treatment_attempts = sorted(set(result.get("treatment_attempt_urls_union", [])))
    states = {url: outcomes.get(url, OUTCOME_UNRESOLVED) for url in treatment_attempts}
    missing = sorted(url for url, state in states.items() if state == OUTCOME_UNRESOLVED)
    censored = sorted(url for url, state in states.items() if state == OUTCOME_CENSORED)
    confirmed_usable = sorted(url for url, state in states.items() if state == OUTCOME_USABLE)
    confirmed_unusable = sorted(url for url, state in states.items() if state == OUTCOME_UNUSABLE)
    if missing:
        utility_status = UTILITY_NEEDS_EVIDENCE
    elif censored:
        utility_status = UTILITY_CENSORED
    else:
        utility_status = UTILITY_COMPLETE
    result["treatment_body_outcomes"] = states
    result["treatment_confirmed_usable_urls"] = confirmed_usable
    result["treatment_confirmed_unusable_urls"] = confirmed_unusable
    result["treatment_missing_body_evidence_urls"] = missing
    result["treatment_instrumentation_censored_urls"] = censored
    result["utility_evidence_manifest"] = missing
    result["utility_irrecoverable_censoring"] = censored
    result["utility_status"] = utility_status
    return result


def replay_s3_run(
    *,
    run_id: str,
    snapshot_rows: Iterable[Mapping[str, Any]],
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    snapshot = list(snapshot_rows)
    route = list(route_rows)
    cohort = list(cohort_rows)
    reviewed = list(reviewed_rows)
    outcomes = review_outcome_map(reviewed)
    with v11._install_v11_reconstruction(), _install_v12_outcomes(outcomes):
        result = v1.replay_s3_run(
            run_id=run_id,
            snapshot_rows=snapshot,
            route_rows=route,
            cohort_rows=cohort,
            reviewed_rows=reviewed,
        )
    result["version"] = S3_VERSION
    result["reconstruction"] = v11.ROOT_CAUSE
    result["measurement_correction"] = ROOT_CAUSE
    return _annotate_utility(result, outcomes)


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
    outcomes = review_outcome_map(reviewed)
    v1._plausible_index(cohort)

    control = [
        v11.replay_control_run(run_id=run_id, snapshot_rows=snapshot)
        for run_id in FROZEN_RUN_IDS
    ]
    if not all(value["pass"] for value in control):
        return {
            "version": S3_VERSION,
            "status": v1.STATUS_CONTROL_MISMATCH,
            "frozen_run_ids": list(FROZEN_RUN_IDS),
            "control_replays": control,
            "runs": [],
            "utility_status": "NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH",
        }

    runs = [
        replay_s3_run(
            run_id=run_id,
            snapshot_rows=snapshot,
            route_rows=route,
            cohort_rows=cohort,
            reviewed_rows=reviewed,
        )
        for run_id in FROZEN_RUN_IDS
    ]
    structural_blockers = sorted(
        {url for run in runs for url in run.get("evidence_completion_manifest", [])}
    )
    utility_missing = sorted(
        {url for run in runs for url in run.get("utility_evidence_manifest", [])}
    )
    utility_censored = sorted(
        {url for run in runs for url in run.get("utility_irrecoverable_censoring", [])}
    )
    treatment_dates = {
        run_id[4:12]
        for run_id, run in zip(FROZEN_RUN_IDS, runs, strict=True)
        if run.get("treatment_attempt_urls_union")
    }
    if utility_missing:
        utility_status = UTILITY_NEEDS_EVIDENCE
    elif utility_censored:
        utility_status = UTILITY_CENSORED
    else:
        utility_status = UTILITY_COMPLETE
    return {
        "version": S3_VERSION,
        "status": v1.STATUS_NEEDS_EVIDENCE if structural_blockers else "S3A_STRUCTURAL_REPLAY_COMPLETE",
        "frozen_run_ids": list(FROZEN_RUN_IDS),
        "frozen_plausible_count": FROZEN_PLAUSIBLE_COUNT,
        "max_attempts": MAX_ATTEMPTS,
        "control_replays": control,
        "runs": runs,
        "treatment_entry_intended_dates": sorted(treatment_dates),
        "evidence_completion_manifest": structural_blockers,
        "utility_evidence_manifest": utility_missing,
        "utility_irrecoverable_censoring": utility_censored,
        "utility_status": utility_status,
        "measurement_correction": ROOT_CAUSE,
        "reconstruction": v11.ROOT_CAUSE,
    }


__all__ = [
    "FROZEN_PLAUSIBLE_COUNT",
    "FROZEN_RUN_IDS",
    "FROZEN_SOURCE_ID",
    "MAX_ATTEMPTS",
    "OUTCOME_CENSORED",
    "OUTCOME_UNRESOLVED",
    "OUTCOME_UNUSABLE",
    "OUTCOME_USABLE",
    "ROOT_CAUSE",
    "S3_VERSION",
    "UTILITY_CENSORED",
    "UTILITY_COMPLETE",
    "UTILITY_NEEDS_EVIDENCE",
    "replay_s3_cohort",
    "replay_s3_run",
    "review_outcome_map",
]
