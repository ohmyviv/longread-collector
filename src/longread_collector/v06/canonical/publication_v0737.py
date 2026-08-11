"""PR-7.3.7 publication plausibility guard for Canonical Article (L4).

The 2026-08-11 scheduled ``zh_evening`` Natural Shadow exposed a factual
failure where a future standards effective date (2026-11-01) arrived through
preserved legacy structured evidence and was promoted to ``published_at``.
Legacy freshness correctly rejected the same candidate as future, but L4 had no
observation-time plausibility boundary.

This wrapper keeps every PR-7.3.3 extraction/provenance rule intact and adds one
factual constraint: a candidate that is materially later than the deterministic
run observation date cannot establish the article's publication date. Rejected
future evidence remains in the audit profile; another plausible publication
candidate may still win. No wall-clock access or network I/O is introduced.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Mapping

from ..contracts import AcquisitionBundle, DiscoveryRecord, Evidence
from .evidence import make_evidence, normalize_space
from . import publication_v0733 as _base

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.3.7"
PublicationResolution = _base.PublicationResolution

_CONTEXT_ONLY_SEMANTICS = frozenset({"updated", "republished", "translated_published"})
_PROVENANCE_RANK = {
    "article_header": 6,
    "article_local_metadata": 5,
    "page_metadata": 4,
    "acquisition_metadata": 3,
    "discovery_metadata": 2,
    "url_path": 1,
}
_SEMANTIC_RANK = {
    "original_published": 5,
    "issued": 4,
    "published": 4,
    "created": 4,
    "unknown": 2,
    "republished": 1,
    "translated_published": 1,
    "updated": 1,
}
_PRIMARY_SEMANTICS = frozenset({"published", "issued", "created", "original_published", "unknown"})
_TIMEZONE_NORMALIZED_BASIS = frozenset({"utc_to_bjt", "offset_to_bjt"})


def resolve_publication(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    observed_at_bj: str = "",
) -> PublicationResolution:
    """Resolve publication facts with deterministic observation-time plausibility."""

    base = _base.resolve_publication(record, bundle)
    observed = _parse_observed_date(observed_at_bj)
    profile = tuple(dict(row) for row in base.evidence_profile)

    if observed is None or not profile:
        return replace(base, evidence=_retag_version(base.evidence))

    rejected = {
        index
        for index, row in enumerate(profile)
        if _row_selectable(row) and _implausibly_future(row, observed)
    }
    if not rejected:
        return replace(base, evidence=_retag_version(base.evidence))

    plausible_selectable = [
        (index, row)
        for index, row in enumerate(profile)
        if index not in rejected and _row_selectable(row)
    ]
    selected_index: int | None = None
    selected: Mapping[str, object] | None = None
    if plausible_selectable:
        selected_index, selected = max(
            plausible_selectable,
            key=lambda item: _row_sort_key(item[1], item[0]),
        )

    conflict_values = _conflict_values(
        selected,
        profile,
        selected_index=selected_index,
        rejected=rejected,
    )
    conflict = bool(conflict_values)

    if selected is None:
        confidence = 0.0
        status = "unknown"
        source = "unknown"
        value = ""
    else:
        selected_confidence = float(selected.get("confidence") or 0.0)
        confidence = min(selected_confidence, 0.45) if conflict else selected_confidence
        status = "conflicting" if conflict else ("weak" if confidence < 0.70 else "resolved")
        source = (
            "conflicting_publication_evidence"
            if conflict
            else str(selected.get("source") or "unknown")
        )
        value = str(selected.get("normalized") or "")

    calibrated_profile = _rebuild_profile(
        profile,
        selected_index=selected_index,
        conflict_values=conflict_values,
        rejected=rejected,
    )
    evidence = _resolution_evidence(
        record.item_id,
        calibrated_profile,
        selected=selected,
        value=value,
        confidence=confidence,
        source=source,
        conflict=conflict,
        conflict_values=conflict_values,
        status=status,
        rejected=rejected,
        observed=observed,
    )

    return PublicationResolution(
        value,
        confidence,
        source,
        evidence,
        conflict=conflict,
        conflict_values=conflict_values,
        status=status,
        evidence_profile=calibrated_profile,
    )


def _parse_observed_date(value: str) -> date | None:
    raw = normalize_space(value)
    if not raw:
        return None
    candidate = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def _normalized_date(row: Mapping[str, object]) -> date | None:
    raw = str(row.get("normalized") or "")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _row_selectable(row: Mapping[str, object]) -> bool:
    return bool(
        row.get("normalized")
        and str(row.get("semantic") or "") not in _CONTEXT_ONLY_SEMANTICS
        and str(row.get("provenance") or "") != "url_path"
    )


def _implausibly_future(row: Mapping[str, object], observed: date) -> bool:
    candidate = _normalized_date(row)
    if candidate is None:
        return False
    basis = str(row.get("timezone_basis") or "")
    # Offset-bearing timestamps have already been normalized to BJT by the
    # established resolver and therefore need no calendar-day tolerance. Date-
    # only / naive-local evidence gets one day for international boundary cases.
    tolerance = timedelta(days=0 if basis in _TIMEZONE_NORMALIZED_BASIS else 1)
    return candidate > observed + tolerance


def _row_sort_key(row: Mapping[str, object], ordinal: int) -> tuple[int, int, int, float, int]:
    return (
        1 if bool(row.get("article_local")) else 0,
        _PROVENANCE_RANK.get(str(row.get("provenance") or ""), 0),
        _SEMANTIC_RANK.get(str(row.get("semantic") or ""), 0),
        float(row.get("confidence") or 0.0),
        -ordinal,
    )


def _conflict_values(
    selected: Mapping[str, object] | None,
    profile: tuple[dict[str, object], ...],
    *,
    selected_index: int | None,
    rejected: set[int],
) -> tuple[str, ...]:
    if selected is None or str(selected.get("semantic") or "") not in _PRIMARY_SEMANTICS:
        return ()
    semantic = str(selected.get("semantic") or "")
    comparable = [
        row
        for index, row in enumerate(profile)
        if index not in rejected
        and row.get("normalized")
        and str(row.get("semantic") or "") == semantic
        and float(row.get("confidence") or 0.0) >= 0.72
        and _PROVENANCE_RANK.get(str(row.get("provenance") or ""), 0)
        >= _PROVENANCE_RANK["acquisition_metadata"]
    ]
    if bool(selected.get("article_local")):
        values = {str(row.get("normalized")) for row in comparable if row.get("article_local")}
        return tuple(sorted(values)) if len(values) > 1 else ()

    values = {str(row.get("normalized")) for row in comparable}
    if len(values) < 2:
        return ()
    parsed = []
    for value in values:
        try:
            parsed.append(datetime.fromisoformat(value).date())
        except ValueError:
            continue
    if len(parsed) >= 2 and (max(parsed) - min(parsed)).days > 7:
        return tuple(sorted(values))
    return ()


def _rebuild_profile(
    profile: tuple[dict[str, object], ...],
    *,
    selected_index: int | None,
    conflict_values: tuple[str, ...],
    rejected: set[int],
) -> tuple[dict[str, object], ...]:
    conflicts = set(conflict_values)
    selected = profile[selected_index] if selected_index is not None else None
    rows: list[dict[str, object]] = []
    for index, original in enumerate(profile):
        row = dict(original)
        semantic = str(row.get("semantic") or "")
        normalized = str(row.get("normalized") or "")
        if index in rejected:
            relation = "contextual"
        elif selected_index is not None and index == selected_index:
            relation = "selected"
        elif semantic in _CONTEXT_ONLY_SEMANTICS or str(row.get("provenance") or "") == "url_path":
            relation = "contextual"
        elif selected is not None and normalized and normalized == str(selected.get("normalized") or ""):
            relation = "supports"
        elif normalized in conflicts and semantic == str(selected.get("semantic") or ""):
            relation = "conflicts"
        else:
            relation = "alternative"
        row["relation"] = relation
        rows.append(row)
    return tuple(rows)


def _resolution_evidence(
    item_id: str,
    profile: tuple[dict[str, object], ...],
    *,
    selected: Mapping[str, object] | None,
    value: str,
    confidence: float,
    source: str,
    conflict: bool,
    conflict_values: tuple[str, ...],
    status: str,
    rejected: set[int],
    observed: date,
) -> tuple[Evidence, ...]:
    evidence: list[Evidence] = []
    if selected is not None and value:
        evidence.append(
            make_evidence(
                item_id,
                "publication_date",
                "published_at",
                value,
                confidence=confidence,
                excerpt=(
                    f"selected_source={source}; semantic={selected.get('semantic')}; "
                    f"provenance={selected.get('provenance')}; "
                    f"timezone_basis={selected.get('timezone_basis')}; conflict={conflict}"
                ),
                extractor=PUBLICATION_VERSION,
            )
        )
        for row in profile[:16]:
            evidence.append(
                make_evidence(
                    item_id,
                    "publication_date_candidate",
                    "published_at",
                    row.get("normalized") or row.get("raw") or "",
                    confidence=float(row.get("confidence") or 0.0),
                    excerpt=(
                        f"source={row.get('source')}; semantic={row.get('semantic')}; "
                        f"provenance={row.get('provenance')}; relation={row.get('relation')}; "
                        f"timezone_basis={row.get('timezone_basis')}; raw={row.get('raw')}"
                    ),
                    extractor=PUBLICATION_VERSION,
                )
            )

    rejected_values = tuple(
        sorted(
            {
                str(profile[index].get("normalized") or profile[index].get("raw") or "")
                for index in rejected
                if profile[index].get("normalized") or profile[index].get("raw")
            }
        )
    )
    evidence.append(
        make_evidence(
            item_id,
            "publication_date_plausibility_guard",
            "published_at_plausibility",
            rejected_values,
            confidence=0.99,
            excerpt=(
                f"observed_bjt_date={observed.isoformat()}; rejected_future_candidates="
                f"{','.join(rejected_values)}; date_only_tolerance_days=1; "
                "timezone_normalized_tolerance_days=0"
            ),
            extractor=PUBLICATION_VERSION,
        )
    )

    if conflict:
        evidence.append(
            make_evidence(
                item_id,
                "publication_date_conflict",
                "published_at_conflict",
                conflict_values,
                confidence=0.98,
                excerpt="credible plausible publication evidence with the same date semantic disagrees materially",
                extractor=PUBLICATION_VERSION,
            )
        )

    if profile:
        evidence.append(
            make_evidence(
                item_id,
                "publication_evidence_profile",
                "publication_evidence_status",
                status,
                confidence=0.99,
                excerpt=f"candidate_count={len(profile)}; version={PUBLICATION_VERSION}",
                extractor=PUBLICATION_VERSION,
            )
        )
    return tuple(evidence)


def _retag_version(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple(
        replace(item, extractor=PUBLICATION_VERSION)
        if item.extractor.startswith("canonical-publication-")
        else item
        for item in evidence
    )


normalize_publication_date = _base.normalize_publication_date
normalize_publication_fact = _base.normalize_publication_fact

__all__ = [
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "normalize_publication_date",
    "normalize_publication_fact",
    "resolve_publication",
]
