import asyncio
from datetime import datetime
from types import SimpleNamespace

from longread_collector.effective_route_extensions_v056 import (
    BJNEWS_EFFECTIVE_ROUTES,
    BJNEWS_NEWS_PAGES,
    JIEMIAN_EFFECTIVE_ROUTES,
    THEPAPER_API_ENDPOINT,
    THEPAPER_EFFECTIVE_ROUTES,
    _bjnews_published_at,
    _discover_thepaper,
    apply_effective_route_fix,
    merge_route_items,
    truthful_route_metrics,
)
from longread_collector.effective_route_smoke_v056 import partition_target_urls


def source(source_id: str):
    return {
        "source_id": source_id,
        "source_name": source_id,
        "language": "zh",
        "homepage_url": "https://example.com/",
        "priority_tier": "rotate",
        "enabled": "TRUE",
        "subject_groups": "business|public_policy",
        "discovery_method": ["section_scan", "firecrawl_search"],
        "parser_config_json": {
            "section_urls": [],
            "fallback_order": ["section_scan", "firecrawl_search"],
        },
    }


def result(source_id: str, suffix: str, rank: int, published_at: str = ""):
    return SimpleNamespace(
        url=f"https://example.com/article/{suffix}",
        rank=rank,
        published_at=published_at,
        metadata={"source_id": source_id},
    )


def test_source_specific_route_contracts_are_bounded_and_ordered() -> None:
    jiemian = apply_effective_route_fix(source("jiemian-depth"))
    assert jiemian["parser_config_json"]["section_urls"] == JIEMIAN_EFFECTIVE_ROUTES
    assert jiemian["parser_config_json"]["metadata_limit"] == 96
    assert "lists/506.html" in JIEMIAN_EFFECTIVE_ROUTES[0]
    assert all("_2.html" not in url for url in JIEMIAN_EFFECTIVE_ROUTES)

    bjnews = apply_effective_route_fix(source("bjnews-depth"))
    assert bjnews["parser_config_json"]["section_urls"] == BJNEWS_EFFECTIVE_ROUTES
    assert bjnews["parser_config_json"]["metadata_limit"] == 64
    assert BJNEWS_EFFECTIVE_ROUTES[0].endswith("/depth")
    assert len(BJNEWS_NEWS_PAGES) == 31
    assert BJNEWS_NEWS_PAGES[-1].endswith("/31.html")

    thepaper = apply_effective_route_fix(source("thepaper"))
    assert thepaper["parser_config_json"]["section_urls"] == THEPAPER_EFFECTIVE_ROUTES
    assert thepaper["parser_config_json"]["metadata_limit"] == 240
    assert thepaper["parser_config_json"]["api_endpoint"] == THEPAPER_API_ENDPOINT
    assert thepaper["parser_config_json"]["api_node_ids"] == [25462, 25448]


def test_bjnews_article_id_restores_approximate_creation_time() -> None:
    observed = _bjnews_published_at(
        "https://www.bjnews.com.cn/detail/1785144458129453.html"
    )
    assert observed is not None
    # The ID timestamp predates the page's displayed publication time, so it is
    # a medium-confidence creation/freshness signal rather than exact publish time.
    assert observed.strftime("%Y-%m-%d %H:%M") == "2026-07-27 17:27"


def test_high_volume_sources_use_declared_priority_not_round_robin() -> None:
    groups = [
        [result("bjnews-depth", f"depth-{index}", index + 1) for index in range(20)],
        [result("bjnews-depth", f"news-{index}", index + 1) for index in range(20)],
    ]
    merged = merge_route_items(groups, limit=24)
    assert [item.url.rsplit("/", 1)[-1] for item in merged[:20]] == [
        f"depth-{index}" for index in range(20)
    ]
    assert [item.url.rsplit("/", 1)[-1] for item in merged[20:]] == [
        f"news-{index}" for index in range(4)
    ]


def test_undated_section_route_is_partial_not_effective() -> None:
    metrics = truthful_route_metrics(
        [result("jiemian-depth", f"item-{index}", index + 1) for index in range(12)],
        started=datetime(2026, 8, 2, 8, 0, 0),
        method="section_scan",
    )
    assert metrics["native_route_status"] == "partial_native"
    assert metrics["effective_native_success"] is False
    assert metrics["oldest_item_at"] == ""


def test_route_smoke_targets_follow_the_same_seven_day_window() -> None:
    before_expiry, expired_before = partition_target_urls(
        started=datetime(2026, 8, 2, 22, 23),
        freshness_days=7,
    )
    target = "https://www.thepaper.cn/newsDetail_forward_33660139"
    assert target in before_expiry["thepaper"]
    assert target not in expired_before.get("thepaper", set())

    after_expiry, expired_after = partition_target_urls(
        started=datetime(2026, 8, 2, 22, 25),
        freshness_days=7,
    )
    assert target not in after_expiry.get("thepaper", set())
    assert target in expired_after["thepaper"]
    assert "https://www.thepaper.cn/newsDetail_forward_33664738" in after_expiry[
        "thepaper"
    ]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.headers = {"content-type": "application/json;charset=UTF-8"}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeThePaperClient:
    def __init__(self):
        self.payloads = []

    async def post(self, endpoint, *, json, headers):
        assert endpoint == THEPAPER_API_ENDPOINT
        assert headers["Origin"] == "https://www.thepaper.cn"
        self.payloads.append(dict(json))
        node = json["nodeId"]
        cursor = json.get("startTime")
        if node == 25462 and cursor is None:
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "hasNext": True,
                        "startTime": 111,
                        "list": [
                            {
                                "contId": "33670000",
                                "name": "Current politics article",
                                "pubTimeLong": 1785204243588,
                            }
                        ],
                    },
                }
            )
        if node == 25462 and cursor == 111:
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "hasNext": False,
                        "startTime": 110,
                        "list": [
                            {
                                "contId": "33664738",
                                "name": "多地推进处改科遏制头衔通货膨胀",
                                "pubTimeLong": 1785109209642,
                            }
                        ],
                    },
                }
            )
        if node == 25448:
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "hasNext": False,
                        "startTime": 222,
                        "list": [
                            {
                                "contId": "33660139",
                                "name": "意定监护老年情感困境前浪2",
                                "pubTimeLong": 1785075884103,
                            }
                        ],
                    },
                }
            )
        raise AssertionError(f"unexpected payload: {json}")


def test_thepaper_cursor_route_uses_start_time_and_exact_dates() -> None:
    client = FakeThePaperClient()
    items, log = asyncio.run(
        _discover_thepaper(
            None,
            client,
            source("thepaper"),
            limit=24,
            started=datetime(2026, 8, 2, 8, 0, 0),
            freshness_days=7,
        )
    )
    urls = {item.url for item in items}
    assert "https://www.thepaper.cn/newsDetail_forward_33664738" in urls
    assert "https://www.thepaper.cn/newsDetail_forward_33660139" in urls
    assert {payload.get("startTime") for payload in client.payloads} == {None, 111}
    assert log.success is True
    assert log.selected_method == "api_cursor"
    assert log.fallback_needed is False
    target = next(item for item in items if item.url.endswith("33664738"))
    assert target.published_at.startswith("2026-07-27 07:40")
    assert target.metadata["published_at_source"] == "thepaper_api_pubTimeLong"
    assert target.metadata["published_at_confidence"] == "high"
