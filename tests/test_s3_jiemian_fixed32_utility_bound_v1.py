from __future__ import annotations

from longread_collector.zh_route_shadow_s3_fixed32_v12 import (
    OUTCOME_CENSORED,
    OUTCOME_UNRESOLVED,
    OUTCOME_UNUSABLE,
    OUTCOME_USABLE,
)
from longread_collector.zh_route_shadow_s3_utility_bound_v1 import (
    DECISION_SUPPORTS,
    conservative_fixed32_utility_bounds,
)


def test_positive_lower_bound_survives_unknown_treatment_and_control() -> None:
    result = {
        "control_replays": [{"pass": True}],
        "treatment_entry_intended_dates": ["20260827", "20260828"],
        "runs": [
            {
                "run_id": "r1",
                "treatment_body_outcomes": {
                    "t-known": OUTCOME_USABLE,
                    "t-censored": OUTCOME_CENSORED,
                    "t-missing": OUTCOME_UNRESOLVED,
                    "t-bad": OUTCOME_UNUSABLE,
                },
                "unknown_treatment_first_stage_urls": ["t-censored"],
                "control_displaced_if_unknown_usable": ["c-known", "c-unknown"],
                "control_displaced_if_unknown_failed": ["c-known"],
                "attempt_count_if_unknown_usable": 10,
                "attempt_count_if_unknown_failed": 10,
            },
            {
                "run_id": "r2",
                "treatment_body_outcomes": {
                    "t2a": OUTCOME_USABLE,
                    "t2b": OUTCOME_USABLE,
                },
                "unknown_treatment_first_stage_urls": [],
                "control_displaced_if_unknown_usable": [],
                "control_displaced_if_unknown_failed": [],
                "attempt_count_if_unknown_usable": 8,
                "attempt_count_if_unknown_failed": 8,
            },
        ],
    }
    bound = conservative_fixed32_utility_bounds(
        result,
        control_outcomes={"c-known": OUTCOME_UNUSABLE},
    )
    # r1 worst case: known Treatment 1 - unknown displaced Control 1 = 0.
    # r2 contributes +2, so aggregate remains strictly positive.
    assert bound["aggregate_delta_lower_bound"] == 2
    assert bound["remaining_unknowns_can_flip_sign"] is False
    assert bound["decision"] == DECISION_SUPPORTS


def test_unknown_displaced_control_is_maximally_adverse_in_lower_bound() -> None:
    result = {
        "control_replays": [{"pass": True}],
        "treatment_entry_intended_dates": ["d1", "d2"],
        "runs": [
            {
                "run_id": "r1",
                "treatment_body_outcomes": {"t": OUTCOME_USABLE},
                "unknown_treatment_first_stage_urls": [],
                "control_displaced_if_unknown_usable": ["c-unknown"],
                "control_displaced_if_unknown_failed": ["c-unknown"],
                "attempt_count_if_unknown_usable": 1,
                "attempt_count_if_unknown_failed": 1,
            }
        ],
    }
    bound = conservative_fixed32_utility_bounds(result, control_outcomes={})
    assert bound["per_run"][0]["delta_lower"] == 0
    assert bound["per_run"][0]["scenarios"][0]["displaced_control_standard_upper"] == 1
