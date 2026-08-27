from __future__ import annotations

from longread_collector.zh_route_shadow_timestamp_forensic_v1 import (
    audit_item_timestamp,
    audit_timestamp_rows,
    url_path_date,
)


def _base(**overrides):
    row = {
        "source_id": "yicai",
        "surface_id": "yicai_kechuang",
        "url_canonical": "https://yicai.com/news/103337130.html",
        "title": "手机卖不动、价格却涨了 3小时前",
        "published_at": "",
        "treatment_observed_at_bj": "2026-08-27 22:48:21",
    }
    row.update(overrides)
    return row


def test_url_path_date_is_extracted_without_claiming_publication_semantics() -> None:
    assert url_path_date("https://companies.caixin.com/2026-08-27/102478733.html") == "2026-08-27"
    assert url_path_date("https://www.jiemian.com/article/15010846.html") == ""


def test_caixin_day0_false_stale_date_is_flagged_as_conflict() -> None:
    findings = audit_item_timestamp(
        _base(
            source_id="caixin",
            surface_id="caixin_companies",
            url_canonical="https://companies.caixin.com/2026-08-27/102478733.html",
            title="上半年储能电池海外订单同比增八成 欧洲为第一大市场",
            published_at="2026-08-02",
        )
    )
    assert [finding.finding for finding in findings] == ["url_path_date_conflict"]
    assert findings[0].url_path_date == "2026-08-27"


def test_yicai_article_local_relative_age_can_be_observed_without_binding() -> None:
    findings = audit_item_timestamp(_base())
    assert [finding.finding for finding in findings] == ["relative_age_available_but_unbound"]
    assert findings[0].relative_age_text == "3小时前"


def test_yicai_neighbor_clock_binding_is_flagged_when_day_scale_wrong() -> None:
    findings = audit_item_timestamp(
        _base(published_at="2026-08-26T22:43:00+08:00")
    )
    assert [finding.finding for finding in findings] == ["relative_age_binding_conflict"]


def test_relative_age_rounding_tolerance_does_not_overclaim_exact_clock() -> None:
    findings = audit_item_timestamp(
        _base(published_at="2026-08-27T19:55:00+08:00")
    )
    assert findings == []


def test_jiemian_good_listing_timestamp_does_not_create_false_finding() -> None:
    findings = audit_item_timestamp(
        _base(
            source_id="jiemian-depth",
            surface_id="jiemian_medicine",
            url_canonical="https://jiemian.com/article/15010846.html",
            title="英国完成全球首例AI实时辅助脑外科手术",
            published_at="2026-08-27T21:16:00+08:00",
        )
    )
    assert findings == []


def test_aggregate_report_separates_conflict_from_available_but_unbound() -> None:
    rows = [
        _base(),
        _base(
            source_id="caixin",
            surface_id="caixin_companies",
            url_canonical="https://companies.caixin.com/2026-08-27/102478733.html",
            title="上半年储能电池海外订单同比增八成 欧洲为第一大市场",
            published_at="2026-08-02",
        ),
    ]
    report = audit_timestamp_rows(rows)
    assert report["item_rows"] == 2
    assert report["conflict_count"] == 1
    assert report["available_but_unbound_count"] == 1
    assert report["timestamp_utility_interpretable"] is False
