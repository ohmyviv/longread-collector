from __future__ import annotations

import random

import pytest

from longread_collector.zh_route_shadow_s2b_sample_plan_v1 import (
    INSUFFICIENT,
    PLAUSIBLE,
    S2B_BODY_ATTEMPT_CAP,
    S2B_PRIMARY_PLAUSIBLE_N,
    S2B_REPLACEMENT_ALLOWED,
    S2B_STRATUM_QUOTAS,
    S2B_UNCERTAINTY_EXPLORE_N,
    sample_summary,
    select_s2b_sample,
)


def _rows_for_frozen_denominators():
    denominators = {
        ("jiemian-depth", PLAUSIBLE, "jiemian_consumer"): 11,
        ("jiemian-depth", PLAUSIBLE, "jiemian_health_face"): 1,
        ("jiemian-depth", PLAUSIBLE, "jiemian_medicine"): 16,
        ("jiemian-depth", INSUFFICIENT, "jiemian_consumer"): 9,
        ("jiemian-depth", INSUFFICIENT, "jiemian_medicine"): 4,
        ("yicai", PLAUSIBLE, "yicai_auto"): 2,
        ("yicai", PLAUSIBLE, "yicai_finance"): 14,
        ("yicai", PLAUSIBLE, "yicai_kechuang"): 22,
        ("yicai", PLAUSIBLE, "yicai_news_breadth"): 5,
        ("yicai", INSUFFICIENT, "yicai_auto"): 1,
        ("yicai", INSUFFICIENT, "yicai_finance"): 15,
        ("yicai", INSUFFICIENT, "yicai_kechuang"): 5,
        ("yicai", INSUFFICIENT, "yicai_news_breadth"): 4,
    }
    rows = []
    counter = 1
    for (source_id, metadata_class, first_surface), count in denominators.items():
        for _ in range(count):
            rows.append(
                {
                    "url_canonical": f"https://example.test/{counter}.html",
                    "source_id": source_id,
                    "metadata_class": metadata_class,
                    "first_surface": first_surface,
                }
            )
            counter += 1
    # Obvious S2-A rejects are intentionally never body targets.
    rows.append(
        {
            "url_canonical": "https://example.test/out.html",
            "source_id": "yicai",
            "metadata_class": "obvious_out_of_scope",
            "first_surface": "yicai_kechuang",
        }
    )
    return rows


def test_sample_is_exactly_bounded_and_matches_frozen_quotas():
    sample = select_s2b_sample(_rows_for_frozen_denominators())
    assert len(sample) == S2B_BODY_ATTEMPT_CAP == 40
    assert S2B_REPLACEMENT_ALLOWED is False

    summary = sample_summary(sample)
    assert summary["selected_total"] == 40
    assert sum(
        count
        for key, count in summary["by_source_role"].items()
        if key.endswith("|primary_plausible")
    ) == S2B_PRIMARY_PLAUSIBLE_N == 30
    assert sum(
        count
        for key, count in summary["by_source_role"].items()
        if key.endswith("|uncertainty_explore")
    ) == S2B_UNCERTAINTY_EXPLORE_N == 10

    expected = {
        f"{source}|{metadata_class}|{surface}": quota
        for (source, metadata_class, surface), quota in S2B_STRATUM_QUOTAS.items()
    }
    assert summary["by_stratum"] == dict(sorted(expected.items()))


def test_selection_is_order_independent_under_fixed_seed():
    rows = _rows_for_frozen_denominators()
    first = [item.url_canonical for item in select_s2b_sample(rows)]
    shuffled = list(rows)
    random.Random(20260829).shuffle(shuffled)
    second = [item.url_canonical for item in select_s2b_sample(shuffled)]
    assert first == second


def test_stratum_under_quota_fails_closed_without_substitution():
    rows = _rows_for_frozen_denominators()
    rows = [
        row
        for row in rows
        if not (
            row["source_id"] == "yicai"
            and row["metadata_class"] == PLAUSIBLE
            and row["first_surface"] == "yicai_auto"
            and row["url_canonical"].endswith(".html")
        )
    ]
    with pytest.raises(ValueError, match="stratum under quota"):
        select_s2b_sample(rows)


def test_duplicate_canonical_url_fails_closed():
    rows = _rows_for_frozen_denominators()
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="duplicate canonical URL"):
        select_s2b_sample(rows)


def test_obvious_out_of_scope_never_enters_sample():
    sample = select_s2b_sample(_rows_for_frozen_denominators())
    assert all(item.metadata_class in {PLAUSIBLE, INSUFFICIENT} for item in sample)
    assert all(item.url_canonical != "https://example.test/out.html" for item in sample)
