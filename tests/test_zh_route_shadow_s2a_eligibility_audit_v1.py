from __future__ import annotations

from longread_collector.zh_route_shadow_s2a_eligibility_audit_v1 import (
    S2A_ELIGIBILITY_VERSION,
    S2ACohortItem,
    build_s2a_cohort,
    validate_reviewed_labels,
)


def _row(**overrides):
    row = {
        "collector_run_id": "COL-A",
        "treatment_observed_at_bj": "2026-08-29 05:00:36",
        "source_id": "yicai",
        "surface_id": "yicai_kechuang",
        "surface_role": "core_editorial",
        "url_canonical": "https://yicai.com/news/1.html",
        "title": "机器人行业深度 2小时前",
        "published_at": "",
        "publication_time_source": "",
        "publication_time_confidence": "",
        "control_overlap": False,
    }
    row.update(overrides)
    return row


def test_build_cohort_filters_to_fresh_incremental_non_control_rows():
    rows = [
        _row(url_canonical="https://yicai.com/news/fresh.html"),
        _row(
            url_canonical="https://yicai.com/news/conflict.html",
            title="冲突 2小时前",
            published_at="2026-08-27T01:00:00+08:00",
            publication_time_confidence="high",
        ),
        _row(url_canonical="https://yicai.com/news/overlap.html", control_overlap=True),
        _row(url_canonical="https://yicai.com/news/noise.html", surface_role="noise_control"),
        _row(url_canonical="https://other.example/a", source_id="caixin"),
    ]
    cohort = build_s2a_cohort(rows)
    assert [item.url_canonical for item in cohort] == ["https://yicai.com/news/fresh.html"]


def test_build_cohort_collapses_canonical_identity_and_retains_provenance():
    rows = [
        _row(
            collector_run_id="COL-A",
            surface_id="yicai_kechuang",
            url_canonical="https://yicai.com/news/2.html",
        ),
        _row(
            collector_run_id="COL-B",
            surface_id="yicai_news_breadth",
            surface_role="breadth_safety",
            url_canonical="https://yicai.com/news/2.html",
        ),
    ]
    cohort = build_s2a_cohort(rows)
    assert len(cohort) == 1
    item = cohort[0]
    assert item.qualifying_row_count == 2
    assert item.qualifying_surfaces == ("yicai_kechuang", "yicai_news_breadth")
    assert item.collector_run_ids == ("COL-A", "COL-B")


def test_jiemian_exact_high_fresh_is_admitted():
    cohort = build_s2a_cohort(
        [
            _row(
                source_id="jiemian-depth",
                surface_id="jiemian_medicine",
                url_canonical="https://jiemian.com/article/1.html",
                title="医药行业深度",
                published_at="2026-08-28T19:17:00+08:00",
                publication_time_source="listing_relative_clock",
                publication_time_confidence="high",
            )
        ]
    )
    assert len(cohort) == 1
    assert cohort[0].source_id == "jiemian-depth"


def test_stale_jiemian_exact_is_not_admitted():
    cohort = build_s2a_cohort(
        [
            _row(
                source_id="jiemian-depth",
                surface_id="jiemian_medicine",
                url_canonical="https://jiemian.com/article/old.html",
                title="旧文章",
                published_at="2026-08-01T19:17:00+08:00",
                publication_time_source="listing_month_day_clock",
                publication_time_confidence="high",
            )
        ]
    )
    assert cohort == ()


def test_reviewed_label_validation_requires_exact_coverage():
    cohort = (
        S2ACohortItem("u1", "jiemian-depth", "a", 1, ("jiemian_medicine",), ("r1",)),
        S2ACohortItem("u2", "yicai", "b", 1, ("yicai_finance",), ("r2",)),
    )
    labels = {
        "u1": {
            "metadata_class": "plausible_standard_longread",
            "class_reason": "substantive_editorial_depth_signal",
        }
    }
    result = validate_reviewed_labels(cohort, labels)
    assert result["version"] == S2A_ELIGIBILITY_VERSION
    assert result["valid"] is False
    assert result["missing_urls"] == ["u2"]


def test_reviewed_label_validation_summarizes_source_counts():
    cohort = (
        S2ACohortItem("u1", "jiemian-depth", "a", 1, ("jiemian_medicine",), ("r1",)),
        S2ACohortItem("u2", "yicai", "b", 1, ("yicai_finance",), ("r2",)),
        S2ACohortItem("u3", "yicai", "c", 1, ("yicai_kechuang",), ("r2",)),
    )
    labels = {
        "u1": {
            "metadata_class": "plausible_standard_longread",
            "class_reason": "substantive_editorial_depth_signal",
        },
        "u2": {
            "metadata_class": "obvious_out_of_scope",
            "class_reason": "promotional_or_corporate_pr_identity",
        },
        "u3": {
            "metadata_class": "insufficient_evidence",
            "class_reason": "metadata_insufficient_for_longread_depth",
        },
    }
    result = validate_reviewed_labels(cohort, labels)
    assert result["valid"] is True
    assert result["class_counts"] == {
        "insufficient_evidence": 1,
        "obvious_out_of_scope": 1,
        "plausible_standard_longread": 1,
    }
    assert result["by_source"]["jiemian-depth"] == {"plausible_standard_longread": 1}
    assert result["by_source"]["yicai"] == {
        "insufficient_evidence": 1,
        "obvious_out_of_scope": 1,
    }
