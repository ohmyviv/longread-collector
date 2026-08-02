"""Route-aware v0.5.6f freshness refinements.

This thin layer preserves the validated 3/7/14-day policy while adding narrow
evidence rules discovered by the labelled replay:

* native Firecrawl search fallback is lower-trust than RSS/section scans when
  publication time is unknown and is kept as reserve-only without strong depth;
* explicit self-publication/republication years in the search snippet are
  usable low-confidence publication evidence;
* government guidance/resource pages use the independent special-document
  freshness track.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
import re

from . import freshness_policy_v056 as _base
from .models import DiscoveredURL
from .supplemental_date_evidence_v056f import supplemental_text_date_evidence

FRESHNESS_POLICY_VERSION = "freshness-policy-v0.5.6f-route-text"
FreshnessPolicyDecision = _base.FreshnessPolicyDecision
_BASE_EVALUATE = _base.evaluate_freshness_policy
_BASE_RESOLVE = _base.resolve_publication_evidence
_BASE_IS_SPECIAL = _base.is_special_document

_FALLBACK_DEPTH_RE = re.compile(
    r"(?:暗访|调查报道|独家调查|深度调查|深度解析|深度报道|特稿|追踪报道|"
    r"产业链调查|内幕调查|揭秘|专访|访谈)|"
    r"\b(?:inside|in[- ]depth|longform|feature|analysis|explainer)\b|"
    r"\binvestigation\s+(?:reveals?|finds?|into|uncovers?)\b|"
    r"^\s*(?:how|why)\b",
    re.I,
)
_GOV_RESOURCE_RE = re.compile(
    r"(?:guidance|guidelines?|resources?|framework|advisory|issues?\s+and\s+challenges|"
    r"privacy|artificial intelligence)|(?:指导|指引|资源|框架|监管|隐私|人工智能)",
    re.I,
)
_GOV_PATH_RE = re.compile(
    r"/(?:guidance|guidelines?|resources?|privacy|publications?|advice|policy)(?:/|$)",
    re.I,
)


def _text_sample(item: DiscoveredURL) -> str:
    return f"{item.title or ''}\n{item.description or ''}".strip()


def _native_search_fallback(item: DiscoveredURL) -> bool:
    if str(item.metadata.get("purpose", "")) != "native_source_scan":
        return False
    method = str(item.discovery_method or "").strip().lower()
    native_method = str(item.metadata.get("native_method", "")).strip().lower()
    return method == "firecrawl_search" or native_method == "firecrawl_search"


def _strong_fallback_depth(item: DiscoveredURL) -> bool:
    return bool(_FALLBACK_DEPTH_RE.search(_text_sample(item)))


def _government_resource(item: DiscoveredURL) -> bool:
    parts = urlsplit(item.url)
    domain = parts.netloc.lower().removeprefix("www.")
    path = (parts.path or "/").lower()
    government = (
        domain.endswith((".gov", ".gov.cn", ".gov.au", ".gov.uk", ".gc.ca"))
        or bool(re.search(r"\.gov\.[a-z]{2}$", domain, re.I))
    )
    if not government:
        return False
    sample = _text_sample(item)
    return bool(_GOV_PATH_RE.search(path) or _GOV_RESOURCE_RE.search(sample))


def _apply_explicit_text_year(item: DiscoveredURL) -> tuple[str, list[Any]]:
    original = str(item.published_at or "")
    initial = _BASE_RESOLVE(item)
    if initial.get("published_at_resolved"):
        return original, []
    evidence = supplemental_text_date_evidence(_text_sample(item))
    if evidence:
        item.published_at = evidence[0].value.isoformat()
    return original, evidence


def _record_text_evidence(item: DiscoveredURL, evidence: list[Any]) -> None:
    if not evidence:
        return
    freshness = item.metadata.setdefault("freshness", {})
    entry = evidence[0]
    freshness["published_at_source"] = entry.source
    freshness["published_at_confidence"] = entry.confidence
    freshness["explicit_text_publication_evidence"] = {
        **asdict(entry),
        "value": entry.value.isoformat(),
    }
    freshness.setdefault("evidence", []).append(
        {**asdict(entry), "value": entry.value.isoformat()}
    )


def evaluate_freshness_policy(
    item: DiscoveredURL,
    *,
    phase: str = "prefilter",
    now: datetime | None = None,
) -> FreshnessPolicyDecision:
    original_published_at, text_evidence = _apply_explicit_text_year(item)
    try:
        decision = _BASE_EVALUATE(item, phase=phase, now=now)
    finally:
        item.published_at = original_published_at

    _record_text_evidence(item, text_evidence)
    freshness = item.metadata.setdefault("freshness", {})
    freshness["policy_version"] = FRESHNESS_POLICY_VERSION

    if _government_resource(item):
        decision = replace(
            decision,
            allowed=True,
            reject_reason="",
            track="special_document",
            exception_reason="government_resource_track",
            score_penalty=-2 if decision.unknown else 0,
        )
        freshness.update(
            {
                "decision_allowed": True,
                "freshness_reject_reason": "",
                "freshness_track": "special_document",
                "freshness_exception_reason": "government_resource_track",
                "freshness_score_penalty": decision.score_penalty,
                "government_resource_track": True,
                "unknown_date_policy": (
                    "special_document" if decision.unknown else "known_date_special_document"
                ),
            }
        )

    if decision.allowed and decision.unknown and _native_search_fallback(item):
        _, structure = _base._depth_and_structure(item)
        strong_depth = _strong_fallback_depth(item)
        if not (strong_depth and structure):
            decision = replace(
                decision,
                allowed=True,
                reject_reason="",
                track="ordinary_unknown_native_fallback_reserve",
                exception_reason="reserve_pending_body_date_and_quality",
                score_penalty=-12,
            )
            selection = item.metadata.setdefault("selection", {})
            selection.update(
                {
                    "selection_force_reserve_only": True,
                    "reserve_only_reason": "unknown_native_search_fallback",
                }
            )
            freshness.update(
                {
                    "decision_allowed": True,
                    "freshness_reject_reason": "",
                    "freshness_track": decision.track,
                    "freshness_exception_reason": decision.exception_reason,
                    "freshness_score_penalty": decision.score_penalty,
                    "unknown_date_policy": "reserve_only_native_search_fallback",
                    "native_search_fallback": True,
                    "strong_fallback_depth": False,
                }
            )
        else:
            freshness.update(
                {
                    "native_search_fallback": True,
                    "strong_fallback_depth": True,
                    "unknown_date_policy": "defer_deep_native_search_fallback",
                }
            )
    return decision


def resolve_publication_evidence(item: DiscoveredURL) -> dict[str, Any]:
    original_published_at, text_evidence = _apply_explicit_text_year(item)
    try:
        result = _BASE_RESOLVE(item)
    finally:
        item.published_at = original_published_at
    _record_text_evidence(item, text_evidence)
    result = item.metadata.setdefault("freshness", result)
    result["policy_version"] = FRESHNESS_POLICY_VERSION
    return result


def is_special_document(item: DiscoveredURL) -> bool:
    return _BASE_IS_SPECIAL(item) or _government_resource(item)


# Make runners that import the base module after this module see the refined
# evaluator without duplicating the large validated implementation.
_base.evaluate_freshness_policy = evaluate_freshness_policy
_base.resolve_publication_evidence = resolve_publication_evidence
_base.is_special_document = is_special_document

begin_freshness_clock = _base.begin_freshness_clock
current_freshness_time = _base.current_freshness_time
end_freshness_clock = _base.end_freshness_clock

__all__ = [
    "FRESHNESS_POLICY_VERSION",
    "FreshnessPolicyDecision",
    "begin_freshness_clock",
    "current_freshness_time",
    "end_freshness_clock",
    "evaluate_freshness_policy",
    "is_special_document",
    "resolve_publication_evidence",
]
