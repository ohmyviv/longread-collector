from __future__ import annotations

import pytest

from longread_collector.zh_route_shadow_s3_fixed32_v1 import (
    FROZEN_PLAUSIBLE_COUNT,
    FROZEN_RUN_IDS,
    MAX_ATTEMPTS,
    S3_VERSION,
    build_treatment_candidates,
    historical_attempt_order,
)


def _cohort() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(1, FROZEN_PLAUSIBLE_COUNT + 1):
        rows.append(
            {
                "source_id": "jiemian-depth",
                "url_canonical": f"https://jiemian.com/article/{1000 + index}.html",
                "title": f"冻结长文 {index}",
                "first_surface": "jiemian_medicine" if index % 2 else "jiemian_consumer",
                "metadata_class": "plausible_standard_longread",
            }
        )
    return rows


def _fresh_route(
    *,
    run_id: str,
    url: str,
    surface: str = "jiemian_medicine",
    ordinal: int = 1,
    title: str = "昨天 12:30 一篇具有解释性的深度报道",
) -> dict[str, object]:
    return {
        "observed_at_bj": "2026-08-28T10:00:00+08:00",
        "collector_run_id": run_id,
        "source_id": "jiemian-depth",
        "surface_id": surface,
        "route_role": "core_editorial",
        "route_type": "section_scan",
        "endpoint_url": "https://www.jiemian.com/lists/280.html",
        "item_ordinal": ordinal,
        "url_canonical": url,
        "title": title,
        "published_at": "2026-08-27T12:30:00+08:00",
        "publication_time_confidence": "high",
        "publication_time_source": "listing_time",
        "control_overlap": "FALSE",
    }


def test_contract_identity_is_frozen() -> None:
    assert S3_VERSION == "zh-route-shadow-s3-jiemian-fixed32-v1"
    assert len(FROZEN_RUN_IDS) == 4
    assert FROZEN_PLAUSIBLE_COUNT == 28
    assert MAX_ATTEMPTS == 32


def test_treatment_is_per_run_fresh_control_incremental_and_title_only() -> None:
    cohort = _cohort()
    run_id = FROZEN_RUN_IDS[0]
    url = str(cohort[0]["url_canonical"])
    other_run = FROZEN_RUN_IDS[1]
    rows = [
        _fresh_route(run_id=run_id, url=url),
        _fresh_route(run_id=other_run, url=str(cohort[1]["url_canonical"])),
        {
            **_fresh_route(run_id=run_id, url=str(cohort[2]["url_canonical"])),
            "control_overlap": "TRUE",
        },
        {
            **_fresh_route(run_id=run_id, url=str(cohort[3]["url_canonical"])),
            "published_at": "2026-07-01T12:30:00+08:00",
            "title": "旧稿",
        },
    ]
    items, evidence = build_treatment_candidates(
        run_id=run_id,
        route_rows=rows,
        cohort_rows=cohort,
        control_urls=set(),
    )
    assert [item.url for item in items] == [url]
    assert items[0].description == ""
    assert items[0].metadata["s3_treatment"] is True
    assert evidence[0].url_canonical == url


def test_same_run_multi_surface_dedup_prefers_frozen_first_surface() -> None:
    cohort = _cohort()
    run_id = FROZEN_RUN_IDS[0]
    url = str(cohort[0]["url_canonical"])
    rows = [
        _fresh_route(run_id=run_id, url=url, surface="jiemian_consumer", ordinal=1),
        _fresh_route(run_id=run_id, url=url, surface="jiemian_medicine", ordinal=8),
    ]
    items, evidence = build_treatment_candidates(
        run_id=run_id,
        route_rows=rows,
        cohort_rows=cohort,
        control_urls=set(),
    )
    assert len(items) == 1
    assert evidence[0].representative_surface == "jiemian_medicine"
    assert evidence[0].surfaces == ("jiemian_consumer", "jiemian_medicine")


def test_control_duplicate_is_not_reintroduced_as_treatment() -> None:
    cohort = _cohort()
    run_id = FROZEN_RUN_IDS[0]
    url = str(cohort[0]["url_canonical"])
    items, _ = build_treatment_candidates(
        run_id=run_id,
        route_rows=[_fresh_route(run_id=run_id, url=url)],
        cohort_rows=cohort,
        control_urls={url},
    )
    assert items == []


def test_frozen_universe_drift_fails_closed() -> None:
    cohort = _cohort()[:-1]
    with pytest.raises(ValueError, match="frozen Jiemian plausible universe changed"):
        build_treatment_candidates(
            run_id=FROZEN_RUN_IDS[0],
            route_rows=[],
            cohort_rows=cohort,
            control_urls=set(),
        )


def test_historical_attempt_order_must_be_contiguous_and_unique() -> None:
    run_id = FROZEN_RUN_IDS[0]
    rows = [
        {
            "collector_run_id": run_id,
            "url_canonical": "https://example.com/a",
            "metadata_json": '{"selection":{"actual_extraction_order":1}}',
        },
        {
            "collector_run_id": run_id,
            "url_canonical": "https://example.com/b",
            "metadata_json": '{"selection":{"actual_extraction_order":2}}',
        },
    ]
    assert historical_attempt_order(rows, run_id) == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    rows[1]["metadata_json"] = '{"selection":{"actual_extraction_order":3}}'
    with pytest.raises(ValueError, match="non-contiguous"):
        historical_attempt_order(rows, run_id)
