"""PR-7.3.1 publication resolution over preserved control provenance.

PR-7.3 correctly separated publication semantics from update/republication dates,
but the full-parallel bridge had flattened legacy post-extraction date evidence
before it reached L4.  This hotfix consumes the preserved structured candidates
and calibrates one legacy heuristic that the first post-merge natural run proved
can mistake Related-card dates for article-header dates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
import re

from ..contracts import AcquisitionBundle, DiscoveryRecord, Evidence
from .evidence import make_evidence, normalize_space, text
from . import publication_v073 as _base

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.3.1"
PublicationResolution = _base.PublicationResolution
_STRUCTURED_EVIDENCE_TYPE = "legacy_publication_date_candidate"
_STANDALONE_BODY_SOURCE = "body_header_standalone_date"
_URL_SOURCE_RE = re.compile(r"(?:^|_)(?:url|urlpath|url_path)(?:_|$)", re.I)
_PAGE_METADATA_SOURCES = frozenset(
    {
        "structured_date_published",
        "article_meta_published",
        "page_metadata_published",
        "date_modified",
    }
)
_DISCOVERY_SOURCES = frozenset(
    {
        "rss_feed",
        "news_sitemap",
        "sitemap_lastmod",
        "sitemap_lastmod_modified",
        "search_result",
        "discovery_metadata",
        "snippet_explicit_publication_year",
    }
)


def resolve_publication(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> PublicationResolution:
    candidates = _base._dedupe_candidates(_collect_candidates(record, bundle))
    selectable = [item for item in candidates if item.selectable]

    if not selectable:
        profile = _base._profile(candidates, selected=None, conflict_values=())
        status = "non_publication_only" if candidates else "unknown"
        evidence = _profile_evidence(record.item_id, profile, status=status)
        return PublicationResolution(
            "",
            0.0,
            "unknown",
            evidence,
            status=status,
            evidence_profile=profile,
        )

    selected = max(selectable, key=lambda item: item.sort_key)
    conflict_values = _base._conflict_values(selected, candidates)
    conflict = bool(conflict_values)
    confidence = min(selected.confidence, 0.45) if conflict else selected.confidence
    status = "conflicting" if conflict else ("weak" if confidence < 0.70 else "resolved")
    source = "conflicting_publication_evidence" if conflict else selected.source

    profile = _base._profile(
        candidates,
        selected=selected,
        conflict_values=conflict_values,
    )
    evidence_rows: list[Evidence] = [
        make_evidence(
            record.item_id,
            "publication_date",
            "published_at",
            selected.normalized,
            confidence=confidence,
            excerpt=(
                f"selected_source={source}; semantic={selected.semantic}; "
                f"provenance={selected.provenance}; timezone_basis={selected.timezone_basis}; "
                f"conflict={conflict}"
            ),
            extractor=PUBLICATION_VERSION,
        )
    ]

    for row in profile[:16]:
        evidence_rows.append(
            make_evidence(
                record.item_id,
                "publication_date_candidate",
                "published_at",
                row["normalized"] or row["raw"],
                confidence=float(row["confidence"]),
                excerpt=(
                    f"source={row['source']}; semantic={row['semantic']}; "
                    f"provenance={row['provenance']}; relation={row['relation']}; "
                    f"timezone_basis={row['timezone_basis']}; raw={row['raw']}"
                ),
                extractor=PUBLICATION_VERSION,
            )
        )

    if conflict:
        evidence_rows.append(
            make_evidence(
                record.item_id,
                "publication_date_conflict",
                "published_at_conflict",
                conflict_values,
                confidence=0.98,
                excerpt=(
                    "credible publication evidence with the same date semantic "
                    "disagrees materially"
                ),
                extractor=PUBLICATION_VERSION,
            )
        )

    evidence_rows.extend(_profile_evidence(record.item_id, profile, status=status))
    return PublicationResolution(
        selected.normalized,
        confidence,
        source,
        tuple(evidence_rows),
        conflict=conflict,
        conflict_values=conflict_values,
        status=status,
        evidence_profile=profile,
    )


def _collect_candidates(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> Iterable[_base._Candidate]:
    body = bundle.body_markdown or bundle.body_text or ""
    title = record.title_hint or bundle.raw_title
    structured = tuple(_structured_candidates(bundle, body=body, title=title))
    structured_values = {
        candidate.normalized for candidate in structured if candidate.normalized
    }

    for candidate in _base._collect_candidates(record, bundle):
        # Adapter raw_dates are flattened projections of legacy top-level dates.
        # Once the same value is available with explicit provenance, keeping the
        # generic acquisition copy adds no information and can create a false
        # same-semantic conflict.
        if (
            candidate.source == "acquisition_raw_date"
            and candidate.normalized
            and candidate.normalized in structured_values
        ):
            continue
        yield _calibrate_legacy_body_candidate(candidate, body=body, title=title)

    yield from structured


def _structured_candidates(
    bundle: AcquisitionBundle,
    *,
    body: str,
    title: str,
) -> Iterable[_base._Candidate]:
    ordinal = 1000
    for evidence in bundle.evidence:
        if evidence.evidence_type != _STRUCTURED_EVIDENCE_TYPE:
            continue
        row = evidence.value
        if not isinstance(row, Mapping):
            continue
        value = text(row.get("value"))
        source = text(row.get("source"))
        if not value or not source:
            continue
        raw = text(row.get("raw")) or value
        role = text(row.get("role")).lower() or "published"
        provenance, article_local, confidence_cap = _structured_provenance(
            source,
            raw,
            body=body,
            title=title,
        )
        confidence = _structured_confidence(row.get("confidence"), evidence.confidence)
        if confidence_cap is not None:
            confidence = min(confidence, confidence_cap)
        semantic = _semantic(role, source, raw)
        yield _base._candidate(
            value,
            confidence,
            source,
            raw,
            semantic=semantic,
            provenance=provenance,
            article_local=article_local,
            ordinal=ordinal,
        )
        ordinal += 1


def _structured_provenance(
    source: str,
    raw: str,
    *,
    body: str,
    title: str,
) -> tuple[str, bool, float | None]:
    lowered = normalize_space(source).lower()
    if _URL_SOURCE_RE.search(lowered):
        return "url_path", False, 0.58
    if lowered.startswith("body_") or "body_header" in lowered:
        if lowered == _STANDALONE_BODY_SOURCE and not _standalone_date_is_local(
            raw,
            body=body,
            title=title,
        ):
            # v0.5.6l searched a 6000-character body window and can therefore
            # pick a Related-card standalone date. Preserve the observation but
            # do not let a non-header occurrence outrank page metadata or create
            # a high-confidence conflict.
            return "acquisition_metadata", False, 0.58
        return "article_local_metadata", True, None
    if lowered in _PAGE_METADATA_SOURCES or "meta_published" in lowered:
        return "page_metadata", False, None
    if lowered in _DISCOVERY_SOURCES:
        return "discovery_metadata", False, None
    return "acquisition_metadata", False, None


def _calibrate_legacy_body_candidate(
    candidate: _base._Candidate,
    *,
    body: str,
    title: str,
) -> _base._Candidate:
    lowered = normalize_space(candidate.source).lower()
    if (
        lowered == _STANDALONE_BODY_SOURCE
        and candidate.article_local
        and not _standalone_date_is_local(candidate.raw, body=body, title=title)
    ):
        return replace(
            candidate,
            confidence=min(candidate.confidence, 0.58),
            provenance="acquisition_metadata",
            article_local=False,
        )
    return candidate


def _standalone_date_is_local(raw: str, *, body: str, title: str) -> bool:
    needle = normalize_space(raw)
    if not needle:
        return False
    # Deliberately much tighter than the legacy 6000-character heuristic. The
    # first natural-run failure came from a Related card later in that window.
    # A true standalone header date should be adjacent to the article title.
    header = normalize_space(_base._article_start(body, title)[:1800])
    return needle in header


def _structured_confidence(value: object, fallback: float) -> float:
    label = text(value).lower()
    if label == "high":
        return 0.98
    if label == "medium":
        return 0.86
    if label == "low":
        return 0.58
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return max(0.0, min(float(fallback or 0.72), 1.0))


def _semantic(role: str, source: str, raw: str) -> str:
    normalized_role = normalize_space(role).lower().replace("_", " ")
    if normalized_role in {"modified", "updated"}:
        return "updated"
    if normalized_role in {"republished", "reprinted"}:
        return "republished"
    if normalized_role in {"translated published", "translation published"}:
        return "translated_published"
    if normalized_role == "issued":
        return "issued"
    if normalized_role == "created":
        return "created"
    return _base._semantic_from_text(
        f"{source} {raw}",
        default="published" if normalized_role == "published" else "unknown",
    )


def _profile_evidence(
    item_id: str,
    profile: tuple[dict[str, object], ...],
    *,
    status: str,
) -> tuple[Evidence, ...]:
    if not profile:
        return ()
    return (
        make_evidence(
            item_id,
            "publication_evidence_profile",
            "publication_evidence_status",
            status,
            confidence=0.99,
            excerpt=f"candidate_count={len(profile)}; version={PUBLICATION_VERSION}",
            extractor=PUBLICATION_VERSION,
        ),
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
