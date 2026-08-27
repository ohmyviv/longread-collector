"""Chinese route-portfolio contracts for paired natural metadata Shadow.

The contracts are intentionally separate from ``source_registry`` and Control
route configuration.  They describe Treatment-only first-party metadata
surfaces.  No surface in this module can enter candidate selection or body
extraction in S1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ROUTE_SHADOW_CONTRACT_VERSION = "zh-route-shadow-contract-v1"
S1_BODY_MODE = "metadata_only"


class SurfaceRole(StrEnum):
    CORE_EDITORIAL = "core_editorial"
    BREADTH_SAFETY = "breadth_safety"
    TIMESTAMP_ENRICHMENT = "timestamp_enrichment"
    NOISE_CONTROL = "noise_control"
    SPECIAL_PRODUCT = "special_product"


@dataclass(frozen=True, slots=True)
class RouteSurface:
    source_id: str
    surface_id: str
    publication_surface_id: str
    url: str
    transport: str  # section | rss
    role: SurfaceRole
    max_items: int
    s1_enabled: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class RoutePortfolio:
    source_id: str
    surfaces: tuple[RouteSurface, ...]

    def active_s1_surfaces(self) -> tuple[RouteSurface, ...]:
        return tuple(surface for surface in self.surfaces if surface.s1_enabled)


def _s(
    source_id: str,
    surface_id: str,
    publication_surface_id: str,
    url: str,
    transport: str,
    role: SurfaceRole,
    max_items: int,
    *,
    s1_enabled: bool = True,
    note: str = "",
) -> RouteSurface:
    return RouteSurface(
        source_id=source_id,
        surface_id=surface_id,
        publication_surface_id=publication_surface_id,
        url=url,
        transport=transport,
        role=role,
        max_items=max_items,
        s1_enabled=s1_enabled,
        note=note,
    )


PORTFOLIOS: dict[str, RoutePortfolio] = {
    "yicai": RoutePortfolio(
        source_id="yicai",
        surfaces=(
            _s("yicai", "yicai_finance", "yicai_finance", "https://www.yicai.com/news/jinrong/", "section", SurfaceRole.CORE_EDITORIAL, 20),
            _s("yicai", "yicai_kechuang", "yicai_kechuang", "https://www.yicai.com/news/kechuang/", "section", SurfaceRole.CORE_EDITORIAL, 20),
            _s("yicai", "yicai_auto", "yicai_auto", "https://www.yicai.com/news/automobile/", "section", SurfaceRole.CORE_EDITORIAL, 16),
            _s("yicai", "yicai_news_breadth", "yicai_news", "https://www.yicai.com/news/", "section", SurfaceRole.BREADTH_SAFETY, 24),
            _s("yicai", "yicai_info_control", "yicai_info", "https://www.yicai.com/news/info/", "section", SurfaceRole.NOISE_CONTROL, 16, note="fresh but historically micro-market/notice heavy"),
            _s("yicai", "yicai_commercial_control", "yicai_commercial", "https://www.yicai.com/news/ad/", "section", SurfaceRole.NOISE_CONTROL, 12, note="commercial-information surface; never a Standard Longread candidate surface"),
        ),
    ),
    "eeo": RoutePortfolio(
        source_id="eeo",
        surfaces=(
            _s("eeo", "eeo_business_industry", "eeo_business_industry", "https://www.eeo.com.cn/shangyechanye/", "section", SurfaceRole.CORE_EDITORIAL, 24),
            _s("eeo", "eeo_technology_plus", "eeo_technology_plus", "https://www.eeo.com.cn/jg/keji/", "section", SurfaceRole.CORE_EDITORIAL, 20),
            _s("eeo", "eeo_politics_rss", "eeo_politics", "https://www.eeo.com.cn/Politics/rss.xml", "rss", SurfaceRole.CORE_EDITORIAL, 20, note="official feed; S1 must quarantine if stale"),
            _s("eeo", "eeo_finance_rss", "eeo_finance", "https://www.eeo.com.cn/finance/rss.xml", "rss", SurfaceRole.CORE_EDITORIAL, 20, note="official feed; S1 must quarantine if stale"),
            _s("eeo", "eeo_industry_rss", "eeo_industry", "https://www.eeo.com.cn/industry/rss.xml", "rss", SurfaceRole.CORE_EDITORIAL, 20, note="official feed; S1 must quarantine if stale"),
            _s("eeo", "eeo_root_rss_control", "eeo_root_feed", "https://app.eeo.com.cn/rss.php", "rss", SurfaceRole.NOISE_CONTROL, 24, note="fresh negative control with observed stock/ETF-flow contamination"),
            _s("eeo", "eeo_epaper_special", "eeo_epaper", "https://app.eeo.com.cn/?action=wxpaper_index&app=hfive&controller=wxpaper", "section", SurfaceRole.SPECIAL_PRODUCT, 8, s1_enabled=False, note="distinct paid newspaper product; identity is not generic EEO web coverage"),
        ),
    ),
    "caixin": RoutePortfolio(
        source_id="caixin",
        surfaces=(
            _s("caixin", "caixin_companies", "caixin_companies", "https://companies.caixin.com/news/", "section", SurfaceRole.CORE_EDITORIAL, 24),
            _s("caixin", "caixin_finance", "caixin_finance", "https://finance.caixin.com/news/", "section", SurfaceRole.CORE_EDITORIAL, 24),
            _s("caixin", "caixin_china", "caixin_china", "https://china.caixin.com/news/", "section", SurfaceRole.CORE_EDITORIAL, 24),
            _s("caixin", "caixin_latest", "caixin_latest", "https://www.caixin.com/latestnews/", "section", SurfaceRole.BREADTH_SAFETY, 24),
            _s("caixin", "caixin_promotion_control", "caixin_promotion", "https://promote.caixin.com/news/", "section", SurfaceRole.NOISE_CONTROL, 12, note="promotion subdomain; must never prove generic Caixin editorial coverage"),
            _s("caixin", "caixin_deepview_special", "caixin_deepview", "https://deepview.caixin.com/topic/BQ02.000007864.html", "section", SurfaceRole.SPECIAL_PRODUCT, 8, s1_enabled=False, note="distinct Deepview/商圈 product surface"),
        ),
    ),
    "jiemian-depth": RoutePortfolio(
        source_id="jiemian-depth",
        surfaces=(
            _s("jiemian-depth", "jiemian_medicine", "jiemian_medicine", "https://www.jiemian.com/lists/472.html", "section", SurfaceRole.CORE_EDITORIAL, 24),
            _s("jiemian-depth", "jiemian_consumer", "jiemian_consumer", "https://www.jiemian.com/lists/31.html", "section", SurfaceRole.CORE_EDITORIAL, 20),
            _s("jiemian-depth", "jiemian_health_face", "jiemian_health_face", "https://www.jiemian.com/lists/441.html", "section", SurfaceRole.CORE_EDITORIAL, 16, note="health investigative/feature surface; freshness must be measured rather than assumed"),
            _s("jiemian-depth", "jiemian_health", "jiemian_health", "https://www.jiemian.com/lists/854.html", "section", SurfaceRole.BREADTH_SAFETY, 16, note="health breadth surface; retained only if live route proves current"),
        ),
    ),
}


def portfolio_for(source_id: str) -> RoutePortfolio | None:
    return PORTFOLIOS.get(str(source_id or "").strip())


def active_s1_surfaces(source_id: str) -> tuple[RouteSurface, ...]:
    portfolio = portfolio_for(source_id)
    return portfolio.active_s1_surfaces() if portfolio else ()


__all__ = [
    "PORTFOLIOS",
    "ROUTE_SHADOW_CONTRACT_VERSION",
    "S1_BODY_MODE",
    "RoutePortfolio",
    "RouteSurface",
    "SurfaceRole",
    "active_s1_surfaces",
    "portfolio_for",
]
