"""Comparison records for legacy-control versus v0.6 full parallel shadow."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from ..contracts import StageEvent

PARALLEL_SHADOW_VERSION = "full-parallel-shadow-v0.6-pr7"


@dataclass(frozen=True, slots=True)
class ShadowItemComparison:
    item_id: str
    url: str
    prefilter_status: str
    prefilter_reason: str
    acquired_by_control: bool
    gate_action: str
    gate_reason: str
    legacy_disposition: str
    legacy_policy_action: str
    v06_editorial_verdict: str
    v06_policy_action: str
    v06_selected: bool
    v06_selection_rank: int | None
    diagnostic_only: bool
    body_sha256: str
    difference_tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "url": self.url,
            "prefilter_status": self.prefilter_status,
            "prefilter_reason": self.prefilter_reason,
            "acquired_by_control": self.acquired_by_control,
            "gate_action": self.gate_action,
            "gate_reason": self.gate_reason,
            "legacy_disposition": self.legacy_disposition,
            "legacy_policy_action": self.legacy_policy_action,
            "v06_editorial_verdict": self.v06_editorial_verdict,
            "v06_policy_action": self.v06_policy_action,
            "v06_selected": self.v06_selected,
            "v06_selection_rank": self.v06_selection_rank,
            "diagnostic_only": self.diagnostic_only,
            "body_sha256": self.body_sha256,
            "difference_tags": list(self.difference_tags),
        }


@dataclass(frozen=True, slots=True)
class ParallelShadowReport:
    run_id: str
    group_id: str
    items: tuple[ShadowItemComparison, ...]
    events: tuple[StageEvent, ...]
    control_acquired_count: int
    shared_body_count: int
    shadow_request_count: int
    shadow_firecrawl_request_count: int
    shadow_incremental_cost: float
    body_fingerprint_mismatches: int
    selected_item_ids: tuple[str, ...]
    source_chase_item_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        gate_counts = Counter(item.gate_action for item in self.items)
        legacy_counts = Counter(item.legacy_disposition or "not_acquired" for item in self.items)
        policy_counts = Counter(item.v06_policy_action for item in self.items)
        difference_counts: Counter[str] = Counter()
        for item in self.items:
            difference_counts.update(item.difference_tags)

        legacy_actionable = {
            item.item_id
            for item in self.items
            if item.legacy_disposition
            in {"formal_candidate", "special_candidate", "original_source_required"}
        }
        v06_actionable = {
            item.item_id
            for item in self.items
            if item.v06_selected or item.v06_policy_action == "source_chase"
        }
        union = legacy_actionable | v06_actionable
        overlap = legacy_actionable & v06_actionable
        compact_events = tuple(_compact_event(event) for event in self.events)
        digest = hashlib.sha256(
            json.dumps(compact_events, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return {
            "version": PARALLEL_SHADOW_VERSION,
            "status": "success",
            "run_id": self.run_id,
            "group_id": self.group_id,
            "mode": "shared_discovery_and_control_bodies_zero_request",
            "discovery_snapshot_count": len(self.items),
            "control_acquired_count": self.control_acquired_count,
            "shared_body_count": self.shared_body_count,
            "shadow_request_count": self.shadow_request_count,
            "shadow_firecrawl_request_count": self.shadow_firecrawl_request_count,
            "shadow_incremental_cost": self.shadow_incremental_cost,
            "body_fingerprint_mismatches": self.body_fingerprint_mismatches,
            "zero_duplicate_network_invariant": (
                self.shadow_request_count == 0
                and self.shadow_firecrawl_request_count == 0
                and self.shadow_incremental_cost == 0.0
            ),
            "gate_action_counts": dict(gate_counts),
            "legacy_disposition_counts": dict(legacy_counts),
            "v06_policy_action_counts": dict(policy_counts),
            "v06_selected_count": len(self.selected_item_ids),
            "v06_source_chase_count": len(self.source_chase_item_ids),
            "legacy_actionable_count": len(legacy_actionable),
            "v06_observed_actionable_count": len(v06_actionable),
            "observed_actionable_overlap_count": len(overlap),
            "observed_actionable_jaccard": (
                round(len(overlap) / len(union), 6) if union else 1.0
            ),
            "difference_tag_counts": dict(difference_counts),
            "selected_item_ids": list(self.selected_item_ids),
            "source_chase_item_ids": list(self.source_chase_item_ids),
            "event_count": len(self.events),
            "event_digest_sha256": digest,
            "items": [item.as_dict() for item in self.items],
            "events": list(compact_events),
            "interpretation_guardrails": {
                "quality_claim_requires_human_labels": True,
                "unacquired_items_have_gate_only_truth": True,
                "portfolio_is_observed_body_subset_only": True,
                "development_or_ci_runs_are_not_natural_holdout_days": True,
            },
        }


def _compact_event(event: StageEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "item_id": event.item_id,
        "stage": event.stage.value,
        "event_type": event.event_type.value,
        "stage_version": event.stage_version,
        "technical_status": event.technical_status.value,
        "flow_status": event.flow_status.value,
        "reason_code": event.reason_code,
        "parent_event_id": event.parent_event_id,
        "cost": event.cost,
        "attributes": _plain(event.attributes),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_plain(item) for item in value]
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value
    return value


def difference_tags(
    *,
    gate_action: str,
    legacy_disposition: str,
    legacy_policy_action: str,
    v06_policy_action: str,
    legacy_canonical: Any | None,
    v06_canonical: Any | None,
    legacy_editorial: Any | None,
    v06_editorial: Any | None,
) -> tuple[str, ...]:
    tags: list[str] = []
    if gate_action == "hard_reject" and legacy_disposition in {
        "formal_candidate",
        "special_candidate",
        "original_source_required",
    }:
        tags.append("gate_rejects_legacy_actionable")
    if legacy_policy_action and v06_policy_action and legacy_policy_action != v06_policy_action:
        tags.append("policy_action_disagreement")
    if legacy_canonical is not None and v06_canonical is not None:
        comparisons = (
            ("publication_disagreement", legacy_canonical.published_at, v06_canonical.published_at),
            ("page_surface_disagreement", legacy_canonical.page_surface, v06_canonical.page_surface),
            ("medium_disagreement", legacy_canonical.main_content_medium, v06_canonical.main_content_medium),
            ("genre_disagreement", legacy_canonical.editorial_genre, v06_canonical.editorial_genre),
            ("source_relationship_disagreement", legacy_canonical.source_relationship, v06_canonical.source_relationship),
            ("source_action_disagreement", legacy_canonical.source_action, v06_canonical.source_action),
        )
        for tag, left, right in comparisons:
            left_value = getattr(left, "value", left)
            right_value = getattr(right, "value", right)
            if str(left_value or "") != str(right_value or ""):
                tags.append(tag)
    if legacy_editorial is not None and v06_editorial is not None:
        if legacy_editorial.verdict is not v06_editorial.verdict:
            tags.append("editorial_verdict_disagreement")
    return tuple(tags)


__all__ = [
    "PARALLEL_SHADOW_VERSION",
    "ParallelShadowReport",
    "ShadowItemComparison",
    "difference_tags",
]
