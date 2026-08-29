from __future__ import annotations

from longread_collector.zh_route_shadow_s2a_eligibility_audit_v1 import (
    S2ACohortItem,
    build_s2a_cohort,
    validate_reviewed_labels,
)


def test_missing_control_overlap_is_not_treated_as_false():
    row = {
        "collector_run_id": "COL-A",
        "treatment_observed_at_bj": "2026-08-29 05:00:36",
        "source_id": "yicai",
        "surface_id": "yicai_kechuang",
        "surface_role": "core_editorial",
        "url_canonical": "https://yicai.com/news/missing-overlap.html",
        "title": "行业分析 2小时前",
        "control_overlap": "",
    }
    assert build_s2a_cohort([row]) == ()


def test_reviewed_label_reason_must_match_class():
    cohort = (
        S2ACohortItem(
            "u1",
            "yicai",
            "article",
            1,
            ("yicai_kechuang",),
            ("r1",),
        ),
    )
    result = validate_reviewed_labels(
        cohort,
        {
            "u1": {
                "metadata_class": "plausible_standard_longread",
                "class_reason": "promotional_or_corporate_pr_identity",
            }
        },
    )
    assert result["valid"] is False
    assert result["invalid_labels"] == [
        {
            "url_canonical": "u1",
            "metadata_class": "plausible_standard_longread",
            "class_reason": "promotional_or_corporate_pr_identity",
        }
    ]
