"""Rank v0.5.6 candidates with resolved dates and editorial utility.

The freshness policy remains authoritative.  This module adds a transparent
pre-extraction editorial score so the portfolio can compare curated reporting,
special documents and low-value search results without source allowlists.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from . import ranked_selection_v056 as _ranked
from .freshness_policy_v056f import evaluate_freshness_policy
from .models import DiscoveredURL
from .ranked_selection_v055 import _score as _legacy_score

RANKING_FRESHNESS_VERSION = "editorial-resolved-ranking-v0.5.6g"

_STRONG_REPORTING_RE = re.compile(
    r"(?:暗访|起底|实测|调查报道|独家调查|深度调查|深度报道|特稿|专访|"
    r"追踪|产业链|灰色产业|逝者|观势|困境|背后|转型|格局|挑战|"
    r"为什么|为何|怎么|如何|审批节奏)|"
    r"\b(?:investigation|investigative|inside|in[- ]depth|longform|feature|"
    r"analysis|explainer|interview|reveals?|uncovers?|what if|why|how|"
    r"after decades|fight for|backlash|warning|failures?)\b",
    re.I,
)
_FEATURE_PATH_RE = re.compile(
    r"/(?:features?|investigations?|longreads?|magazine|ideas|critics-notebook|"
    r"open-questions|the-weekend-essay|the-lede)(?:/|$)",
    re.I,
)
_LOW_VALUE_FORMAT_RE = re.compile(
    r"/(?:podcasts?|audio|newsletters?|digest)(?:/|$)|"
    r"\b(?:podcast|audio edition|newsletter|behind the blog|weekly roundup|"
    r"press release|webinar|event recap)\b|(?:播客节目|音频版|每周简报|新闻发布会)",
    re.I,
)
_SPECIAL_MATERIAL_RE = re.compile(
    r"\.pdf(?:$|[?#])|/(?:doi|publication|publications|journal|lawreview)/|"
    r"/(?:science/article/pii|articles/PMC\d+)|"
    r"\b(?:review paper|systematic review|academic paper|working paper|"
    r"cited by|journal article|literature review)\b|"
    r"(?:论文导读|学术论文|研究论文|期刊论文)",
    re.I,
)
_GENERIC_OVERVIEW_RE = re.compile(
    r"\b(?:overview|primer|roadmap|introduction|basics|high-level summary|"
    r"what is (?:an? )?|evidence and causes|comprehensive review|"
    r"recent advances)\b|"
    r"(?:研究中心|行业研究|新闻动态|蓝皮书发布会|报告发布会|基本情况|入门指南)",
    re.I,
)
_COMMERCIAL_RE = re.compile(
    r"\b(?:deal|sale|discount|coupon|flash sale|best price|buy now|shopping|"
    r"product comparison|tested products?|gift guide)\b|"
    r"(?:限时折扣|大促|优惠券|购买指南|产品对比|好价|测评清单)",
    re.I,
)
_PLACEHOLDER_TITLE_RE = re.compile(
    r"^(?:read more|learn more|click here|untitled|news|article|新闻动态|详情)$",
    re.I,
)
_DIGEST_PATH_RE = re.compile(r"/(?:digest|briefing|roundup)(?:/|$)", re.I)


def _editorial_components(
    item: DiscoveredURL,
    components: dict[str, int],
) -> dict[str, int]:
    parts = urlsplit(item.url)
    path = parts.path or "/"
    title = str(item.title or "").strip()
    description = str(item.description or "").strip()
    sample = f"{title}\n{description}\n{path}"
    selection = item.metadata.get("selection", {})
    freshness = item.metadata.get("freshness", {})

    native = str(item.metadata.get("purpose", "")) == "native_source_scan"
    method = str(item.discovery_method or item.metadata.get("native_method", ""))
    native_signal = 7 if native else 0
    if native and method in {"rss", "section_scan", "api_cursor", "reader_section"}:
        native_signal += 2

    reporting_signal = 0
    if _STRONG_REPORTING_RE.search(sample):
        reporting_signal += 9
    if _FEATURE_PATH_RE.search(path):
        reporting_signal += 8
    if "/article/" in path.lower() or "/news/" in path.lower():
        reporting_signal += 2

    special_material_penalty = 0
    special_track = str(
        selection.get("freshness_track") or freshness.get("freshness_track") or ""
    ) == "special_document"
    if special_track or _SPECIAL_MATERIAL_RE.search(sample):
        special_material_penalty = -10

    generic_overview_penalty = -8 if _GENERIC_OVERVIEW_RE.search(sample) else 0
    commercial_penalty = -18 if _COMMERCIAL_RE.search(sample) else 0
    low_value_format_penalty = -14 if _LOW_VALUE_FORMAT_RE.search(sample) else 0
    if _DIGEST_PATH_RE.search(path):
        low_value_format_penalty = min(low_value_format_penalty, -8)
    placeholder_title_penalty = -12 if _PLACEHOLDER_TITLE_RE.fullmatch(title) else 0

    # ``quality`` already includes the unchanged freshness-policy penalty.  It
    # is deliberately amplified so unknown/stale-risk evidence cannot be
    # hidden by a superficially attractive title.
    editorial_priority = (
        50
        + native_signal
        + reporting_signal
        + int(components.get("quality", 0)) * 4
        + min(int(components.get("article_confidence", 0)), 8)
        + min(int(components.get("depth", 0)), 4)
        + special_material_penalty
        + generic_overview_penalty
        + commercial_penalty
        + low_value_format_penalty
        + placeholder_title_penalty
    )
    return {
        "editorial_priority": editorial_priority,
        "native_signal": native_signal,
        "reporting_signal": reporting_signal,
        "special_material_penalty": special_material_penalty,
        "generic_overview_penalty": generic_overview_penalty,
        "commercial_penalty": commercial_penalty,
        "low_value_format_penalty": low_value_format_penalty,
        "placeholder_title_penalty": placeholder_title_penalty,
    }


def score_with_resolved_freshness(
    item: DiscoveredURL,
    original_index: int,
) -> tuple[tuple[int, ...], dict[str, int]]:
    _, components = _legacy_score(item, original_index)
    decision = evaluate_freshness_policy(item, phase="prefilter")
    components = dict(components)
    components["quality"] = int(components.get("quality", 0)) + int(
        decision.score_penalty
    )
    components["freshness_ordinal"] = int(decision.score_ordinal)
    components["freshness_penalty"] = int(decision.score_penalty)
    components.update(_editorial_components(item, components))
    item.metadata.setdefault("selection", {})["ranking_freshness_version"] = (
        RANKING_FRESHNESS_VERSION
    )
    score = (
        components["editorial_priority"],
        components["quality"],
        components["freshness_ordinal"],
        components["article_confidence"],
        components["depth"],
        components["title_richness"],
        components["description_richness"],
        components["rank_score"],
    )
    return score, components


def install_ranked_freshness() -> None:
    _ranked._score = score_with_resolved_freshness


__all__ = [
    "RANKING_FRESHNESS_VERSION",
    "install_ranked_freshness",
    "score_with_resolved_freshness",
]
