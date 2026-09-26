from __future__ import annotations

from longread_collector.zh_route_shadow_s3_fixed32_v12 import (
    OUTCOME_CENSORED,
    OUTCOME_UNRESOLVED,
    OUTCOME_UNUSABLE,
    OUTCOME_USABLE,
    ROOT_CAUSE,
    S3_VERSION,
    UTILITY_CENSORED,
    UTILITY_NEEDS_EVIDENCE,
    _annotate_utility,
    review_outcome_map,
)


def _row(url: str, review_class: str, *, evidence_state: str = "") -> dict[str, str]:
    return {
        "url": url,
        "source": "jiemian-depth",
        "role": "primary_plausible",
        "review_class": review_class,
        "evidence_state": evidence_state,
    }


def test_v12_identity_and_root_cause_are_explicit() -> None:
    assert S3_VERSION == "zh-route-shadow-s3-jiemian-fixed32-v1.2-outcome-aware"
    assert ROOT_CAUSE == "treatment_body_outcome_tristate_measurement"


def test_review_outcome_map_keeps_usable_unusable_and_censored_distinct() -> None:
    rows = [
        _row("https://jiemian.com/article/1.html", "body_confirmed_standard_longread"),
        _row("https://jiemian.com/article/2.html", "body_confirmed_non_target"),
        _row("https://jiemian.com/article/3.html", "body_borderline_insufficient"),
        _row(
            "https://jiemian.com/article/4.html",
            "not_evaluable_instrumentation_failure_after_network_attempt",
            evidence_state="instrumentation_censored",
        ),
        _row("https://jiemian.com/article/5.html", ""),
    ]
    outcomes = review_outcome_map(rows)
    assert outcomes["https://jiemian.com/article/1.html"] == OUTCOME_USABLE
    assert outcomes["https://jiemian.com/article/2.html"] == OUTCOME_UNUSABLE
    assert outcomes["https://jiemian.com/article/3.html"] == OUTCOME_UNUSABLE
    assert outcomes["https://jiemian.com/article/4.html"] == OUTCOME_CENSORED
    assert outcomes["https://jiemian.com/article/5.html"] == OUTCOME_UNRESOLVED


def test_known_non_target_is_not_reported_as_missing_utility_evidence() -> None:
    result = {
        "treatment_attempt_urls_union": [
            "https://jiemian.com/article/1.html",
            "https://jiemian.com/article/2.html",
            "https://jiemian.com/article/3.html",
        ]
    }
    outcomes = {
        "https://jiemian.com/article/1.html": OUTCOME_USABLE,
        "https://jiemian.com/article/2.html": OUTCOME_UNUSABLE,
        "https://jiemian.com/article/3.html": OUTCOME_CENSORED,
    }
    annotated = _annotate_utility(result, outcomes)
    assert annotated["treatment_confirmed_unusable_urls"] == [
        "https://jiemian.com/article/2.html"
    ]
    assert annotated["treatment_missing_body_evidence_urls"] == []
    assert annotated["utility_irrecoverable_censoring"] == [
        "https://jiemian.com/article/3.html"
    ]
    assert annotated["utility_status"] == UTILITY_CENSORED


def test_absent_review_is_a_true_missing_utility_manifest_item() -> None:
    result = {
        "treatment_attempt_urls_union": [
            "https://jiemian.com/article/1.html",
            "https://jiemian.com/article/99.html",
        ]
    }
    annotated = _annotate_utility(
        result,
        {"https://jiemian.com/article/1.html": OUTCOME_USABLE},
    )
    assert annotated["utility_evidence_manifest"] == [
        "https://jiemian.com/article/99.html"
    ]
    assert annotated["utility_status"] == UTILITY_NEEDS_EVIDENCE
