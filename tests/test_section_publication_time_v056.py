from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.effective_route_v056 import parse_section_html_v056
from longread_collector.freshness_policy_v056f import evaluate_freshness_policy
from longread_collector.freshness_v056 import collect_date_evidence
from longread_collector.section_publication_time_v056 import (
    SECTION_PUBLICATION_CLOCK_KEY,
    SECTION_PUBLICATION_CLOCK_SOURCE,
    SECTION_PUBLICATION_TIME_VERSION,
    enrich_section_publication_times,
)
from longread_collector.source_run_coverage import build_source_run_coverage_rows

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


def _parse(
    html: str, *, source_id: str, homepage: str
):
    source = _source(source_id, homepage)
    items = parse_section_html_v056(
        html,
        source=source,
        endpoint=homepage,
        limit=24,
    )
    for item in items:
        item.metadata.setdefault("source_id", source_id)
        item.metadata.setdefault("purpose", "native_source_scan")
        item.metadata.setdefault("native_method", "section_scan")
    return source, items


def _parse_and_enrich(
    html: str, *, source_id: str, homepage: str
):
    source, items = _parse(html, source_id=source_id, homepage=homepage)
    return enrich_section_publication_times(
        html,
        source=source,
        endpoint=homepage,
        items=items,
        observed_at=OBSERVED,
    )


def test_yicai_clock_is_telemetry_only_and_does_not_mutate_published_at() -> None:
    html = """
    <div class='card'><a href='/news/102100001.html'>第一篇足够长的第一财经文章标题</a>
      <span>摘要文字</span><span>昨天 18:08</span></div>
    <div class='card'><a href='/news/102100002.html'>第二篇足够长的第一财经文章标题</a>
      <span>今天 08:54</span></div>
    """
    items = _parse_and_enrich(html, source_id="yicai", homepage="https://www.yicai.com/")

    assert [item.published_at for item in items] == ["", ""]
    assert [item.metadata[SECTION_PUBLICATION_CLOCK_KEY] for item in items] == [
        "2026-08-17T18:08:00+08:00",
        "2026-08-18T08:54:00+08:00",
    ]
    assert all(
        item.metadata["section_publication_clock_source"]
        == SECTION_PUBLICATION_CLOCK_SOURCE
        for item in items
    )
    assert all(
        item.metadata["section_publication_time_version"]
        == SECTION_PUBLICATION_TIME_VERSION
        for item in items
    )
    assert all(
        item.metadata["section_publication_clock_confidence"] == "high"
        for item in items
    )


def test_jiemian_exact_clock_is_observed_but_vague_age_is_not() -> None:
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
    assert items[0].published_at == ""
    assert items[0].metadata[SECTION_PUBLICATION_CLOCK_KEY] == "2026-08-18T08:54:00+08:00"
    assert items[0].metadata["section_publication_clock_raw"] == "今天 08:54"
    assert items[1].published_at == ""
    assert SECTION_PUBLICATION_CLOCK_KEY not in items[1].metadata


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
    assert SECTION_PUBLICATION_CLOCK_KEY not in items[0].metadata


def test_chinawriter_remains_unobserved_even_if_generic_text_looks_dated() -> None:
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
    assert SECTION_PUBLICATION_CLOCK_KEY not in items[0].metadata


def test_future_same_day_clock_is_not_accepted() -> None:
    html = """
    <div><a href='/news/102100003.html'>未来时刻不能被当作已发布证据的文章</a>
      <span>今天 23:59</span></div>
    """
    items = _parse_and_enrich(html, source_id="yicai", homepage="https://www.yicai.com/")

    assert len(items) == 1
    assert items[0].published_at == ""
    assert SECTION_PUBLICATION_CLOCK_KEY not in items[0].metadata


def test_section_clock_is_not_consumed_by_control_freshness_evidence() -> None:
    html = """
    <div><a href='/news/102100004.html'>用于验证 freshness 隔离的一篇足够长文章标题</a>
      <span>今天 08:54</span></div>
    """
    baseline_source, baseline_items = _parse(
        html,
        source_id="yicai",
        homepage="https://www.yicai.com/",
    )
    baseline = baseline_items[0]
    baseline_decision = evaluate_freshness_policy(
        baseline,
        phase="prefilter",
        now=OBSERVED,
    )

    observed_source, observed_items = _parse(
        html,
        source_id="yicai",
        homepage="https://www.yicai.com/",
    )
    observed = enrich_section_publication_times(
        html,
        source=observed_source,
        endpoint="https://www.yicai.com/",
        items=observed_items,
        observed_at=OBSERVED,
    )[0]
    observed_decision = evaluate_freshness_policy(
        observed,
        phase="prefilter",
        now=OBSERVED,
    )

    assert observed.published_at == baseline.published_at == ""
    assert collect_date_evidence(observed) == collect_date_evidence(baseline)
    assert (
        observed_decision.allowed,
        observed_decision.reject_reason,
        observed_decision.track,
        observed_decision.unknown,
        observed_decision.score_ordinal,
        observed_decision.score_penalty,
    ) == (
        baseline_decision.allowed,
        baseline_decision.reject_reason,
        baseline_decision.track,
        baseline_decision.unknown,
        baseline_decision.score_ordinal,
        baseline_decision.score_penalty,
    )


def test_source_run_coverage_consumes_isolated_section_clock() -> None:
    html = """
    <div><a href='/news/102100005.html'>用于 coverage horizon 的一篇足够长文章标题</a>
      <span>今天 08:54</span></div>
    """
    source, items = _parse(
        html,
        source_id="yicai",
        homepage="https://www.yicai.com/",
    )
    item = enrich_section_publication_times(
        html,
        source=source,
        endpoint="https://www.yicai.com/",
        items=items,
        observed_at=OBSERVED,
    )[0]

    rows = build_source_run_coverage_rows(
        run_id="COL-20260818-181236-BJT-zh_evening",
        query_group="zh_evening",
        started=OBSERVED,
        selected_sources=[source],
        native_logs=[
            {
                "source_id": "yicai",
                "success": True,
                "results_count": 1,
                "selected_method": "section_scan",
                "selected_endpoint": "https://www.yicai.com/",
                "attempts": [],
                "fallback_needed": False,
            }
        ],
        native_items=[item],
        firecrawl_logs=[],
        firecrawl_items=[],
        persisted_at=OBSERVED,
    )

    assert len(rows) == 1
    row = rows[0]
    assert item.published_at == ""
    assert row["dated_observation_count"] == 1
    assert row["route_status"] == "native_covered"
    assert row["oldest_observed_published_at"] == "2026-08-18 08:54:00"
    assert row["newest_observed_published_at"] == "2026-08-18 08:54:00"
    assert row["observed_horizon_hours"] == 9.31
    assert row["coverage_confidence"] == "lower_bound"
