"""Artifact-only full-funnel observability for v0.6 parallel shadow runs.

This module is deliberately outside the Collector runtime path. It consumes an
already-produced ``collector-result.json`` and derives measurement rows without
network requests, Sheet writes, or mutation of frozen L4/L5/L6 semantics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping

FULL_FUNNEL_AUDIT_VERSION = "full-funnel-audit-v1"
_RESULT_TYPES = (
    "discovery_result",
    "gate_result",
    "acquisition_result",
    "canonical_result",
    "editorial_result",
    "selection_result",
    "projection_result",
)
_ACTIONABLE_VERDICTS = frozenset({"recommend", "consider"})


def build_full_funnel_audit(collector_result: Mapping[str, Any]) -> dict[str, Any]:
    """Derive an observation-aware Discovery→Selection funnel.

    A missing Acquisition result means the control did not expose a body to the
    shadow. It is an observation boundary, not a synthetic acquisition failure.
    Native stage statuses/reasons remain authoritative; ``failure_family`` is
    derived only in this audit output.
    """

    shadow = collector_result.get("v06_shadow")
    if not isinstance(shadow, Mapping):
        return _unavailable(collector_result, "v06_shadow_missing")
    if str(shadow.get("status", "")) != "success":
        return _unavailable(
            collector_result,
            f"v06_shadow_status:{shadow.get('status') or 'unknown'}",
        )

    events = tuple(e for e in shadow.get("events", ()) if isinstance(e, Mapping))
    comparisons = tuple(i for i in shadow.get("items", ()) if isinstance(i, Mapping))
    comparison_by_item = {
        str(item.get("item_id", "")): item
        for item in comparisons
        if str(item.get("item_id", ""))
    }

    by_item: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    event_type_counts: Counter[str] = Counter()
    for event in events:
        item_id = str(event.get("item_id", ""))
        event_type = str(event.get("event_type", ""))
        if item_id and event_type:
            by_item[item_id][event_type].append(event)
            event_type_counts[event_type] += 1

    discovery_events = _of_type(events, "discovery_result")
    raw_observations = len(discovery_events)
    unique_urls = {
        _attr(event, "canonical_url_hint") or _attr(event, "url")
        for event in discovery_events
        if _attr(event, "canonical_url_hint") or _attr(event, "url")
    }
    surfaces = _surface_summary(collector_result, discovery_events)

    integrity_errors: list[str] = []
    shadow_snapshot_count = _as_int(shadow.get("discovery_snapshot_count"))
    control_snapshot_count = _as_int(collector_result.get("discovery_snapshot_rows"))
    if shadow_snapshot_count and shadow_snapshot_count != raw_observations:
        integrity_errors.append(
            f"discovery_event_count={raw_observations}!=shadow_snapshot_count={shadow_snapshot_count}"
        )
    if control_snapshot_count and control_snapshot_count != raw_observations:
        integrity_errors.append(
            f"discovery_event_count={raw_observations}!=control_snapshot_count={control_snapshot_count}"
        )

    all_item_ids = set(by_item) | set(comparison_by_item)
    rows: list[dict[str, Any]] = []
    closed_count = 0
    duplicate_items = 0
    no_acquisition_count = 0
    gate_pass_body_not_observed = 0
    gate_terminal_without_body = 0

    for item_id in sorted(all_item_ids):
        lists = by_item.get(item_id, {})
        duplicates = {
            event_type: len(lists.get(event_type, ()))
            for event_type in _RESULT_TYPES
            if len(lists.get(event_type, ())) > 1
        }
        if duplicates:
            duplicate_items += 1
            integrity_errors.append(f"{item_id}:duplicate_result_events={duplicates}")

        one = {event_type: _one(lists.get(event_type, ())) for event_type in _RESULT_TYPES}
        discovery = one["discovery_result"]
        gate = one["gate_result"]
        acquisition = one["acquisition_result"]
        canonical = one["canonical_result"]
        editorial = one["editorial_result"]
        selection = one["selection_result"]
        projection = one["projection_result"]
        comparison = comparison_by_item.get(item_id, {})

        gate_action = _attr(gate, "gate_action")
        if acquisition is None:
            no_acquisition_count += 1
            if gate_action == "acquire":
                gate_pass_body_not_observed += 1
            else:
                gate_terminal_without_body += 1

        closed, closure_reason = _observation_closed(one)
        if closed:
            closed_count += 1
        else:
            integrity_errors.append(f"{item_id}:{closure_reason}")

        verdict = _attr(editorial, "verdict")
        selected = _as_bool(_attr(selection, "selected"))
        terminal_stage, terminal_reason, failure_family = _terminal_outcome(
            gate=gate,
            acquisition=acquisition,
            canonical=canonical,
            editorial=editorial,
            selection=selection,
        )
        rows.append(
            {
                "item_id": item_id,
                "url": str(comparison.get("url", "") or _attr(discovery, "url")),
                "canonical_url_hint": _attr(discovery, "canonical_url_hint"),
                "source_id": _attr(discovery, "source_id"),
                "discovery_method": _attr(discovery, "discovery_method"),
                "prefilter_status": str(comparison.get("prefilter_status", "")),
                "prefilter_reason": str(comparison.get("prefilter_reason", "")),
                "gate_action": gate_action,
                "gate_reason_code": _reason(gate),
                "body_observed_from_control": acquisition is not None,
                "acquisition_technical_status": _technical(acquisition),
                "acquisition_reason_code": _reason(acquisition),
                "canonical_technical_status": _technical(canonical),
                "canonical_source": _attr(canonical, "canonical_source"),
                "editorial_verdict": verdict,
                "high_editorial_value": verdict == "recommend",
                "strong_editorial_actionable": verdict in _ACTIONABLE_VERDICTS,
                "selection_action": _attr(selection, "policy_action"),
                "selected": selected,
                "selection_rank": _attr(selection, "selection_rank"),
                "selection_reason_code": _reason(selection),
                "projection_emitted": projection is not None,
                "first_terminal_stage": terminal_stage,
                "terminal_reason_code": terminal_reason,
                "failure_family": failure_family,
                "observation_closed": closed,
                "stage_presence": {
                    "discovery": discovery is not None,
                    "acquisition_gate": gate is not None,
                    "acquisition": acquisition is not None,
                    "canonical": canonical is not None,
                    "editorial": editorial is not None,
                    "selection": selection is not None,
                    "projection": projection is not None,
                },
            }
        )

    gate_events = _of_type(events, "gate_result")
    acquisition_events = _of_type(events, "acquisition_result")
    canonical_events = _of_type(events, "canonical_result")
    editorial_events = _of_type(events, "editorial_result")
    selection_events = _of_type(events, "selection_result")
    projection_events = _of_type(events, "projection_result")

    gate_actions = Counter(_attr(event, "gate_action") or "unknown" for event in gate_events)
    acquisition_statuses = Counter(_technical(event) or "unknown" for event in acquisition_events)
    editorial_verdicts = Counter(_attr(event, "verdict") or "unknown" for event in editorial_events)
    selection_actions = Counter(_attr(event, "policy_action") or "unknown" for event in selection_events)
    failure_families = Counter(row["failure_family"] for row in rows)

    acquisition_success_ids = {
        str(event.get("item_id", ""))
        for event in acquisition_events
        if _technical(event) == "success"
    }
    canonical_after_success = sum(
        _technical(event) == "success"
        and str(event.get("item_id", "")) in acquisition_success_ids
        for event in canonical_events
    )
    editorial_eligible = sum(
        str(event.get("item_id", "")) in acquisition_success_ids
        and _attr(event, "verdict") not in {"", "insufficient_evidence"}
        for event in editorial_events
    )
    high_editorial = sum(_attr(event, "verdict") == "recommend" for event in editorial_events)
    strong_actionable = sum(_attr(event, "verdict") in _ACTIONABLE_VERDICTS for event in editorial_events)
    selected_count = sum(_as_bool(_attr(event, "selected")) for event in selection_events)

    return {
        "measurement_version": FULL_FUNNEL_AUDIT_VERSION,
        "audit_status": "complete" if not integrity_errors else "partial",
        "run_id": str(collector_result.get("collector_run_id", shadow.get("run_id", ""))),
        "query_group": str(collector_result.get("query_group", shadow.get("group_id", ""))),
        "collector_version": str(shadow.get("pipeline_version", "")),
        "control_version": str(shadow.get("control_version", "")),
        "measurement_contract": {
            "artifact_only": True,
            "network_requests_added": 0,
            "sheet_writes_added": 0,
            "runtime_path_mutated": False,
            "raw_lead_definition": "one discovery_result observation",
            "unique_url_definition": "distinct canonical_url_hint, falling back to observed URL",
            "body_observation_boundary": "no acquisition_result means control body was not observed; not an acquisition failure",
            "strong_editorial_definition": "frozen L5 verdict in {recommend, consider}; existing policy-actionable set",
            "high_editorial_value_definition": "frozen L5 verdict == recommend",
            "failure_family_semantics": "derived audit layer only; native stage reason/status remains authoritative",
            "projection_semantics": "reported when emitted; not required for current shadow observation closure",
        },
        "surface_summary": surfaces,
        "funnel": {
            "attempted_discovery_surfaces": surfaces["attempted_surface_count"],
            "raw_discovery_observations": raw_observations,
            "unique_article_urls": len(unique_urls),
            "gate_acquire": gate_actions.get("acquire", 0),
            "gate_hard_reject": gate_actions.get("hard_reject", 0),
            "gate_defer": gate_actions.get("defer", 0),
            "control_body_observed": len(acquisition_events),
            "acquisition_success": acquisition_statuses.get("success", 0),
            "acquisition_partial": acquisition_statuses.get("partial", 0),
            "acquisition_failed": acquisition_statuses.get("failed", 0),
            "canonicalized_after_acquisition_success": canonical_after_success,
            "editorial_eligible_for_decision": editorial_eligible,
            "canonical_stage_executed": len(canonical_events),
            "editorial_stage_executed": len(editorial_events),
            "high_editorial_value": high_editorial,
            "strong_editorial_actionable": strong_actionable,
            "selected": selected_count,
            "projection_emitted": len(projection_events),
        },
        "stage_counts": {
            "event_type_counts": dict(sorted(event_type_counts.items())),
            "gate_action_counts": dict(sorted(gate_actions.items())),
            "acquisition_technical_status_counts": dict(sorted(acquisition_statuses.items())),
            "editorial_verdict_counts": dict(sorted(editorial_verdicts.items())),
            "selection_action_counts": dict(sorted(selection_actions.items())),
            "prefilter_status_counts": dict(
                sorted(Counter(str(item.get("prefilter_status", "")) or "unknown" for item in comparisons).items())
            ),
        },
        "coverage": {
            "shadow_item_count": len(all_item_ids),
            "observation_closed_item_count": closed_count,
            "observation_incomplete_item_count": len(all_item_ids) - closed_count,
            "control_body_observed_item_count": len(acquisition_events),
            "no_acquisition_observation_item_count": no_acquisition_count,
            "gate_pass_body_not_observed_item_count": gate_pass_body_not_observed,
            "gate_terminal_without_body_item_count": gate_terminal_without_body,
            "duplicate_stage_result_item_count": duplicate_items,
            "projection_event_count": len(projection_events),
            "projection_coverage_status": (
                "emitted" if projection_events else "not_emitted_by_current_shadow_artifact"
            ),
            "surface_identity_coverage_ratio": surfaces["surface_identity_coverage_ratio"],
            "surface_observability_status": surfaces["surface_observability_status"],
        },
        "failure_family_counts": dict(sorted(failure_families.items())),
        "integrity_errors": integrity_errors,
        "items": rows,
    }


def _surface_summary(
    collector_result: Mapping[str, Any],
    discovery_events: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    selection_audit = collector_result.get("source_selection_audit")
    native_ids: list[str] = []
    if isinstance(selection_audit, Mapping):
        for item in selection_audit.get("selected", ()):
            if isinstance(item, Mapping):
                source_id = str(item.get("source_id", "")).strip()
                if source_id and source_id not in native_ids:
                    native_ids.append(source_id)

    native_attempts = _as_int(collector_result.get("sources_scanned")) or len(native_ids)
    open_attempts = _as_int(collector_result.get("queries_count"))
    lead_counts: Counter[tuple[str, str]] = Counter()
    methods: dict[tuple[str, str], set[str]] = defaultdict(set)
    observed_native: list[str] = []
    observed_open: list[str] = []

    for event in discovery_events:
        surface_id = _attr(event, "source_id")
        method = _attr(event, "discovery_method")
        if not surface_id:
            continue
        kind = "open_query" if method == "firecrawl_search" else "native_source"
        lead_counts[(kind, surface_id)] += 1
        methods[(kind, surface_id)].add(method)
        target = observed_open if kind == "open_query" else observed_native
        if surface_id not in target:
            target.append(surface_id)

    surface_rows: list[dict[str, Any]] = []
    for surface_id in native_ids:
        key = ("native_source", surface_id)
        surface_rows.append(
            {
                "surface_type": "native_source",
                "surface_id": surface_id,
                "attempted": True,
                "raw_lead_count": lead_counts.get(key, 0),
                "discovery_methods": sorted(methods.get(key, set())),
                "identity_provenance": "source_selection_audit",
            }
        )
    for surface_id in observed_native:
        if surface_id in native_ids:
            continue
        key = ("native_source", surface_id)
        surface_rows.append(
            {
                "surface_type": "native_source",
                "surface_id": surface_id,
                "attempted": True,
                "raw_lead_count": lead_counts.get(key, 0),
                "discovery_methods": sorted(methods.get(key, set())),
                "identity_provenance": "discovery_event_only",
            }
        )
    for surface_id in observed_open:
        key = ("open_query", surface_id)
        surface_rows.append(
            {
                "surface_type": "open_query",
                "surface_id": surface_id,
                "attempted": True,
                "raw_lead_count": lead_counts.get(key, 0),
                "discovery_methods": sorted(methods.get(key, set())),
                "identity_provenance": "discovery_event_nonzero_result",
            }
        )

    native_known = min(native_attempts, len(native_ids) if native_ids else len(observed_native))
    open_known = min(open_attempts, len(observed_open))
    attempted = native_attempts + open_attempts
    known = native_known + open_known
    unattributed_native = max(0, native_attempts - (len(native_ids) if native_ids else len(observed_native)))
    unattributed_open = max(0, open_attempts - len(observed_open))
    coverage = round(known / attempted, 6) if attempted else 1.0

    return {
        "attempted_surface_count": attempted,
        "native_source_attempt_count": native_attempts,
        "open_query_attempt_count": open_attempts,
        "known_surface_identity_count": known,
        "unattributed_native_attempt_count": unattributed_native,
        "unattributed_open_query_attempt_count": unattributed_open,
        "surface_identity_coverage_ratio": coverage,
        "surface_observability_status": (
            "aggregate_only_for_zero_result_surfaces"
            if unattributed_native or unattributed_open
            else "identity_complete_for_this_artifact"
        ),
        "observed_surface_rows": surface_rows,
    }


def _observation_closed(one: Mapping[str, Mapping[str, Any] | None]) -> tuple[bool, str]:
    for event_type in ("discovery_result", "gate_result", "selection_result"):
        if one.get(event_type) is None:
            return False, f"missing={event_type}"
    if one.get("acquisition_result") is None:
        if one.get("canonical_result") is not None or one.get("editorial_result") is not None:
            return False, "downstream_event_without_acquisition_observation"
        return True, "body_not_observed_boundary"
    if one.get("canonical_result") is None:
        return False, "missing=canonical_result_after_acquisition"
    if one.get("editorial_result") is None:
        return False, "missing=editorial_result_after_canonical"
    return True, "observed_body_path_closed"


def _terminal_outcome(
    *,
    gate: Mapping[str, Any] | None,
    acquisition: Mapping[str, Any] | None,
    canonical: Mapping[str, Any] | None,
    editorial: Mapping[str, Any] | None,
    selection: Mapping[str, Any] | None,
) -> tuple[str, str, str]:
    if gate is None:
        return "acquisition_gate", "gate_result_missing", "instrumentation_incomplete"
    gate_action = _attr(gate, "gate_action")
    if gate_action == "hard_reject":
        return "acquisition_gate", _reason(gate), "gate_reject"
    if gate_action == "defer":
        return "acquisition_gate", _reason(gate), "gate_defer"
    if acquisition is None:
        return "acquisition", "body_not_observed_in_control", "body_not_observed"
    if _technical(acquisition) not in {"success", "partial"}:
        return "acquisition", _reason(acquisition), "acquisition_failed"
    if canonical is None:
        return "canonical", "canonical_result_missing", "instrumentation_incomplete"
    if _technical(canonical) != "success":
        return "canonical", _reason(canonical), "canonical_failed"
    if editorial is None:
        return "editorial", "editorial_result_missing", "instrumentation_incomplete"
    verdict = _attr(editorial, "verdict")
    if verdict == "insufficient_evidence":
        return "editorial", _reason(editorial), "editorial_insufficient_evidence"
    if verdict in {"low_value", "reject"}:
        return "editorial", _reason(editorial), "editorial_low_value_or_reject"
    if selection is None:
        return "selection", "selection_result_missing", "instrumentation_incomplete"
    if _as_bool(_attr(selection, "selected")):
        return "selection", _reason(selection), "selected"
    if _attr(selection, "policy_action") == "source_chase":
        return "selection", _reason(selection), "source_chase_required"
    if verdict in _ACTIONABLE_VERDICTS:
        return "selection", _reason(selection), "portfolio_not_selected"
    return "selection", _reason(selection), "selection_defer_or_reject"


def _unavailable(collector_result: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "measurement_version": FULL_FUNNEL_AUDIT_VERSION,
        "audit_status": "unavailable",
        "run_id": str(collector_result.get("collector_run_id", "")),
        "query_group": str(collector_result.get("query_group", "")),
        "reason": reason,
        "measurement_contract": {
            "artifact_only": True,
            "network_requests_added": 0,
            "sheet_writes_added": 0,
            "runtime_path_mutated": False,
        },
    }


def _of_type(events: tuple[Mapping[str, Any], ...], event_type: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(event for event in events if str(event.get("event_type", "")) == event_type)


def _one(events: Any) -> Mapping[str, Any] | None:
    values = tuple(events or ())
    return values[0] if values else None


def _attr(event: Mapping[str, Any] | None, key: str) -> str:
    if not isinstance(event, Mapping) or not isinstance(event.get("attributes"), Mapping):
        return ""
    value = event["attributes"].get(key)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _technical(event: Mapping[str, Any] | None) -> str:
    return str(event.get("technical_status", "")) if isinstance(event, Mapping) else ""


def _reason(event: Mapping[str, Any] | None) -> str:
    return str(event.get("reason_code", "")) if isinstance(event, Mapping) else ""


def _as_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


__all__ = ["FULL_FUNNEL_AUDIT_VERSION", "build_full_funnel_audit"]
