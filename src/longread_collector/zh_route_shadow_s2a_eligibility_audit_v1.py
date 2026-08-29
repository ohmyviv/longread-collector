"""Deterministic S2-A zero-new-body eligibility audit helpers.

OFFLINE / READ-ONLY only. This module consumes already-persisted Chinese Route
Shadow item telemetry plus the frozen timestamp-measurement-v2 evaluator. It
never performs Discovery, network requests, body extraction, Sheet writes,
Editor wiring, or production mutation.

The deterministic part of S2-A is cohort construction and reviewed-label
validation. Metadata eligibility labels remain explicit reviewed judgments;
this module deliberately does not pretend title-only classification is an
objective model truth.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from .zh_route_shadow_timestamp_measurement_v2 import measure_item_timestamp

S2A_ELIGIBILITY_VERSION = "zh-route-shadow-s2a-eligibility-v1"
S2A_SOURCES = frozenset({"jiemian-depth", "yicai"})
S2A_ALLOWED_CLASSES = frozenset({"plausible_standard_longread", "obvious_out_of_scope", "insufficient_evidence"})
S2A_ALLOWED_REASONS = frozenset({"substantive_editorial_depth_signal", "promotional_or_corporate_pr_identity", "quick_digest_comment_or_roundup_format", "metadata_insufficient_for_longread_depth"})

@dataclass(slots=True, frozen=True)
class S2ACohortItem:
    url_canonical: str
    source_id: str
    title: str
    qualifying_row_count: int
    qualifying_surfaces: tuple[str, ...]
    collector_run_ids: tuple[str, ...]
    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["qualifying_surfaces"] = list(self.qualifying_surfaces)
        value["collector_run_ids"] = list(self.collector_run_ids)
        return value

def _text(value: Any) -> str:
    return str(value or "").strip()

def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return None

def build_s2a_cohort(rows: Iterable[dict[str, Any]]) -> tuple[S2ACohortItem, ...]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = _text(row.get("source_id"))
        if source_id not in S2A_SOURCES or _text(row.get("surface_role")) == "noise_control":
            continue
        if _bool(row.get("control_overlap")) is not False:
            continue
        if measure_item_timestamp(row).freshness_state != "fresh":
            continue
        url = _text(row.get("url_canonical")) or _text(row.get("url"))
        if not url:
            continue
        surface_id = _text(row.get("surface_id")); run_id = _text(row.get("collector_run_id")); title = _text(row.get("title"))
        existing = grouped.get(url)
        if existing is None:
            grouped[url] = {"source_id": source_id, "title": title, "row_count": 1, "surfaces": {surface_id} if surface_id else set(), "runs": {run_id} if run_id else set()}
            continue
        if existing["source_id"] != source_id:
            raise ValueError(f"canonical URL spans S2-A sources: {url}")
        existing["row_count"] += 1
        if not existing["title"] and title: existing["title"] = title
        if surface_id: existing["surfaces"].add(surface_id)
        if run_id: existing["runs"].add(run_id)
    items = [S2ACohortItem(url, value["source_id"], value["title"], int(value["row_count"]), tuple(sorted(value["surfaces"])), tuple(sorted(value["runs"]))) for url, value in grouped.items()]
    return tuple(sorted(items, key=lambda item: (item.source_id, item.url_canonical)))

def validate_reviewed_labels(cohort: Iterable[S2ACohortItem], labels: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    items = tuple(cohort); cohort_by_url = {item.url_canonical: item for item in items}; cohort_urls = set(cohort_by_url); label_urls = set(labels)
    missing = sorted(cohort_urls - label_urls); unexpected = sorted(label_urls - cohort_urls); invalid: list[dict[str, str]] = []
    by_class: Counter[str] = Counter(); by_reason: Counter[str] = Counter(); by_source: dict[str, Counter[str]] = defaultdict(Counter)
    for url in sorted(cohort_urls & label_urls):
        label = labels[url]; metadata_class = _text(label.get("metadata_class")); reason = _text(label.get("class_reason"))
        if metadata_class not in S2A_ALLOWED_CLASSES or reason not in S2A_ALLOWED_REASONS:
            invalid.append({"url_canonical": url, "metadata_class": metadata_class, "class_reason": reason}); continue
        by_class[metadata_class] += 1; by_reason[reason] += 1; by_source[cohort_by_url[url].source_id][metadata_class] += 1
    return {"version": S2A_ELIGIBILITY_VERSION, "valid": not missing and not unexpected and not invalid, "cohort_total": len(items), "reviewed_total": len(cohort_urls & label_urls), "missing_urls": missing, "unexpected_urls": unexpected, "invalid_labels": invalid, "class_counts": dict(sorted(by_class.items())), "reason_counts": dict(sorted(by_reason.items())), "by_source": {source: dict(sorted(counts.items())) for source, counts in sorted(by_source.items())}}

__all__ = ["S2A_ALLOWED_CLASSES", "S2A_ALLOWED_REASONS", "S2A_ELIGIBILITY_VERSION", "S2A_SOURCES", "S2ACohortItem", "build_s2a_cohort", "validate_reviewed_labels"]
