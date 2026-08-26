"""Offline/Shadow-only Chinese route experiment contract.

This module deliberately does not patch ``source_registry`` or production route
selection.  It freezes candidate first-party surfaces and a common evaluation
rubric so route experiments can be compared without silently changing the
Collector's live discovery path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

EXPERIMENT_VERSION = "zh-route-shadow-v0.1"


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    source_id: str
    route_id: str
    url: str
    route_kind: str
    role: str = "candidate"  # candidate | negative_control
    note: str = ""


@dataclass(frozen=True, slots=True)
class RouteObservation:
    route_id: str
    total_items: int
    known_miss_hits: int
    timestamped_items: int
    high_value_items: int
    noise_items: int
    metadata_requests: int = 1

    @property
    def timestamp_observability(self) -> float:
        return self.timestamped_items / self.total_items if self.total_items else 0.0

    @property
    def high_value_yield(self) -> float:
        return self.high_value_items / self.total_items if self.total_items else 0.0

    @property
    def noise_rate(self) -> float:
        return self.noise_items / self.total_items if self.total_items else 0.0

    @property
    def known_miss_recovery_per_request(self) -> float:
        return self.known_miss_hits / max(1, self.metadata_requests)


ROUTES: tuple[RouteCandidate, ...] = (
    # 第一财经: broad editorial listing plus two topical sections.  The
    # ``info`` feed is retained only as a negative control because observed
    # results were dominated by stock notices / market-flow snippets.
    RouteCandidate("yicai", "yicai_news", "https://www.yicai.com/news/", "section"),
    RouteCandidate("yicai", "yicai_kechuang", "https://www.yicai.com/news/kechuang", "section"),
    RouteCandidate("yicai", "yicai_jinrong", "https://www.yicai.com/news/jinrong/", "section"),
    RouteCandidate("yicai", "yicai_info_control", "https://www.yicai.com/news/info/", "section", "negative_control", "high micro-market / notice noise"),

    # 经济观察报: current department / author surfaces are evaluated against
    # the noisy root RSS.  Author routes are experiments, not a proposed fixed
    # production roster.
    RouteCandidate("eeo", "eeo_business_industry", "https://www.eeo.com.cn/shangyechanye/", "section"),
    RouteCandidate("eeo", "eeo_health_author_liuxiaonuo", "https://space.eeo.com.cn/liuxiaonuo", "author"),
    RouteCandidate("eeo", "eeo_rss_control", "https://app.eeo.com.cn/rss.php", "rss", "negative_control", "observed stock/ETF-flow dominance"),

    # 财新: deterministic channel listings.  Deepview/商圈 is intentionally
    # not collapsed into generic Caixin news because it is a distinct surface.
    RouteCandidate("caixin", "caixin_latest", "https://www.caixin.com/latestnews/", "section"),
    RouteCandidate("caixin", "caixin_companies", "https://companies.caixin.com/news/", "section"),
    RouteCandidate("caixin", "caixin_china", "https://china.caixin.com/news/", "section"),
    RouteCandidate("caixin", "caixin_finance", "https://finance.caixin.com/news", "section"),
    RouteCandidate("caixin", "caixin_deepview_business_circle", "https://deepview.caixin.com/topic/BQ02.000007864.html", "topic", note="separate JS-heavy product surface"),

    # 界面: medical / health surfaces omitted by the current v0.5.6 route scope.
    RouteCandidate("jiemian-depth", "jiemian_medicine", "https://www.jiemian.com/lists/472.html", "section"),
    RouteCandidate("jiemian-depth", "jiemian_health", "https://www.jiemian.com/lists/854.html", "section"),
    RouteCandidate("jiemian-depth", "jiemian_health_face", "https://www.jiemian.com/lists/441.html", "section"),
)


def routes_for(source_id: str, *, include_negative_controls: bool = True) -> list[RouteCandidate]:
    return [
        route for route in ROUTES
        if route.source_id == source_id
        and (include_negative_controls or route.role != "negative_control")
    ]


def observation_score(observation: RouteObservation) -> tuple[float, ...]:
    """Rank routes by recovery/value before breadth.

    Primary objective is high-value known-miss recovery per metadata request;
    timestamp observability and low noise break ties.  This is an experiment
    score only and is not a production route-selection function.
    """
    return (
        observation.known_miss_recovery_per_request,
        observation.high_value_yield,
        observation.timestamp_observability,
        -observation.noise_rate,
        -float(observation.metadata_requests),
    )


def rank_observations(observations: Iterable[RouteObservation]) -> list[RouteObservation]:
    return sorted(observations, key=observation_score, reverse=True)


__all__ = [
    "EXPERIMENT_VERSION",
    "ROUTES",
    "RouteCandidate",
    "RouteObservation",
    "observation_score",
    "rank_observations",
    "routes_for",
]
