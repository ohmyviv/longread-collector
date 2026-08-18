from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.effective_route_v056 import parse_section_html_v056
from longread_collector.section_publication_time_v056 import (
    SECTION_PUBLICATION_TIME_VERSION,
    enrich_section_publication_times,
)

TZ = ZoneInfo("Asia/Shanghai")
OBSERVED = datetime(2026, 8, 18, 18, 12, 36, tzinfo=TZ)


def _source(source_id: str, homepage: str) -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_name": source_id,
        "homepage_url": homepage,
        "language": "zh",
        "priority_tier": "rotate",
    }


def _parse_and_enrich(
    html: str, *, source_id: str, homepage: str
):
    source = _source(source_id, homepage)
    items = parse_section_html_v056(
        html,
        source=source,
        endpoint=homepage,
        limit=24,
    )
    return enrich_section_publication_times(
        html,
        source=source,
        endpoint=homepage,
        items=items,
        observed_at=OBSERVED,
    )


def test_yicai_today_and_yesterday_clock_are_attached_to_their_article_cards() -> None:
    html = """
    <div class='card'><a href='/news/102100001.html'>第一篇足够长的第一财经文章标题</a>
      <span>摘要文字</span><span>昨天 18:08</span></div>
    <div class='card'><a href='/news/102100002.html'>第二篇足够长的第一财经文章标题</a>
      <span>今天 08:54</span></div>
    """
    items = _parse_and_enrich(html, source_id="yicai", homepage="https://www.yicai.com/")

    assert [item.published_at for item in items] == [
        "2026-08-17 18:08:00",
        "2026-08-18 08:54:00",
    ]
    assert all(
        item.metadata["section_publication_time_version"]
        == SECTION_PUBLICATION_TIME_VERSION
        for item in items
    )
    assert all(item.metadata["published_at_confidence"] == "high" for item in items)


def test_jiemian_exact_relative_day_clock_is_observed_but_vague_age_is_not() -> None:
    html = """
    <article><a href='/article/12345678.html'>界面列表中的一篇足够长文章标题</a>
      <a href='/author/1.html'>作者甲</a><span>今天 08:54 2.7w</span></article>
    <article><a href='/article/12345679.html'>界面列表中的另一篇足够长文章标题</a>
      <span>作者乙 40分钟前</span></article>
    """
    items = _parse_and_enrich(
        html,
        source_id="jiemian-depth",
        homepage="https://www.jiemian.com/",
    )

    assert len(items) == 2
    assert items[0].published_at == "2026-08-18 08:54:00"
    assert items[0].metadata["published_at_raw"] == "今天 08:54"
    assert items[1].published_at == ""


def test_month_day_without_year_is_deliberately_left_unknown() -> None:
    html = """
    <article><a href='/article/12345680.html'>界面旧条目也有足够长的文章标题</a>
      <span>作者甲 08/02 11:28 13.2w</span></article>
    """
    items = _parse_and_enrich(
        html,
        source_id="jiemian-depth",
        homepage="https://www.jiemian.com/",
    )

    assert len(items) == 1
    assert items[0].published_at == ""
    assert "section_publication_time_version" not in items[0].metadata


def test_chinawriter_remains_date_unknown_even_if_generic_text_looks_dated() -> None:
    html = """
    <div><a href='/n1/2026/0818/c404018-40512345.html'>中国作家网一篇足够长的文章标题</a>
      <span>昨天 18:08</span></div>
    """
    items = _parse_and_enrich(
        html,
        source_id="chinawriter",
        homepage="https://www.chinawriter.com.cn/",
    )

    assert len(items) == 1
    assert items[0].published_at == ""


def test_future_same_day_clock_is_not_accepted() -> None:
    html = """
    <div><a href='/news/102100003.html'>未来时刻不能被当作已发布证据的文章</a>
      <span>今天 23:59</span></div>
    """
    items = _parse_and_enrich(html, source_id="yicai", homepage="https://www.yicai.com/")

    assert len(items) == 1
    assert items[0].published_at == ""
