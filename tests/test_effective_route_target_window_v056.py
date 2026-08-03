from datetime import datetime

from longread_collector.effective_route_smoke_v056 import partition_target_urls

BJNEWS_OLD = "https://www.bjnews.com.cn/detail/1785144458129453.html"
BJNEWS_NEWER = "https://www.bjnews.com.cn/detail/1785199934129721.html"


def test_bjnews_unix_id_target_expires_at_real_seven_day_boundary() -> None:
    active, expired = partition_target_urls(
        started=datetime(2026, 8, 3, 21, 0, 0),
        freshness_days=7,
    )
    assert BJNEWS_OLD in expired["bjnews-depth"]
    assert BJNEWS_OLD not in active.get("bjnews-depth", set())
    assert BJNEWS_NEWER in active["bjnews-depth"]


def test_bjnews_target_remains_active_before_exact_boundary() -> None:
    active, expired = partition_target_urls(
        started=datetime(2026, 8, 3, 17, 27, 38),
        freshness_days=7,
    )
    assert BJNEWS_OLD in active["bjnews-depth"]
    assert BJNEWS_OLD not in expired.get("bjnews-depth", set())
