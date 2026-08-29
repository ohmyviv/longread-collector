from __future__ import annotations

from longread_collector.zh_route_shadow_timestamp_measurement_v2 import (
    S1_TIMESTAMP_MEASUREMENT_VERSION,
    measure_item_timestamp,
    replay_timestamp_rows,
)


def _row(**overrides):
    row = {
        "source_id": "yicai",
        "surface_id": "yicai_news_breadth",
        "url_canonical": "https://yicai.com/news/1.html",
        "title": "example",
        "treatment_observed_at_bj": "2026-08-28 23:42:16",
        "published_at": "",
        "publication_time_source": "",
        "publication_time_confidence": "",
    }
    row.update(overrides)
    return row


def test_relative_age_becomes_bounded_fresh_when_unbound():
    result = measure_item_timestamp(_row(title="一篇文章 3小时前"))
    assert result.measurement_state == "bounded_relative"
    assert result.freshness_state == "fresh"
    assert result.primary_evidence == "listing_relative_age_bounded"


def test_card_local_yesterday_clock_becomes_exact_s1_evidence():
    result = measure_item_timestamp(
        _row(
            title="监管重拳整治速成车 昨天 20:04",
            treatment_observed_at_bj="2026-08-28 04:01:33",
        )
    )
    assert result.measurement_state == "card_clock_exact"
    assert result.freshness_state == "fresh"
    assert result.interval_start.startswith("2026-08-27T20:04:00")


def test_yicai_wrong_day_high_timestamp_fails_closed_as_conflict():
    result = measure_item_timestamp(
        _row(
            title="具身智能市场将破1万亿 3小时前",
            treatment_observed_at_bj="2026-08-27 22:48:21",
            published_at="2026-08-26T22:43:00+08:00",
            publication_time_source="listing_relative_clock",
            publication_time_confidence="high",
        )
    )
    assert result.measurement_state == "conflict"
    assert result.freshness_state == "conflict"
    assert "trusted_evidence_conflict" in result.diagnostic_flags


def test_yicai_wrong_bound_yesterday_clock_is_conflict():
    result = measure_item_timestamp(
        _row(
            title="监管重拳整治速成车 昨天 20:04",
            treatment_observed_at_bj="2026-08-28 04:01:33",
            published_at="2026-08-27T22:51:00+08:00",
            publication_time_source="listing_relative_clock",
            publication_time_confidence="high",
        )
    )
    assert result.measurement_state == "conflict"
    assert result.freshness_state == "conflict"
    assert "trusted_evidence_conflict" in result.diagnostic_flags


def test_jiemian_trusted_exact_timestamp_remains_fresh():
    result = measure_item_timestamp(
        _row(
            source_id="jiemian-depth",
            surface_id="jiemian_medicine",
            url_canonical="https://jiemian.com/article/15021674.html",
            title="上海医药靠创新药代理恢复增长",
            treatment_observed_at_bj="2026-08-29 05:00:36",
            published_at="2026-08-28T19:17:00+08:00",
            publication_time_source="listing_relative_clock",
            publication_time_confidence="high",
        )
    )
    assert result.measurement_state == "trusted_exact"
    assert result.freshness_state == "fresh"


def test_caixin_untrusted_persisted_date_does_not_override_url_day():
    result = measure_item_timestamp(
        _row(
            source_id="caixin",
            surface_id="caixin_companies",
            url_canonical="https://companies.caixin.com/2026-08-27/102.html",
            treatment_observed_at_bj="2026-08-27 22:48:21",
            published_at="2026-08-02",
            publication_time_source="listing_context",
            publication_time_confidence="",
        )
    )
    assert result.measurement_state == "date_only"
    assert result.freshness_state == "fresh"
    assert "persisted_timestamp_not_trusted" in result.diagnostic_flags


def test_url_date_near_seven_day_boundary_stays_unknown():
    result = measure_item_timestamp(
        _row(
            source_id="eeo",
            surface_id="eeo_business_industry",
            url_canonical="https://www.eeo.com.cn/2026/0821/123.shtml",
            treatment_observed_at_bj="2026-08-28 12:00:00",
        )
    )
    assert result.measurement_state == "date_only"
    assert result.freshness_state == "boundary_unknown"


def test_trusted_timestamp_vs_url_path_date_conflict_fails_closed():
    result = measure_item_timestamp(
        _row(
            url_canonical="https://www.eeo.com.cn/2026/0828/123.shtml",
            published_at="2026-08-27T10:00:00+08:00",
            publication_time_source="rss_pubdate",
            publication_time_confidence="high",
        )
    )
    assert result.measurement_state == "conflict"
    assert result.freshness_state == "conflict"
    assert "url_path_date_conflict" in result.diagnostic_flags


def test_old_exact_is_stale():
    result = measure_item_timestamp(
        _row(
            published_at="2026-08-10T10:00:00+08:00",
            publication_time_source="rss_pubdate",
            publication_time_confidence="high",
        )
    )
    assert result.measurement_state == "trusted_exact"
    assert result.freshness_state == "stale"


def test_no_evidence_is_unknown_not_stale():
    result = measure_item_timestamp(_row())
    assert result.measurement_state == "unknown"
    assert result.freshness_state == "unknown"


def test_replay_aggregates_without_rewriting_source_semantics():
    rows = [
        _row(title="fresh 1小时前"),
        _row(url_canonical="https://www.eeo.com.cn/2026/0828/2.shtml", source_id="eeo"),
        _row(),
    ]
    result = replay_timestamp_rows(rows)
    assert result["version"] == S1_TIMESTAMP_MEASUREMENT_VERSION
    assert result["item_rows"] == 3
    assert result["freshness_counts"]["fresh"] == 2
    assert result["freshness_counts"]["unknown"] == 1
    assert result["interpretable_freshness_rows"] == 2
    assert result["by_source"]["yicai"]["freshness:fresh"] == 1
    assert result["by_source"]["eeo"]["freshness:fresh"] == 1
