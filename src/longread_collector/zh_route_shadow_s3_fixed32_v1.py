"""Offline Jiemian-only S3 fixed-32 counterfactual replay.

This module is intentionally read-only.  It never performs Discovery, body
acquisition, network requests, Sheet writes, Editor wiring or production
mutation.  The primary experiment inherits the exact S2-A/S2-B four-run window
and 28 Jiemian metadata-plausible identities.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Iterable, Iterator, Mapping

from . import offline_replay_v056 as replay_base
from . import prefilter_v056m as prefilter_module
from . import ranked_freshness_v056 as ranking_module
from .freshness_policy_v056f import evaluate_freshness_policy as _freshness_v056f
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url
from .prefilter_v056m import filter_discovered_v056m
from .selection_plan_v056 import clear_selection_plan, current_selection_plan
from .staged_reserve_v056m import build_second_stage_v056m, split_first_stage
from .zh_route_shadow_timestamp_measurement_v2 import measure_item_timestamp

S3_VERSION = "zh-route-shadow-s3-jiemian-fixed32-v1"
FROZEN_RUN_IDS = (
    "COL-20260827-224813-BJT-zh_midday",
    "COL-20260828-040117-BJT-zh_evening",
    "COL-20260828-234148-BJT-zh_midday",
    "COL-20260829-050025-BJT-zh_evening",
)
FROZEN_SOURCE_ID = "jiemian-depth"
FROZEN_PLAUSIBLE_COUNT = 28
MAX_ATTEMPTS = 32

STATUS_NO_EFFECT = "STRUCTURAL_NO_EFFECT"
STATUS_COMPLETE = "STRUCTURAL_EFFECT_BODY_EVIDENCE_COMPLETE"
STATUS_NEEDS_EVIDENCE = "STRUCTURAL_EFFECT_NEEDS_EVIDENCE"
STATUS_CONTROL_MISMATCH = "NOT_EVALUABLE_CONTROL_REPLAY_MISMATCH"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    value = _text(value).lower()
    if value in {"true", "1", "yes", "y"}:
        return True
    if value in {"false", "0", "no", "n"}:
        return False
    return None


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(_text(value) or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _canonical(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        return canonicalize_url(text)
    except Exception:
        return text


def _normalize_snapshot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(row)
    value["run_id"] = _text(row.get("collector_run_id") or row.get("run_id"))
    value["query_id"] = _text(row.get("query_or_source") or row.get("query_id"))
    value["rank_score"] = row.get("discovered_rank") or row.get("rank_score") or 0
    metadata = _json(row.get("metadata_json"))
    selection = metadata.get("selection") if isinstance(metadata.get("selection"), dict) else {}
    value["selection_group"] = _text(selection.get("selection_bucket"))
    return value


def _normalize_route_row(row: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(row)
    value["treatment_observed_at_bj"] = _text(
        row.get("treatment_observed_at_bj") or row.get("observed_at_bj")
    )
    value["surface_role"] = _text(row.get("surface_role") or row.get("route_role"))
    return value


def _historical_selection(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _json(row.get("metadata_json"))
    selection = metadata.get("selection", {})
    return dict(selection) if isinstance(selection, dict) else {}


def historical_attempt_order(rows: Iterable[Mapping[str, Any]], run_id: str) -> list[str]:
    ordered: list[tuple[int, str]] = []
    for row in rows:
        if _text(row.get("collector_run_id") or row.get("run_id")) != run_id:
            continue
        order = _historical_selection(row).get("actual_extraction_order")
        if order in (None, ""):
            continue
        try:
            ordinal = int(order)
        except (TypeError, ValueError):
            continue
        url = _canonical(row.get("url_canonical") or row.get("url"))
        if url:
            ordered.append((ordinal, url))
    ordered.sort()
    if len({order for order, _ in ordered}) != len(ordered):
        raise ValueError(f"duplicate historical extraction order for {run_id}")
    if ordered and [order for order, _ in ordered] != list(range(1, len(ordered) + 1)):
        raise ValueError(f"non-contiguous historical extraction order for {run_id}")
    return [url for _, url in ordered]


def _control_items(rows: Iterable[Mapping[str, Any]], run_id: str) -> list[DiscoveredURL]:
    items: list[DiscoveredURL] = []
    for raw in rows:
        row = _normalize_snapshot_row(raw)
        if row["run_id"] != run_id:
            continue
        items.append(replay_base._snapshot_item(row))
    return items


def _plausible_index(cohort_rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in cohort_rows:
        if _text(row.get("source_id")) != FROZEN_SOURCE_ID:
            continue
        if _text(row.get("metadata_class")) != "plausible_standard_longread":
            continue
        url = _canonical(row.get("url_canonical") or row.get("url"))
        if not url:
            continue
        result[url] = dict(row)
    if len(result) != FROZEN_PLAUSIBLE_COUNT:
        raise ValueError(
            f"frozen Jiemian plausible universe changed: expected {FROZEN_PLAUSIBLE_COUNT}, got {len(result)}"
        )
    return result


def _route_method(row: Mapping[str, Any]) -> str:
    route_type = _text(row.get("route_type")).lower()
    if route_type in {"section", "section_scan", "html_section"}:
        return "section_scan"
    if route_type in {"rss", "rss_feed"}:
        return "rss"
    return route_type or "section_scan"


@dataclass(frozen=True, slots=True)
class TreatmentCandidateEvidence:
    url_canonical: str
    first_surface: str
    surfaces: tuple[str, ...]
    representative_surface: str
    representative_item_ordinal: int


def build_treatment_candidates(
    *,
    run_id: str,
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    control_urls: set[str] | None = None,
) -> tuple[list[DiscoveredURL], list[TreatmentCandidateEvidence]]:
    """Build exact per-run qualified Jiemian Treatment incrementals.

    A plausible identity must independently satisfy v2 freshness and same-run
    Control non-overlap in the requested run.  Cross-run freshness is never
    borrowed.  Description is deliberately blank because the Route ledger did
    not persist it.
    """

    plausible = _plausible_index(cohort_rows)
    control_urls = control_urls or set()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in route_rows:
        row = _normalize_route_row(raw)
        if _text(row.get("collector_run_id")) != run_id:
            continue
        if _text(row.get("source_id")) != FROZEN_SOURCE_ID:
            continue
        if row.get("surface_role") == "noise_control":
            continue
        if _bool(row.get("control_overlap")) is not False:
            continue
        url = _canonical(row.get("url_canonical") or row.get("url_raw") or row.get("url"))
        if not url or url not in plausible or url in control_urls:
            continue
        measurement = measure_item_timestamp(row)
        if measurement.freshness_state != "fresh":
            continue
        row["_canonical"] = url
        grouped.setdefault(url, []).append(row)

    candidates: list[DiscoveredURL] = []
    evidence: list[TreatmentCandidateEvidence] = []
    for url in sorted(grouped):
        rows = grouped[url]
        cohort = plausible[url]
        first_surface = _text(cohort.get("first_surface"))
        rows.sort(
            key=lambda row: (
                0 if _text(row.get("surface_id")) == first_surface else 1,
                _text(row.get("surface_id")),
                int(row.get("item_ordinal") or 0),
                _canonical(row.get("url_canonical") or row.get("url_raw")),
            )
        )
        representative = rows[0]
        surfaces = tuple(sorted({_text(row.get("surface_id")) for row in rows if _text(row.get("surface_id"))}))
        method = _route_method(representative)
        metadata = {
            "purpose": "native_source_scan",
            "source_id": FROZEN_SOURCE_ID,
            "source_name": "界面新闻",
            "native_method": method,
            "native_endpoint": _text(representative.get("endpoint_url")),
            "priority_tier": "rotate",
            "s3_treatment": True,
            "s3_version": S3_VERSION,
            "s3_first_surface": first_surface,
            "s3_qualifying_surfaces": list(surfaces),
            "s3_route_provenance": [
                {
                    "surface_id": _text(row.get("surface_id")),
                    "item_ordinal": int(row.get("item_ordinal") or 0),
                    "published_at": _text(row.get("published_at")),
                    "publication_time_confidence": _text(row.get("publication_time_confidence")),
                }
                for row in rows
            ],
        }
        candidates.append(
            DiscoveredURL(
                url=url,
                title=_text(representative.get("title") or cohort.get("title")),
                description="",
                published_at=_text(representative.get("published_at")),
                discovery_method=method,
                query_or_source=f"s3:{_text(representative.get('surface_id'))}",
                rank=int(representative.get("item_ordinal") or 0),
                metadata=metadata,
            )
        )
        evidence.append(
            TreatmentCandidateEvidence(
                url_canonical=url,
                first_surface=first_surface,
                surfaces=surfaces,
                representative_surface=_text(representative.get("surface_id")),
                representative_item_ordinal=int(representative.get("item_ordinal") or 0),
            )
        )
    return candidates, evidence


@contextmanager
def _run_time_freshness(run_id: str) -> Iterator[None]:
    run_now = replay_base._run_datetime(run_id)
    original_prefilter = prefilter_module.evaluate_freshness_policy
    original_ranking = ranking_module.evaluate_freshness_policy

    def fixed(item: DiscoveredURL, *, phase: str, now: datetime | None = None):
        return _freshness_v056f(item, phase=phase, now=run_now)

    prefilter_module.evaluate_freshness_policy = fixed
    ranking_module.evaluate_freshness_policy = fixed
    try:
        yield
    finally:
        prefilter_module.evaluate_freshness_policy = original_prefilter
        ranking_module.evaluate_freshness_policy = original_ranking


def _historical_stub(item: DiscoveredURL, row: Mapping[str, Any], index: int) -> ExtractedArticle:
    status = _text(row.get("extraction_status")) or "failed"
    disposition = _text(row.get("candidate_disposition")) or "reject"
    return ExtractedArticle(
        article_id=_text(row.get("article_id")) or f"s3-control-{index}",
        url=item.url,
        url_canonical=_canonical(item.url),
        domain=domain_from_url(item.url),
        title=item.title,
        extraction_status=status,
        candidate_disposition=disposition,
        eligible_for_editor=_bool(row.get("eligible_for_editor")) is True,
        classification_version="s3-persisted-historical-outcome",
    )


def _treatment_stub(item: DiscoveredURL, index: int, *, usable: bool) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=f"s3-treatment-{index}",
        url=item.url,
        url_canonical=_canonical(item.url),
        domain=domain_from_url(item.url),
        title=item.title,
        extraction_status="success" if usable else "failed",
        candidate_disposition="formal_candidate" if usable else "reject",
        eligible_for_editor=usable,
        classification_version="s3-frozen-treatment-outcome-bound",
    )


def _reviewed_confirmed_urls(reviewed_rows: Iterable[Mapping[str, Any]]) -> set[str]:
    return {
        _canonical(row.get("url") or row.get("url_canonical"))
        for row in reviewed_rows
        if _text(row.get("source")) == FROZEN_SOURCE_ID
        and _text(row.get("role")) == "primary_plausible"
        and _text(row.get("review_class")) == "body_confirmed_standard_longread"
        and _canonical(row.get("url") or row.get("url_canonical"))
    }


def _snapshot_by_url(rows: Iterable[Mapping[str, Any]], run_id: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if _text(row.get("collector_run_id") or row.get("run_id")) != run_id:
            continue
        url = _canonical(row.get("url_canonical") or row.get("url"))
        if url:
            result[url] = row
    return result


def _select_and_stage(
    *,
    run_id: str,
    discovered: list[DiscoveredURL],
    snapshot_by_url: Mapping[str, Mapping[str, Any]],
    treatment_confirmed: set[str],
    unknown_treatment_usable: bool,
) -> dict[str, Any]:
    clear_selection_plan()
    with _run_time_freshness(run_id):
        selected, rejected = filter_discovered_v056m(
            discovered,
            max_urls=MAX_ATTEMPTS,
            max_per_domain=2,
        )
        plan = current_selection_plan()
        if plan is None:
            raise RuntimeError("S3 selection did not publish a reserve plan")
        first_stage, deferred = split_first_stage(selected, max_attempts=MAX_ATTEMPTS)
        first_articles: list[ExtractedArticle] = []
        unknown_first_stage: list[str] = []
        for index, item in enumerate(first_stage, start=1):
            url = _canonical(item.url)
            if bool(item.metadata.get("s3_treatment")):
                known = url in treatment_confirmed
                if not known:
                    unknown_first_stage.append(url)
                first_articles.append(
                    _treatment_stub(
                        item,
                        index,
                        usable=known or unknown_treatment_usable,
                    )
                )
            else:
                row = snapshot_by_url.get(url)
                if row is None:
                    raise ValueError(f"missing persisted Control outcome for first-stage URL: {url}")
                first_articles.append(_historical_stub(item, row, index))
        decision = build_second_stage_v056m(
            plan=plan,
            first_stage=first_stage,
            deferred=deferred,
            first_articles=first_articles,
            max_attempts=MAX_ATTEMPTS,
        )
    attempts = decision.first_stage + decision.second_stage
    return {
        "selected": selected,
        "rejected": rejected,
        "first_stage": decision.first_stage,
        "second_stage": decision.second_stage,
        "attempts": attempts,
        "attempt_urls": [_canonical(item.url) for item in attempts],
        "first_stage_urls": [_canonical(item.url) for item in decision.first_stage],
        "treatment_first_stage_urls": [
            _canonical(item.url) for item in decision.first_stage if bool(item.metadata.get("s3_treatment"))
        ],
        "treatment_attempt_urls": [
            _canonical(item.url) for item in attempts if bool(item.metadata.get("s3_treatment"))
        ],
        "unknown_treatment_first_stage_urls": sorted(set(unknown_first_stage)),
    }


def replay_control_run(
    *, run_id: str, snapshot_rows: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    rows = list(snapshot_rows)
    actual = historical_attempt_order(rows, run_id)
    by_url = _snapshot_by_url(rows, run_id)
    discovered = _control_items(rows, run_id)
    simulation = _select_and_stage(
        run_id=run_id,
        discovered=discovered,
        snapshot_by_url=by_url,
        treatment_confirmed=set(),
        unknown_treatment_usable=False,
    )
    replayed = simulation["attempt_urls"]
    return {
        "run_id": run_id,
        "pass": replayed == actual,
        "historical_attempt_count": len(actual),
        "replay_attempt_count": len(replayed),
        "historical_attempt_urls": actual,
        "replay_attempt_urls": replayed,
        "first_mismatch_index": next(
            (
                index
                for index, pair in enumerate(zip(actual, replayed, strict=False), start=1)
                if pair[0] != pair[1]
            ),
            None if len(actual) == len(replayed) else min(len(actual), len(replayed)) + 1,
        ),
    }


def replay_s3_run(
    *,
    run_id: str,
    snapshot_rows: Iterable[Mapping[str, Any]],
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    if run_id not in FROZEN_RUN_IDS:
        raise ValueError(f"run outside frozen S3 cohort: {run_id}")
    snapshot = list(snapshot_rows)
    route = list(route_rows)
    cohort = list(cohort_rows)
    reviewed = list(reviewed_rows)

    control_replay = replay_control_run(run_id=run_id, snapshot_rows=snapshot)
    if not control_replay["pass"]:
        return {
            "run_id": run_id,
            "version": S3_VERSION,
            "status": STATUS_CONTROL_MISMATCH,
            "control_replay": control_replay,
        }

    control_items = _control_items(snapshot, run_id)
    control_urls = {_canonical(item.url) for item in control_items}
    treatment_items, treatment_evidence = build_treatment_candidates(
        run_id=run_id,
        route_rows=route,
        cohort_rows=cohort,
        control_urls=control_urls,
    )
    confirmed = _reviewed_confirmed_urls(reviewed)
    by_url = _snapshot_by_url(snapshot, run_id)

    usable = _select_and_stage(
        run_id=run_id,
        discovered=_control_items(snapshot, run_id) + treatment_items,
        snapshot_by_url=by_url,
        treatment_confirmed=confirmed,
        unknown_treatment_usable=True,
    )
    failed = _select_and_stage(
        run_id=run_id,
        discovered=_control_items(snapshot, run_id) + treatment_items,
        snapshot_by_url=by_url,
        treatment_confirmed=confirmed,
        unknown_treatment_usable=False,
    )

    treatment_first = sorted(set(usable["treatment_first_stage_urls"]) | set(failed["treatment_first_stage_urls"]))
    treatment_attempt = sorted(set(usable["treatment_attempt_urls"]) | set(failed["treatment_attempt_urls"]))
    unknown_blockers = sorted(
        set(usable["unknown_treatment_first_stage_urls"])
        | set(failed["unknown_treatment_first_stage_urls"])
    )
    scenarios_equal = usable["attempt_urls"] == failed["attempt_urls"]
    if not treatment_attempt:
        status = STATUS_NO_EFFECT
    elif unknown_blockers and not scenarios_equal:
        status = STATUS_NEEDS_EVIDENCE
    else:
        status = STATUS_COMPLETE

    historical = control_replay["historical_attempt_urls"]
    usable_set = set(usable["attempt_urls"])
    failed_set = set(failed["attempt_urls"])
    return {
        "run_id": run_id,
        "version": S3_VERSION,
        "status": status,
        "control_replay": control_replay,
        "treatment_eligible_count": len(treatment_items),
        "treatment_candidate_evidence": [
            {
                "url_canonical": value.url_canonical,
                "first_surface": value.first_surface,
                "surfaces": list(value.surfaces),
                "representative_surface": value.representative_surface,
                "representative_item_ordinal": value.representative_item_ordinal,
            }
            for value in treatment_evidence
        ],
        "treatment_first_stage_urls": treatment_first,
        "treatment_attempt_urls_union": treatment_attempt,
        "unknown_treatment_first_stage_urls": unknown_blockers,
        "evidence_completion_manifest": unknown_blockers if status == STATUS_NEEDS_EVIDENCE else [],
        "unknown_treatment_usable_attempt_urls": usable["attempt_urls"],
        "unknown_treatment_failed_attempt_urls": failed["attempt_urls"],
        "scenario_attempt_identity_equal": scenarios_equal,
        "control_displaced_if_unknown_usable": sorted(set(historical) - usable_set),
        "control_displaced_if_unknown_failed": sorted(set(historical) - failed_set),
        "attempt_count_if_unknown_usable": len(usable["attempt_urls"]),
        "attempt_count_if_unknown_failed": len(failed["attempt_urls"]),
    }


def replay_s3_cohort(
    *,
    snapshot_rows: Iterable[Mapping[str, Any]],
    route_rows: Iterable[Mapping[str, Any]],
    cohort_rows: Iterable[Mapping[str, Any]],
    reviewed_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    snapshot = list(snapshot_rows)
    route = list(route_rows)
    cohort = list(cohort_rows)
    reviewed = list(reviewed_rows)
    # Validate the frozen identity universe before looking at treatment effects.
    _plausible_index(cohort)

    control = [replay_control_run(run_id=run_id, snapshot_rows=snapshot) for run_id in FROZEN_RUN_IDS]
    if not all(value["pass"] for value in control):
        return {
            "version": S3_VERSION,
            "status": STATUS_CONTROL_MISMATCH,
            "frozen_run_ids": list(FROZEN_RUN_IDS),
            "control_replays": control,
            "runs": [],
        }

    runs = [
        replay_s3_run(
            run_id=run_id,
            snapshot_rows=snapshot,
            route_rows=route,
            cohort_rows=cohort,
            reviewed_rows=reviewed,
        )
        for run_id in FROZEN_RUN_IDS
    ]
    blockers = sorted(
        {
            url
            for run in runs
            for url in run.get("evidence_completion_manifest", [])
        }
    )
    treatment_dates = {
        run_id[4:12]
        for run_id, run in zip(FROZEN_RUN_IDS, runs, strict=True)
        if run.get("treatment_attempt_urls_union")
    }
    return {
        "version": S3_VERSION,
        "status": STATUS_NEEDS_EVIDENCE if blockers else "S3A_STRUCTURAL_REPLAY_COMPLETE",
        "frozen_run_ids": list(FROZEN_RUN_IDS),
        "frozen_plausible_count": FROZEN_PLAUSIBLE_COUNT,
        "max_attempts": MAX_ATTEMPTS,
        "control_replays": control,
        "runs": runs,
        "treatment_entry_intended_dates": sorted(treatment_dates),
        "evidence_completion_manifest": blockers,
    }


__all__ = [
    "FROZEN_PLAUSIBLE_COUNT",
    "FROZEN_RUN_IDS",
    "FROZEN_SOURCE_ID",
    "MAX_ATTEMPTS",
    "S3_VERSION",
    "STATUS_COMPLETE",
    "STATUS_CONTROL_MISMATCH",
    "STATUS_NEEDS_EVIDENCE",
    "STATUS_NO_EFFECT",
    "TreatmentCandidateEvidence",
    "build_treatment_candidates",
    "historical_attempt_order",
    "replay_control_run",
    "replay_s3_cohort",
    "replay_s3_run",
]
