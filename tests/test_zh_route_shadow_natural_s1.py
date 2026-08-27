from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from longread_collector.models import DiscoveredURL
from longread_collector.native_discovery import NativeDiscoveryBatch
from longread_collector.quality_aware_reserve_replay_v1 import (
    tier1_micro_market_reason,
)
from longread_collector.zh_route_shadow_contracts_v1 import (
    PORTFOLIOS,
    S1_BODY_MODE,
    SurfaceRole,
    active_s1_surfaces,
)
import longread_collector.zh_route_shadow_discovery_v1 as shadow_discovery
from longread_collector.zh_route_shadow_discovery_v1 import (
    PairedZhRouteShadowDiscovery,
    ShadowRouteItem,
    ZhRouteShadowReport,
    _surface_status,
    begin_zh_route_shadow,
    current_zh_route_shadow_state,
    discover_treatment_metadata,
    end_zh_route_shadow,
    parse_shadow_feed,
    parse_shadow_section_html,
)
from longread_collector.zh_route_shadow_telemetry_v1 import _item_rows

TZ = ZoneInfo("Asia/Shanghai")
OBSERVED = datetime(2026, 8, 27, 12, 0, tzinfo=TZ)


def _source(source_id: str) -> dict[str, str]:
    homes = {
        "yicai": "https://www.yicai.com/",
        "eeo": "https://www.eeo.com.cn/",
        "caixin": "https://www.caixin.com/",
        "jiemian-depth": "https://www.jiemian.com/",
        "huxiu": "https://www.huxiu.com/",
    }
    return {
        "source_id": source_id,
        "source_name": source_id,
        "language": "zh",
        "homepage_url": homes[source_id],
        "priority_tier": "rotate",
    }


def _surface(source_id: str, surface_id: str):
    return next(
        surface
        for surface in PORTFOLIOS[source_id].surfaces
        if surface.surface_id == surface_id
    )


def test_s1_portfolios_are_treatment_only_and_special_products_are_inactive() -> None:
    assert set(PORTFOLIOS) == {"yicai", "eeo", "caixin", "jiemian-depth"}
    assert S1_BODY_MODE == "metadata_only"
    assert all(
        surface.role is not SurfaceRole.SPECIAL_PRODUCT
        for source_id in PORTFOLIOS
        for surface in active_s1_surfaces(source_id)
    )
    assert any(
        surface.role is SurfaceRole.NOISE_CONTROL
        for source_id in PORTFOLIOS
        for surface in active_s1_surfaces(source_id)
    )


def test_frozen_route_regression_surfaces_are_present() -> None:
    assert _surface("yicai", "yicai_kechuang").url.endswith("/news/kechuang/")
    assert _surface("eeo", "eeo_business_industry").url.endswith("/shangyechanye/")
    assert _surface("caixin", "caixin_companies").url == "https://companies.caixin.com/news/"
    assert _surface("jiemian-depth", "jiemian_medicine").url.endswith("/lists/472.html")


def test_jiemian_listing_recovers_exact_month_day_clock() -> None:
    surface = _surface("jiemian-depth", "jiemian_medicine")
    body = """
    <div class='card'>
      <a href='/article/11800001.html'>首个国产基因疗法的商业困局：打五折仍零处方</a>
      <span>08/25 09:28</span>
    </div>
    """
    items = parse_shadow_section_html(
        body,
        source=_source("jiemian-depth"),
        surface=surface,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert len(items) == 1
    assert items[0].published_at.startswith("2026-08-25T09:28")
    assert items[0].publication_time_confidence == "high"
    assert items[0].within_freshness is True


def test_yicai_relative_clock_is_resolved_without_body_fetch() -> None:
    surface = _surface("yicai", "yicai_finance")
    body = """
    <a href='/news/103015243.html'>一篇有足够标题长度的第一财经文章</a>
    <span>昨天 21:51</span>
    """
    items = parse_shadow_section_html(
        body,
        source=_source("yicai"),
        surface=surface,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert items[0].published_at.startswith("2026-08-26T21:51")
    assert items[0].within_freshness is True


def test_unknown_publication_time_is_observed_but_not_counted_as_proven_recent() -> None:
    surface = _surface("yicai", "yicai_finance")
    body = "<a href='/news/103015244.html'>没有任何发布时间证据的编辑文章</a>"
    items = parse_shadow_section_html(
        body,
        source=_source("yicai"),
        surface=surface,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert len(items) == 1
    assert items[0].published_at == ""
    assert items[0].within_freshness is False
    assert _surface_status(items, request_success=True) == "date_unknown"


def test_stale_eeo_rss_is_not_false_healthy_coverage() -> None:
    surface = _surface("eeo", "eeo_politics_rss")
    rss = """<?xml version='1.0' encoding='utf-8'?>
    <rss version='2.0'><channel><title>EEO</title>
      <item><title>十年前的政经旧稿仍能正常解析</title>
        <link>https://www.eeo.com.cn/2016/0825/300001.shtml</link>
        <pubDate>Thu, 25 Aug 2016 08:00:00 +0800</pubDate>
      </item>
    </channel></rss>"""
    items = parse_shadow_feed(
        rss,
        source=_source("eeo"),
        surface=surface,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert len(items) == 1
    assert items[0].within_freshness is False
    assert _surface_status(items, request_success=True) == "stale_surface"


def test_micro_market_detector_does_not_penalize_generic_etf_reporting() -> None:
    assert tier1_micro_market_reason("东方红、中欧新入局，ETF赛道迎来最后的头部玩家") == ""
    assert (
        tier1_micro_market_reason("创新药ETF华泰柏瑞净申购600万份，建议关注溢价率")
        == "etf_transaction_snapshot"
    )


def test_caixin_promotion_surface_is_explicit_noise_not_editorial_coverage() -> None:
    promotion = _surface("caixin", "caixin_promotion_control")
    items = parse_shadow_section_html(
        "<a href='/2026-08-27/102300001.html'>品牌合作商业推广内容样本</a><span>2026-08-27 08:30</span>",
        source=_source("caixin"),
        surface=promotion,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert len(items) == 1
    assert items[0].noise_reason == "commercial_surface"

    companies = _surface("caixin", "caixin_companies")
    cross_surface = parse_shadow_section_html(
        "<a href='https://promote.caixin.com/2026-08-27/102300002.html'>不应被公司频道吸收的推广稿</a>",
        source=_source("caixin"),
        surface=companies,
        observed_at=OBSERVED,
        freshness_days=7,
    )
    assert cross_surface == []


def test_treatment_runs_only_for_naturally_selected_target_sources_and_uses_zero_body_requests() -> None:
    report = asyncio.run(
        discover_treatment_metadata(
            [_source("huxiu")],
            control_items=[],
            group_id="zh_midday",
            started=OBSERVED,
            freshness_days=7,
            timeout=1,
            concurrency=1,
        )
    )
    assert report.status == "no_treatment_source_selected"
    assert report.treatment_source_ids == []
    assert report.metadata_requests == 0
    assert report.body_requests == 0


def test_paired_treatment_failure_returns_control_batch_unchanged(monkeypatch) -> None:
    control_item = DiscoveredURL(
        url="https://www.eeo.com.cn/2026/0827/700001.shtml",
        title="Control article",
        language="zh",
    )
    control = NativeDiscoveryBatch(
        items=[control_item],
        logs=[{"source_id": "eeo", "success": True}],
        fallback_sources=[],
    )

    async def fake_control(self, sources, *, limit_per_source, started, freshness_days):
        return control

    async def failing_treatment(*args, **kwargs):
        raise RuntimeError("treatment exploded")

    monkeypatch.setattr(
        shadow_discovery.EffectiveRouteDiscovery,
        "discover",
        fake_control,
    )
    monkeypatch.setattr(
        shadow_discovery,
        "discover_treatment_metadata",
        failing_treatment,
    )

    token = begin_zh_route_shadow(enabled=True, group_id="zh_midday")
    try:
        discovery = PairedZhRouteShadowDiscovery(timeout=1, concurrency=1)
        result = asyncio.run(
            discovery.discover(
                [_source("eeo")],
                limit_per_source=24,
                started=OBSERVED,
                freshness_days=7,
            )
        )
        state = current_zh_route_shadow_state()
        assert result is control
        assert result.items == [control_item]
        assert state is not None
        assert state.report is None
        assert "treatment exploded" in state.error
    finally:
        end_zh_route_shadow(token)


def test_same_canonical_article_keeps_multi_surface_provenance_in_item_ledger() -> None:
    canonical = "https://companies.caixin.com/2026-08-27/102300003.html"
    common = dict(
        source_id="caixin",
        surface_role="core_editorial",
        publication_surface_id="caixin_companies",
        transport="section",
        url=canonical,
        url_canonical=canonical,
        title="同一篇文章被两个表面观察到",
        published_at="2026-08-27T08:00:00+08:00",
        publication_time_source="listing_absolute_clock",
        publication_time_confidence="high",
        rank=1,
        within_freshness=True,
    )
    items = [
        ShadowRouteItem(surface_id="caixin_companies", endpoint="https://companies.caixin.com/news/", **common),
        ShadowRouteItem(surface_id="caixin_latest", endpoint="https://www.caixin.com/latestnews/", **common),
    ]
    report = ZhRouteShadowReport(
        version="zh-route-shadow-discovery-v1",
        contract_version="zh-route-shadow-contract-v1",
        body_mode="metadata_only",
        group_id="zh_midday",
        started_at_bj="2026-08-27 11:50:00",
        observed_at_bj="2026-08-27 11:50:05",
        selected_source_ids=["caixin"],
        treatment_source_ids=["caixin"],
        surfaces_attempted=2,
        metadata_requests=2,
        body_requests=0,
        items=items,
    )
    rows = _item_rows(report, collector_run_id="COL-test", persisted_at=OBSERVED)
    assert len(rows) == 2
    assert rows[0]["route_shadow_item_id"] != rows[1]["route_shadow_item_id"]
    assert {row["surface_id"] for row in rows} == {"caixin_companies", "caixin_latest"}


def test_workflow_keeps_production_boundaries_frozen_when_s1_is_enabled() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/collector.yml").read_text()
    assert "ZH_ROUTE_SHADOW_ENABLED: 'true'" in workflow
    assert "ZH_ROUTE_SHADOW_BODY_MODE: metadata_only" in workflow
    assert "MAX_URLS_PER_RUN: '32'" in workflow
    assert "V06_PRIMARY_ENABLED: 'false'" in workflow
    assert "AUTO_PROMOTE_WHEN_READY: 'false'" in workflow
    assert "EDITOR_0735_CONNECTED: 'false'" in workflow
