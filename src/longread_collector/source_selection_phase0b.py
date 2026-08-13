"""Phase 0B deadline-aware source freshness selection."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .known_source_fixes import apply_known_source_fixes
from .native_discovery import _parse_last_scanned, select_sources_for_run as _base_selector

SOURCE_SELECTION_POLICY_VERSION = "deadline-freshness-reserve-v0.6-phase0b.1"


@dataclass(frozen=True, slots=True)
class SourceFreshnessPolicy:
    enabled: bool = False
    group_id: str = "all"
    freshness_source_ids: tuple[str, ...] = ()
    freshness_max_sources: int = 0
    rotate_share: float = 0.75


@dataclass(slots=True)
class SourceSelectionState:
    policy: SourceFreshnessPolicy
    selected: list[dict[str, Any]] = field(default_factory=list)
    missing_freshness_source_ids: list[str] = field(default_factory=list)


_STATE: ContextVar[SourceSelectionState | None] = ContextVar(
    "phase0b_source_selection_state", default=None
)


def begin_source_selection(policy: SourceFreshnessPolicy) -> Token:
    return _STATE.set(SourceSelectionState(policy=policy))


def end_source_selection(token: Token) -> None:
    _STATE.reset(token)


def current_source_selection_state() -> SourceSelectionState | None:
    return _STATE.get()


def _enabled(source: dict[str, Any]) -> bool:
    return (
        str(source.get("priority_tier", "")).strip() != "monitor"
        and source.get("enabled", True) is not False
        and str(source.get("enabled", "TRUE")).strip().upper()
        not in {"FALSE", "0", "NO", "N"}
    )


def _sort_key(source: dict[str, Any]) -> tuple[datetime, str]:
    scanned = _parse_last_scanned(source.get("last_scanned_at_bj"))
    return (scanned or datetime.min, str(source.get("source_id", "")))


def _age_hours(source: dict[str, Any], started: datetime) -> float | None:
    scanned = _parse_last_scanned(source.get("last_scanned_at_bj"))
    if scanned is None:
        return None
    value = (started.replace(tzinfo=None) - scanned).total_seconds() / 3600
    return round(max(0.0, value), 3)


def _annotate(source: dict[str, Any], reason: str, started: datetime) -> dict[str, Any]:
    item = dict(source)
    item["_selection_reason"] = reason
    item["_selection_scan_age_hours"] = _age_hours(item, started)
    return item


def _record(selected: list[dict[str, Any]], missing: list[str]) -> None:
    state = current_source_selection_state()
    if state is None:
        return
    state.selected = [
        {
            "source_id": str(source.get("source_id", "")),
            "source_name": str(source.get("source_name", "")),
            "priority_tier": str(source.get("priority_tier", "")),
            "selection_reason": str(source.get("_selection_reason", "")),
            "scan_age_hours": source.get("_selection_scan_age_hours"),
        }
        for source in selected
    ]
    state.missing_freshness_source_ids = list(missing)


def _baseline(
    sources: list[dict[str, Any]],
    *,
    started: datetime,
    max_sources: int,
    rotate_share: float,
) -> list[dict[str, Any]]:
    selected = _base_selector(
        apply_known_source_fixes(sources),
        started=started,
        max_sources=max_sources,
        rotate_share=rotate_share,
    )
    annotated = [_annotate(source, "coverage_rotation", started) for source in selected]
    _record(annotated, [])
    return annotated


def select_sources_for_run(
    sources: list[dict[str, Any]],
    *,
    started: datetime,
    max_sources: int,
    rotate_share: float = 0.75,
) -> list[dict[str, Any]]:
    """Reserve configured deadline-freshness slots inside the existing cap."""
    state = current_source_selection_state()
    policy = state.policy if state is not None else SourceFreshnessPolicy()
    share = policy.rotate_share if state is not None else rotate_share
    if (
        not policy.enabled
        or max_sources <= 0
        or policy.freshness_max_sources <= 0
        or not policy.freshness_source_ids
    ):
        return _baseline(
            sources, started=started, max_sources=max_sources, rotate_share=share
        )

    fixed = apply_known_source_fixes(sources)
    enabled = [source for source in fixed if _enabled(source)]
    if not enabled:
        _record([], list(policy.freshness_source_ids))
        return []

    by_id = {
        str(source.get("source_id", "")): source
        for source in enabled
        if str(source.get("source_id", ""))
    }
    configured = list(dict.fromkeys(policy.freshness_source_ids))
    missing = [source_id for source_id in configured if source_id not in by_id]
    order = {source_id: index for index, source_id in enumerate(configured)}
    fresh = [by_id[source_id] for source_id in configured if source_id in by_id]
    fresh.sort(
        key=lambda source: (
            _sort_key(source)[0],
            order.get(str(source.get("source_id", "")), 10**9),
            str(source.get("source_id", "")),
        )
    )
    fresh = fresh[: min(max_sources, policy.freshness_max_sources)]
    fresh_ids = {str(source.get("source_id", "")) for source in fresh}
    selected = [_annotate(source, "freshness_reserve", started) for source in fresh]
    slots = max_sources - len(selected)
    if slots <= 0:
        _record(selected, missing)
        return selected[:max_sources]

    ordinary = [
        source for source in enabled if str(source.get("source_id", "")) not in fresh_ids
    ]
    today = started.replace(tzinfo=None).date()
    not_today = [
        source
        for source in ordinary
        if (_parse_last_scanned(source.get("last_scanned_at_bj")) or datetime.min).date()
        != today
    ]
    pool = not_today if len(not_today) >= min(slots, len(ordinary)) else ordinary
    rotate = sorted(
        [source for source in pool if str(source.get("priority_tier", "")) == "rotate"],
        key=_sort_key,
    )
    explore = sorted(
        [source for source in pool if str(source.get("priority_tier", "")) != "rotate"],
        key=_sort_key,
    )

    total_rotate = sum(
        str(source.get("priority_tier", "")) == "rotate" for source in enabled
    )
    rotate_target = min(total_rotate, max(1, round(max_sources * share)))
    explore_target = max(0, max_sources - rotate_target)
    fresh_rotate = sum(
        str(source.get("priority_tier", "")) == "rotate" for source in fresh
    )
    fresh_explore = len(fresh) - fresh_rotate

    coverage: list[dict[str, Any]] = []
    take_rotate = min(max(0, rotate_target - fresh_rotate), slots)
    coverage.extend(rotate[:take_rotate])
    slots -= take_rotate
    picked = {str(source.get("source_id", "")) for source in coverage}
    if slots > 0:
        explore_choices = [
            source for source in explore if str(source.get("source_id", "")) not in picked
        ]
        take_explore = min(max(0, explore_target - fresh_explore), slots)
        coverage.extend(explore_choices[:take_explore])
        slots -= take_explore

    if slots > 0:
        picked = {str(source.get("source_id", "")) for source in coverage}
        remainder = sorted(
            [source for source in pool if str(source.get("source_id", "")) not in picked],
            key=lambda source: (
                0 if str(source.get("priority_tier", "")) == "rotate" else 1,
                *_sort_key(source),
            ),
        )
        coverage.extend(remainder[:slots])

    selected.extend(_annotate(source, "coverage_rotation", started) for source in coverage)
    selected = selected[:max_sources]
    _record(selected, missing)
    return selected


def selection_audit_payload() -> dict[str, Any]:
    state = current_source_selection_state()
    if state is None:
        return {
            "version": SOURCE_SELECTION_POLICY_VERSION,
            "enabled": False,
            "group_id": "",
            "freshness_source_ids": [],
            "freshness_max_sources": 0,
            "selected": [],
            "missing_freshness_source_ids": [],
        }
    return {
        "version": SOURCE_SELECTION_POLICY_VERSION,
        "enabled": state.policy.enabled,
        "group_id": state.policy.group_id,
        "freshness_source_ids": list(state.policy.freshness_source_ids),
        "freshness_max_sources": state.policy.freshness_max_sources,
        "selected": list(state.selected),
        "missing_freshness_source_ids": list(state.missing_freshness_source_ids),
    }
