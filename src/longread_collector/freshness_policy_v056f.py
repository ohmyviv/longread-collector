"""Route-aware v0.5.6f freshness refinements.

This thin layer preserves the validated 3/7/14-day policy while adding two
narrow evidence rules discovered by the labelled replay:

* native Firecrawl search fallback is lower-trust than RSS/section scans when
  publication time is unknown;
* explicit self-publication/republication years in the search snippet are
  usable low-confidence publication evidence.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
from typing import Any

from . import freshness_policy_v056 as _base
from .models import DiscoveredURL
from .supplemental_date_evidence_v056f import supplemental_text_date_evidence

FRESHNESS_POLICY_VERSION = "freshness-policy-v0.5.6f-route-text"
FreshnessPolicyDecision = _base.FreshnessPolicyDecision
_BASE_EVALUATE = _base.evaluate_freshness_policy
_BASE_RESOLVE = _base.resolve_publication_evidence


def _text_sample(item: DiscoveredURL) -> str:
    return f"{item.title or ''}\n{item.description or ''}".strip()


def _native_search_fallback(item: DiscoveredURL) -> bool:
    if str(item.metadata.get("purpose", "")) != "native_source_scan":
        return False
    method = str(item.discovery_method or "").strip().lower()
    native_method = str(item.metadata.get("native_method", "")).strip().lower()
    return method == "firecrawl_search" or native_method == "firecrawl_search"


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

    if decision.allowed and decision.unknown and _native_search_fallback(item):
        depth, structure = _base._depth_and_structure(item)
        if not (depth and structure):
            decision = replace(
                decision,
                allowed=False,
                reject_reason="freshness_unknown_native_fallback_insufficient_evidence",
                track="ordinary_unknown_native_fallback",
                exception_reason="",
                score_penalty=-12,
            )
            freshness.update(
                {
                    "decision_allowed": False,
                    "freshness_reject_reason": decision.reject_reason,
                    "freshness_track": decision.track,
                    "freshness_exception_reason": "",
                    "freshness_score_penalty": decision.score_penalty,
                    "unknown_date_policy": "hard_reject_native_search_fallback",
                    "native_search_fallback": True,
                }
            )
        else:
            freshness.update(
                {
                    "native_search_fallback": True,
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


# Make runners that import the base module after this module see the refined
# evaluator without duplicating the large validated implementation.
_base.evaluate_freshness_policy = evaluate_freshness_policy
_base.resolve_publication_evidence = resolve_publication_evidence

begin_freshness_clock = _base.begin_freshness_clock
current_freshness_time = _base.current_freshness_time
end_freshness_clock = _base.end_freshness_clock
is_special_document = _base.is_special_document

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
