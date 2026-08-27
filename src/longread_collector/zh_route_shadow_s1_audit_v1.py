"""Deterministic read-only acceptance audit for Chinese Route Shadow S1.

The audit consumes already-persisted ledger rows.  It performs no Discovery,
network fetch, Sheet write, candidate selection or body extraction.  Its purpose
is to separate experiment validity from route utility before prospective S1
evidence is interpreted.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Iterable
from urllib.parse import urlsplit

from .source_run_coverage import SOURCE_RUN_COVERAGE_VERSION
from .v06.shadow.run_summary_persistence import SHADOW_RUN_SUMMARY_VERSION
from .zh_route_shadow_contracts_v1 import (
    PORTFOLIOS,
    ROUTE_SHADOW_CONTRACT_VERSION,
    S1_BODY_MODE,
    SurfaceRole,
    active_s1_surfaces,
)
from .zh_route_shadow_discovery_v1 import ROUTE_SHADOW_DISCOVERY_VERSION
from .zh_route_shadow_telemetry_v1 import ROUTE_SHADOW_TELEMETRY_VERSION

S1_AUDIT_VERSION = "zh-route-shadow-s1-audit-v1"
TARGET_SOURCE_IDS = frozenset(PORTFOLIOS)
VALID_SURFACE_STATUSES = {
    "observed",
    "date_unknown",
    "stale_surface",
    "empty",
    "request_failed",
}


class AuditVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"
    OBSERVE = "OBSERVE"


@dataclass(slots=True)
class LayerResult:
    layer: str
    verdict: str
    checks: dict[str, bool | None] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class S1AuditReport:
    audit_version: str
    collector_run_id: str
    verdict: str
    eligible_exposure: bool
    treatment_source_ids: list[str]
    layers: list[LayerResult]
    static_contract: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    return _text(value).upper() in {"TRUE", "1", "YES", "Y", "ON"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(_text(value)))
    except (TypeError, ValueError):
        return default


def parse_run_notes(value: Any) -> dict[str, str]:
    """Parse the Collector's semicolon-delimited audit markers without guessing."""

    markers: dict[str, str] = {}
    for part in _text(value).split(";"):
        if "=" not in part:
            continue
        key, raw = part.split("=", 1)
        key = key.strip()
        if key:
            markers[key] = raw.strip()
    return markers


def _first(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    values = list(rows)
    return values[0] if values else None


def audit_surface_contracts() -> dict[str, Any]:
    """Statically validate the frozen S1 Route Portfolio measurement contract."""

    errors: list[str] = []
    warnings: list[str] = []
    active = []
    seen_surface_ids: set[str] = set()
    expected_noise = {
        "yicai_info_control",
        "yicai_commercial_control",
        "eeo_root_rss_control",
        "caixin_promotion_control",
    }

    suffixes = {
        "yicai": "yicai.com",
        "eeo": "eeo.com.cn",
        "caixin": "caixin.com",
        "jiemian-depth": "jiemian.com",
    }

    for source_id, portfolio in PORTFOLIOS.items():
        if portfolio.source_id != source_id:
            errors.append(f"portfolio_source_mismatch:{source_id}")
        for surface in portfolio.surfaces:
            if surface.surface_id in seen_surface_ids:
                errors.append(f"duplicate_surface_id:{surface.surface_id}")
            seen_surface_ids.add(surface.surface_id)
            if not surface.publication_surface_id:
                errors.append(f"missing_publication_surface:{surface.surface_id}")
            if surface.source_id != source_id:
                errors.append(f"surface_source_mismatch:{surface.surface_id}")
            if surface.transport not in {"section", "rss"}:
                errors.append(f"unsupported_transport:{surface.surface_id}")
            if surface.max_items <= 0:
                errors.append(f"invalid_max_items:{surface.surface_id}")
            if surface.role is SurfaceRole.SPECIAL_PRODUCT and surface.s1_enabled:
                errors.append(f"special_product_active:{surface.surface_id}")

            host = urlsplit(surface.url).hostname or ""
            suffix = suffixes[source_id]
            if not (host == suffix or host.endswith("." + suffix)):
                errors.append(f"non_first_party_endpoint:{surface.surface_id}:{host}")

            if surface.s1_enabled:
                active.append(surface)

    actual_noise = {
        surface.surface_id
        for surface in active
        if surface.role is SurfaceRole.NOISE_CONTROL
    }
    if actual_noise != expected_noise:
        errors.append(
            "noise_control_set_mismatch:"
            f"expected={sorted(expected_noise)} actual={sorted(actual_noise)}"
        )

    for surface in active:
        host = urlsplit(surface.url).hostname or ""
        path = urlsplit(surface.url).path.lower()
        if surface.source_id == "caixin" and host.startswith("promote."):
            if surface.role is not SurfaceRole.NOISE_CONTROL:
                errors.append(f"caixin_promotion_not_isolated:{surface.surface_id}")
        if surface.source_id == "jiemian-depth" and any(
            token in path for token in ("/account/", "/author/", "/jmedia/")
        ):
            errors.append(f"jiemian_partner_surface_active:{surface.surface_id}")

    if len(active) != 21:
        errors.append(f"active_surface_count_changed:expected=21 actual={len(active)}")

    # Generic section parsing associates clock text with the preceding admitted
    # article until the next admitted article anchor.  This is adequate for S1
    # freshness observation but is not, by itself, Final Recall A-level proof.
    warnings.append("section_clock_context_is_s1_observation_not_final_recall_A_level")

    return {
        "contract_version": ROUTE_SHADOW_CONTRACT_VERSION,
        "body_mode": S1_BODY_MODE,
        "target_sources": sorted(TARGET_SOURCE_IDS),
        "active_surface_count": len(active),
        "active_surfaces_by_source": {
            source_id: [s.surface_id for s in active_s1_surfaces(source_id)]
            for source_id in sorted(PORTFOLIOS)
        },
        "errors": errors,
        "warnings": warnings,
        "pass": not errors,
    }


def _control_layer(
    run: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
    shadow_summary: dict[str, Any] | None,
) -> LayerResult:
    notes = parse_run_notes(run.get("notes"))
    checks: dict[str, bool | None] = {
        "terminal_success": _text(run.get("final_status")) == "success",
        "coverage_persisted": _bool(notes.get("source_run_coverage_persisted")),
        "coverage_version_current": (
            notes.get("source_run_coverage_version") == SOURCE_RUN_COVERAGE_VERSION
        ),
        "coverage_row_count_matches": (
            _int(notes.get("source_run_coverage_rows")) == len(coverage_rows)
        ),
        "snapshot_success": notes.get("snapshot_persistence_status") == "success",
        "snapshot_expected_positive": _int(notes.get("snapshot_expected_rows")) > 0,
        "snapshot_expected_equals_persisted": (
            _int(notes.get("snapshot_expected_rows"))
            == _int(notes.get("snapshot_persisted_rows"))
        ),
        "snapshot_readback_true": _bool(notes.get("snapshot_readback_performed")),
    }
    facts: dict[str, Any] = {
        "query_group": _text(run.get("query_group")),
        "coverage_rows": len(coverage_rows),
        "snapshot_expected_rows": _int(notes.get("snapshot_expected_rows")),
        "snapshot_persisted_rows": _int(notes.get("snapshot_persisted_rows")),
    }
    errors: list[str] = []
    if shadow_summary is None:
        checks["shadow_full_snapshot_invariant"] = None
        checks["shadow_capture_gap_zero"] = None
        errors.append("missing_v06_shadow_run_summary")
    else:
        checks["shadow_summary_version_current"] = (
            _text(shadow_summary.get("summary_version")) == SHADOW_RUN_SUMMARY_VERSION
        )
        checks["shadow_full_snapshot_invariant"] = _bool(
            shadow_summary.get("full_snapshot_invariant")
        )
        checks["shadow_capture_gap_zero"] = (
            _int(shadow_summary.get("capture_gap_count")) == 0
        )
        checks["control_result_preserved"] = _bool(
            shadow_summary.get("control_result_preserved")
        )
        facts["capture_gap_count"] = _int(shadow_summary.get("capture_gap_count"))

    hard_fail = any(value is False for value in checks.values())
    return LayerResult(
        layer="L1_control_validity",
        verdict=AuditVerdict.FAIL if hard_fail else AuditVerdict.PASS,
        checks=checks,
        facts=facts,
        errors=errors,
    )


def _selected_target_sources(coverage_rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            _text(row.get("source_id"))
            for row in coverage_rows
            if _bool(row.get("selected"))
            and _text(row.get("source_id")) in TARGET_SOURCE_IDS
            and _text(row.get("coverage_version")) == SOURCE_RUN_COVERAGE_VERSION
        }
    )


def _isolation_layer(
    run: dict[str, Any],
    selected_targets: list[str],
    route_rows: list[dict[str, Any]],
    static_contract: dict[str, Any],
) -> LayerResult:
    notes = parse_run_notes(run.get("notes"))
    observed_sources = sorted({_text(row.get("source_id")) for row in route_rows})
    body_modes = {_text(row.get("body_mode")) for row in route_rows if row}
    first_attempts = _int(notes.get("first_stage_attempts"))
    second_attempts = _int(notes.get("second_stage_attempts"))
    total_attempts = first_attempts + second_attempts

    checks: dict[str, bool | None] = {
        "only_naturally_selected_target_sources": set(observed_sources).issubset(
            set(selected_targets)
        ),
        "metadata_only_rows": (not route_rows or body_modes == {S1_BODY_MODE}),
        "static_route_contract_pass": bool(static_contract.get("pass")),
        "extraction_attempt_cap_32": _int(notes.get("extraction_attempt_cap")) == 32,
        "observed_control_attempts_within_32": total_attempts <= 32,
        "native_source_cap_4": _int(notes.get("native_source_cap")) == 4,
        "absolute_host_cap_4": _int(notes.get("absolute_host_cap")) == 4,
        # Not persisted per natural run in S1 v1.  These are deliberately
        # represented as static-contract evidence rather than fake runtime proof.
        "treatment_body_requests_zero_runtime_observable": None,
        "treatment_never_enters_candidate_selection_runtime_observable": None,
        "treatment_article_cache_isolation_runtime_observable": None,
    }
    hard_fail = any(value is False for value in checks.values())
    notes_out = [
        "body_requests=0/candidate-selection/article_cache isolation are code+workflow regression contracts in S1 v1, not independent per-run Sheet observations"
    ]
    return LayerResult(
        layer="L2_experimental_isolation",
        verdict=AuditVerdict.FAIL if hard_fail else AuditVerdict.PASS,
        checks=checks,
        facts={
            "selected_target_sources": selected_targets,
            "observed_treatment_sources": observed_sources,
            "first_stage_attempts": first_attempts,
            "second_stage_attempts": second_attempts,
            "total_control_body_attempts": total_attempts,
        },
        notes=notes_out,
    )


def _telemetry_layer(
    run_id: str,
    selected_targets: list[str],
    route_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
) -> LayerResult:
    expected_surfaces = {
        (source_id, surface.surface_id)
        for source_id in selected_targets
        for surface in active_s1_surfaces(source_id)
    }
    actual_surfaces = {
        (_text(row.get("source_id")), _text(row.get("surface_id")))
        for row in route_rows
    }
    errors: list[str] = []
    checks: dict[str, bool | None] = {
        "expected_surface_set_complete": actual_surfaces == expected_surfaces,
        "one_observation_per_surface": len(route_rows) == len(actual_surfaces),
        "observation_run_fk": all(
            _text(row.get("collector_run_id")) == run_id for row in route_rows
        ),
        "item_run_fk": all(
            _text(row.get("collector_run_id")) == run_id for row in item_rows
        ),
        "contract_version_current": all(
            _text(row.get("route_contract_version")) == ROUTE_SHADOW_CONTRACT_VERSION
            for row in route_rows + item_rows
        ),
        "discovery_version_current": all(
            _text(row.get("route_discovery_version")) == ROUTE_SHADOW_DISCOVERY_VERSION
            for row in route_rows + item_rows
        ),
        "telemetry_version_current": all(
            _text(row.get("telemetry_version")) == ROUTE_SHADOW_TELEMETRY_VERSION
            for row in route_rows + item_rows
        ),
        "surface_status_valid": all(
            _text(row.get("surface_status")) in VALID_SURFACE_STATUSES
            for row in route_rows
        ),
    }

    route_by_surface = {
        (_text(row.get("source_id")), _text(row.get("surface_id"))): row
        for row in route_rows
    }
    items_by_surface: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in item_rows:
        key = (_text(row.get("source_id")), _text(row.get("surface_id")))
        items_by_surface[key].append(row)
        parent = route_by_surface.get(key)
        if parent is None:
            errors.append(f"item_without_surface_observation:{key[0]}:{key[1]}")
            continue
        for field in ("surface_role", "publication_surface_id", "endpoint", "transport"):
            if _text(row.get(field)) != _text(parent.get(field)):
                errors.append(f"item_parent_mismatch:{key[0]}:{key[1]}:{field}")

    aggregate_mismatches: list[str] = []
    for key, route in route_by_surface.items():
        items = items_by_surface.get(key, [])
        noise = Counter(_text(row.get("noise_reason")) for row in items if _text(row.get("noise_reason")))
        try:
            persisted_noise = json.loads(_text(route.get("noise_reason_counts_json")) or "{}")
        except json.JSONDecodeError:
            persisted_noise = {"__invalid_json__": 1}
        expected = {
            "unique_item_count": len(items),
            "raw_item_count": len(items),
            "recent_item_count": sum(_bool(row.get("within_freshness")) for row in items),
            "dated_item_count": sum(bool(_text(row.get("published_at"))) for row in items),
            "exact_timestamp_count": sum(
                _text(row.get("publication_time_confidence")) == "high" for row in items
            ),
            "control_overlap_count": sum(_bool(row.get("control_overlap")) for row in items),
            "treatment_unique_count": sum(not _bool(row.get("control_overlap")) for row in items),
            "noise_item_count": sum(bool(_text(row.get("noise_reason"))) for row in items),
        }
        for field, value in expected.items():
            if _int(route.get(field)) != value:
                aggregate_mismatches.append(
                    f"{key[0]}:{key[1]}:{field}:persisted={_int(route.get(field))}:recomputed={value}"
                )
        if persisted_noise != dict(noise):
            aggregate_mismatches.append(
                f"{key[0]}:{key[1]}:noise_reason_counts_json"
            )

    checks["item_parent_fk_complete"] = not errors
    checks["observation_aggregates_recompute"] = not aggregate_mismatches
    hard_fail = any(value is False for value in checks.values())
    return LayerResult(
        layer="L3_telemetry_integrity",
        verdict=AuditVerdict.FAIL if hard_fail else AuditVerdict.PASS,
        checks=checks,
        facts={
            "expected_surface_count": len(expected_surfaces),
            "observed_surface_count": len(actual_surfaces),
            "item_rows": len(item_rows),
            "aggregate_mismatches": aggregate_mismatches,
        },
        errors=errors,
    )


def _technical_layer(route_rows: list[dict[str, Any]]) -> LayerResult:
    statuses = Counter(_text(row.get("surface_status")) for row in route_rows)
    request_success = sum(_bool(row.get("request_success")) for row in route_rows)
    parse_success = sum(_bool(row.get("parse_success")) for row in route_rows)
    dated = sum(_int(row.get("dated_item_count")) for row in route_rows)
    exact = sum(_int(row.get("exact_timestamp_count")) for row in route_rows)
    unique = sum(_int(row.get("unique_item_count")) for row in route_rows)
    return LayerResult(
        layer="L4_route_technical_health",
        verdict=AuditVerdict.OBSERVE,
        facts={
            "surface_status_counts": dict(statuses),
            "request_success_surfaces": request_success,
            "parse_success_surfaces": parse_success,
            "surface_count": len(route_rows),
            "unique_items_surface_sum": unique,
            "dated_items_surface_sum": dated,
            "exact_timestamp_items_surface_sum": exact,
            "dated_rate_surface_weighted": round(dated / unique, 4) if unique else None,
            "exact_timestamp_rate_surface_weighted": round(exact / unique, 4) if unique else None,
        },
        notes=["technical health is descriptive on Day-0; poor route yield does not invalidate an otherwise isolated experiment"],
    )


def _utility_layer(item_rows: list[dict[str, Any]]) -> LayerResult:
    canonical_all = {_text(row.get("url_canonical")) for row in item_rows if _text(row.get("url_canonical"))}
    recent = {
        _text(row.get("url_canonical"))
        for row in item_rows
        if _bool(row.get("within_freshness")) and _text(row.get("url_canonical"))
    }
    incremental = {
        _text(row.get("url_canonical"))
        for row in item_rows
        if _bool(row.get("within_freshness"))
        and not _bool(row.get("control_overlap"))
        and _text(row.get("url_canonical"))
    }
    overlap = {
        _text(row.get("url_canonical"))
        for row in item_rows
        if _bool(row.get("control_overlap")) and _text(row.get("url_canonical"))
    }
    noise_incremental = {
        _text(row.get("url_canonical"))
        for row in item_rows
        if _text(row.get("url_canonical")) in incremental
        and bool(_text(row.get("noise_reason")))
    }
    return LayerResult(
        layer="L5_route_utility_evidence",
        verdict=AuditVerdict.OBSERVE,
        facts={
            "canonical_observed": len(canonical_all),
            "canonical_proven_recent": len(recent),
            "canonical_control_overlap": len(overlap),
            "canonical_proven_recent_incremental": len(incremental),
            "canonical_incremental_with_explicit_noise": len(noise_incremental),
            "incremental_noise_rate": (
                round(len(noise_incremental) / len(incremental), 4)
                if incremental else None
            ),
        },
        notes=[
            "S1 does not label metadata-only incrementals eligible/editable/Final-quality",
            "historical known misses are regression fixtures only and are excluded from route ranking/tuning",
        ],
    )


def audit_s1_run(
    *,
    collector_run_id: str,
    run_rows: Iterable[dict[str, Any]],
    coverage_rows: Iterable[dict[str, Any]],
    shadow_summary_rows: Iterable[dict[str, Any]] = (),
    route_observation_rows: Iterable[dict[str, Any]] = (),
    route_item_rows: Iterable[dict[str, Any]] = (),
) -> S1AuditReport:
    """Audit one prospective natural run from already persisted evidence."""

    run_matches = [row for row in run_rows if _text(row.get("collector_run_id")) == collector_run_id]
    static_contract = audit_surface_contracts()
    if not run_matches:
        return S1AuditReport(
            audit_version=S1_AUDIT_VERSION,
            collector_run_id=collector_run_id,
            verdict=AuditVerdict.NOT_EVALUABLE,
            eligible_exposure=False,
            treatment_source_ids=[],
            layers=[LayerResult(
                layer="L0_scheduler_availability",
                verdict=AuditVerdict.NOT_EVALUABLE,
                checks={"durable_control_run_exists": False},
                notes=["No durable Collector run means no S1 evidence; this is not an S1 failure."],
            )],
            static_contract=static_contract,
        )

    if len(run_matches) != 1:
        return S1AuditReport(
            audit_version=S1_AUDIT_VERSION,
            collector_run_id=collector_run_id,
            verdict=AuditVerdict.FAIL,
            eligible_exposure=False,
            treatment_source_ids=[],
            layers=[LayerResult(
                layer="L0_scheduler_availability",
                verdict=AuditVerdict.FAIL,
                checks={"unique_durable_control_run": False},
                errors=[f"duplicate_collector_run_rows:{len(run_matches)}"],
            )],
            static_contract=static_contract,
        )

    run = run_matches[0]
    coverage = [row for row in coverage_rows if _text(row.get("collector_run_id")) == collector_run_id]
    summaries = [row for row in shadow_summary_rows if _text(row.get("collector_run_id")) == collector_run_id]
    routes = [row for row in route_observation_rows if _text(row.get("collector_run_id")) == collector_run_id]
    items = [row for row in route_item_rows if _text(row.get("collector_run_id")) == collector_run_id]
    selected_targets = _selected_target_sources(coverage)

    l0 = LayerResult(
        layer="L0_scheduler_availability",
        verdict=AuditVerdict.PASS,
        checks={"durable_control_run_exists": True, "unique_durable_control_run": True},
        facts={"started_at_bj": _text(run.get("started_at_bj")), "query_group": _text(run.get("query_group"))},
    )
    l1 = _control_layer(run, coverage, _first(summaries))

    if not _text(run.get("query_group")).startswith("zh_"):
        l0.verdict = AuditVerdict.NOT_EVALUABLE
        l0.notes.append("S1 Chinese Route experiment only evaluates zh_* groups")
        return S1AuditReport(
            audit_version=S1_AUDIT_VERSION,
            collector_run_id=collector_run_id,
            verdict=AuditVerdict.NOT_EVALUABLE,
            eligible_exposure=False,
            treatment_source_ids=[],
            layers=[l0, l1],
            static_contract=static_contract,
        )

    if l1.verdict == AuditVerdict.FAIL:
        return S1AuditReport(
            audit_version=S1_AUDIT_VERSION,
            collector_run_id=collector_run_id,
            verdict=AuditVerdict.FAIL,
            eligible_exposure=False,
            treatment_source_ids=selected_targets,
            layers=[l0, l1],
            static_contract=static_contract,
        )

    if not selected_targets:
        return S1AuditReport(
            audit_version=S1_AUDIT_VERSION,
            collector_run_id=collector_run_id,
            verdict=AuditVerdict.NOT_EVALUABLE,
            eligible_exposure=False,
            treatment_source_ids=[],
            layers=[
                l0,
                l1,
                LayerResult(
                    layer="L2_experimental_isolation",
                    verdict=AuditVerdict.NOT_EVALUABLE,
                    checks={"natural_target_source_selected": False},
                    notes=["No target source was naturally selected; do not count a route miss or exposure."],
                ),
            ],
            static_contract=static_contract,
        )

    l2 = _isolation_layer(run, selected_targets, routes, static_contract)
    l3 = _telemetry_layer(collector_run_id, selected_targets, routes, items)
    l4 = _technical_layer(routes)
    l5 = _utility_layer(items)
    hard_layers = (l1, l2, l3)
    verdict = AuditVerdict.PASS if all(layer.verdict == AuditVerdict.PASS for layer in hard_layers) else AuditVerdict.FAIL
    return S1AuditReport(
        audit_version=S1_AUDIT_VERSION,
        collector_run_id=collector_run_id,
        verdict=verdict,
        eligible_exposure=verdict == AuditVerdict.PASS,
        treatment_source_ids=selected_targets,
        layers=[l0, l1, l2, l3, l4, l5],
        static_contract=static_contract,
    )


__all__ = [
    "AuditVerdict",
    "S1_AUDIT_VERSION",
    "S1AuditReport",
    "audit_s1_run",
    "audit_surface_contracts",
    "parse_run_notes",
]
