from __future__ import annotations

from longread_collector.supplemental_date_evidence_v056f import (
    supplemental_url_date_evidence,
)


def resolved(url: str):
    values = supplemental_url_date_evidence(url)
    assert len(values) == 1
    return values[0]


def test_chinese_newspaper_year_month_day_paths() -> None:
    entry = resolved(
        "https://paper.people.com.cn/xwzx/html/2018-02/01/content_1840117.htm"
    )
    assert entry.value.date().isoformat() == "2018-02-01"
    assert entry.source == "url_path_legacy_date"

    entry = resolved(
        "http://mzqb.cyol.com/html/2023-04/18/content_332995.htm"
    )
    assert entry.value.date().isoformat() == "2023-04-18"


def test_compact_date_and_month_segments() -> None:
    entry = resolved(
        "https://www.scio.gov.cn/xwfb/202207/t20220715_214897.html"
    )
    assert entry.value.date().isoformat() == "2022-07-15"

    month = resolved(
        "https://caict.ac.cn/kxyj/qwfb/ztbg/202603/P020260324.pdf"
    )
    assert month.value.date().isoformat() == "2026-03-01"
    assert month.source == "url_month_segment"


def test_bjnews_detail_prefix_is_unix_timestamp() -> None:
    entry = resolved(
        "https://www.bjnews.com.cn/detail/1785199934129721.html"
    )
    assert entry.value.date().isoformat() == "2026-07-28"
    assert entry.source == "url_unix_timestamp"


def test_uuid_and_generic_paths_do_not_invent_dates() -> None:
    assert supplemental_url_date_evidence(
        "https://example.com/article/62a9e903-c859-4b82-81dd-d0ee1d4adbb0"
    ) == []
