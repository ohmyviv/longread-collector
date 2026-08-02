from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from longread_collector.models import DiscoveredURL
from longread_collector.operational_hotfix import (
    allocate_fallback_budget,
    registered_domain_label,
    resolve_source_name,
    scheduled_run_metrics,
)


class FakeStore:
    def __init__(self, total: int, groups: dict[str, int]) -> None:
        self.total = total
        self.groups = groups

    def count_firecrawl_scrapes_today(self, query_group: str | None = None) -> int:
        if query_group:
            return self.groups.get(query_group, 0)
        return self.total


def runtime() -> SimpleNamespace:
    return SimpleNamespace(
        firecrawl_fallback_daily_limit=3,
        firecrawl_fallback_intl_early_limit=0,
        firecrawl_fallback_pre_report_limit=1,
        firecrawl_fallback_zh_midday_limit=1,
        firecrawl_fallback_zh_evening_limit=1,
    )


def test_public_suffix_resolution_avoids_generic_com_org() -> None:
    assert registered_domain_label("caijing.com.cn") == "caijing"
    assert registered_domain_label("chinadevelopmentbrief.org.cn") == "chinadevelopmentbrief"
    assert registered_domain_label("www.eeo.com.cn") == "eeo"


def test_registry_source_name_wins_over_generic_extraction_metadata() -> None:
    discovered = DiscoveredURL(
        url="https://caijing.com.cn/article/123",
        metadata={"source_id": "caijing", "source_name": "财经杂志"},
    )
    assert resolve_source_name(discovered, {"publisher": "com"}, "caijing.com.cn") == "财经杂志"


def test_source_id_precedes_psl_fallback_when_registry_name_missing() -> None:
    discovered = DiscoveredURL(
        url="https://eeo.com.cn/article/123",
        metadata={"source_id": "eeo"},
    )
    assert resolve_source_name(discovered, {}, "eeo.com.cn") == "eeo"


def test_schedule_delay_uses_configured_query_time() -> None:
    started = datetime(2026, 7, 31, 14, 34, 47, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = scheduled_run_metrics(
        started,
        [{"scheduled_time_bj": "11:50"}],
        "zh_midday",
    )
    assert result["scheduled_at_bj"] == "2026-07-31 11:50:00"
    assert result["start_delay_seconds"] == 9887


def test_late_night_schedule_rolls_to_previous_day() -> None:
    started = datetime(2026, 8, 1, 0, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = scheduled_run_metrics(started, [], "intl_early")
    assert result["scheduled_at_bj"] == "2026-07-31 22:30:00"
    assert result["start_delay_seconds"] == 6000


def test_group_reservation_preserves_later_run_capacity() -> None:
    allocation = allocate_fallback_budget(
        FakeStore(total=1, groups={"zh_midday": 0}),
        runtime(),
        "zh_midday",
    )
    assert allocation.group_cap == 1
    assert allocation.remaining == 1


def test_group_cannot_exceed_its_reserved_cap() -> None:
    allocation = allocate_fallback_budget(
        FakeStore(total=1, groups={"pre_report": 1}),
        runtime(),
        "pre_report",
    )
    assert allocation.remaining == 0


def test_intl_early_has_no_reserved_scrape_budget() -> None:
    allocation = allocate_fallback_budget(
        FakeStore(total=0, groups={}),
        runtime(),
        "intl_early",
    )
    assert allocation.group_cap == 0
    assert allocation.remaining == 0
