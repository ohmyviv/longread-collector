"""PR-7.3 publication evidence graph for Canonical Article (L4).

The resolver keeps publication-date resolution factual while preserving why a
date was observed, what it means, and how it relates to the selected fact.
Editorial scoring remains outside this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Iterable
from urllib.parse import urlsplit

from ..contracts import AcquisitionBundle, DiscoveryRecord, Evidence
from .evidence import make_evidence, nested, normalize_space, text

PUBLICATION_VERSION = "canonical-publication-v0.6-pr7.3"

_BJT = timezone(timedelta(hours=8))

_PRIMARY_SEMANTICS = frozenset(
    {"published", "issued", "created", "original_published", "unknown"}
)
_CONTEXT_ONLY_SEMANTICS = frozenset({"updated"})
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
    "republished": 3,
    "unknown": 2,
    "updated": 1,
}


@dataclass(frozen=True, slots=True)
class PublicationResolution:
    value: str
    confidence: float
    source: str
    evidence: tuple[Evidence, ...]
    conflict: bool = False
    conflict_values: tuple[str, ...] = ()
    status: str = "unknown"
    evidence_profile: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    value: str
    normalized: str
    confidence: float
    source: str
    raw: str
    semantic: str
    provenance: str
    article_local: bool
    timezone_basis: str
    ordinal: int

    @property
    def selectable(self) -> bool:
        return (
            bool(self.normalized)
            and self.semantic not in _CONTEXT_ONLY_SEMANTICS
            and self.provenance != "url_path"
        )

    @property
    def sort_key(self) -> tuple[int, int, int, float, int]:
        return (
            _SEMANTIC_RANK.get(self.semantic, 0),
            _PROVENANCE_RANK.get(self.provenance, 0),
            1 if self.article_local else 0,
            self.confidence,
            -self.ordinal,
        )


def resolve_publication(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
) -> PublicationResolution:
    candidates = _dedupe_candidates(_collect_candidates(record, bundle))
    selectable = [item for item in candidates if item.selectable]

    if not selectable:
        profile = _profile(candidates, selected=None, conflict_values=())
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
    conflict_values = _conflict_values(selected, candidates)
    conflict = bool(conflict_values)
    confidence = min(selected.confidence, 0.45) if conflict else selected.confidence
    status = "conflicting" if conflict else ("weak" if confidence < 0.70 else "resolved")
    source = "conflicting_publication_evidence" if conflict else selected.source

    profile = _profile(candidates, selected=selected, conflict_values=conflict_values)
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

    for row in profile[:12]:
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
) -> Iterable[_Candidate]:
    metadata = record.raw_metadata
    ordinal = 0

    body_evidence = nested(metadata, "freshness", "body_publication_evidence", default={})
    if hasattr(body_evidence, "get"):
        value = text(body_evidence.get("value"))
        if value:
            source = text(body_evidence.get("source")) or "body_publication_evidence"
            raw = text(body_evidence.get("raw")) or value
            confidence_label = text(body_evidence.get("confidence")).lower()
            confidence = {"high": 0.98, "medium": 0.86, "low": 0.64}.get(
                confidence_label, 0.88
            )
            local = _body_source(source)
            yield _candidate(
                value,
                confidence,
                source,
                raw,
                semantic=_semantic_from_text(source + " " + raw),
                provenance="article_local_metadata" if local else "page_metadata",
                article_local=local,
                ordinal=ordinal,
            )
            ordinal += 1

    body = bundle.body_markdown or bundle.body_text or ""
    title = record.title_hint or bundle.raw_title
    for value, source, raw, semantic in _extract_article_local_dates(body, title):
        yield _candidate(
            value,
            0.96 if semantic != "updated" else 0.90,
            source,
            raw,
            semantic=semantic,
            provenance="article_header",
            article_local=True,
            ordinal=ordinal,
        )
        ordinal += 1

    resolved = text(nested(metadata, "freshness", "published_at_resolved"))
    if resolved:
        resolved_conf = text(
            nested(metadata, "freshness", "published_at_confidence")
        ).lower()
        resolved_source = text(
            nested(metadata, "freshness", "published_at_source")
        ) or "freshness_metadata"
        confidence = {"high": 0.95, "medium": 0.82, "low": 0.58}.get(
            resolved_conf, 0.72
        )
        local = _body_source(resolved_source)
        yield _candidate(
            resolved,
            confidence,
            resolved_source,
            resolved,
            semantic=_semantic_from_text(resolved_source),
            provenance="article_local_metadata" if local else "page_metadata",
            article_local=local,
            ordinal=ordinal,
        )
        ordinal += 1

    for raw in bundle.raw_dates:
        value = text(raw)
        if value:
            yield _candidate(
                value,
                0.76,
                "acquisition_raw_date",
                value,
                semantic=_semantic_from_text(value, default="unknown"),
                provenance="acquisition_metadata",
                article_local=False,
                ordinal=ordinal,
            )
            ordinal += 1

    for raw in record.published_at_hints:
        value = text(raw)
        if value:
            yield _candidate(
                value,
                0.68,
                "discovery_date_hint",
                value,
                semantic=_semantic_from_text(value, default="unknown"),
                provenance="discovery_metadata",
                article_local=False,
                ordinal=ordinal,
            )
            ordinal += 1

    url_date = _url_path_date(record.url)
    if url_date:
        yield _candidate(
            url_date,
            0.48,
            "url_path_date",
            url_date,
            semantic="unknown",
            provenance="url_path",
            article_local=False,
            ordinal=ordinal,
        )


def _candidate(
    value: str,
    confidence: float,
    source: str,
    raw: str,
    *,
    semantic: str,
    provenance: str,
    article_local: bool,
    ordinal: int,
) -> _Candidate:
    normalized, timezone_basis = normalize_publication_fact(value)
    return _Candidate(
        value=value,
        normalized=normalized,
        confidence=max(0.0, min(1.0, confidence)),
        source=source,
        raw=normalize_space(raw),
        semantic=semantic,
        provenance=provenance,
        article_local=article_local,
        timezone_basis=timezone_basis,
        ordinal=ordinal,
    )


def _dedupe_candidates(candidates: Iterable[_Candidate]) -> list[_Candidate]:
    seen: set[tuple[str, str, str, str]] = set()
    output: list[_Candidate] = []
    for candidate in candidates:
        key = (
            candidate.normalized,
            candidate.semantic,
            candidate.provenance,
            candidate.source,
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def _body_source(source: str) -> bool:
    lowered = (source or "").lower()
    return (
        lowered.startswith("body_")
        or "body_header" in lowered
        or "article_header" in lowered
        or "article_local" in lowered
    )


def _semantic_from_text(value: str, default: str = "published") -> str:
    lowered = normalize_space(value).lower()
    if re.search(r"\b(?:last\s+)?updated\b|\bmodified\b|更新|最後更新|最后更新", lowered):
        return "updated"
    if re.search(r"\boriginally\s+published\b|首次(?:发表|發表|发布|發布)|首发|首發", lowered):
        return "original_published"
    if re.search(r"\brepublished\b|\breprinted\b|转载日期|轉載日期|重刊", lowered):
        return "republished"
    if re.search(r"印发日期|印發日期|\bissued\b", lowered):
        return "issued"
    if re.search(r"\bcreated\b", lowered):
        return "created"
    if re.search(r"\bpublished\b|\bposted\b|发布时间|發布時間|发布日期|發布日期", lowered):
        return "published"
    return default


def _extract_article_local_dates(
    body: str,
    title: str,
) -> tuple[tuple[str, str, str, str], ...]:
    sample = _article_start(body, title)[:7000]
    patterns: tuple[tuple[str, str, str], ...] = (
        (
            r"(?:印发日期|印發日期)\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_issued_date",
            "issued",
        ),
        (
            r"(?:发布时间|發布時間|发布日期|發布日期|文章日期|出版时间|出版時間|来源日期|來源日期)"
            r"\s*[：:]?\s*((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_labeled_date",
            "published",
        ),
        (
            r"(?:更新日期|更新时间|更新時間|最后更新|最後更新)\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_updated_date",
            "updated",
        ),
        (
            r"(?:首次发表|首次發表|首次发布|首次發布|首发日期|首發日期)\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_original_published_date",
            "original_published",
        ),
        (
            r"(?<![\w\u4e00-\u9fff])日期\s*[：:]?\s*"
            r"((?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?)",
            "article_header_generic_date",
            "published",
        ),
        (
            r"(?:Originally\s+published)(?:\s+on)?\s*[:：-]?\s*"
            r"([A-Z][a-z]+\s+\d{1,2},\s+(?:19|20)\d{2}|(?:19|20)\d{2}-\d{1,2}-\d{1,2})",
            "article_header_original_published_date",
            "original_published",
        ),
        (
            r"(?:Published|Posted)(?:\s+on)?\s*[:：-]?\s*"
            r"([A-Z][a-z]+\s+\d{1,2},\s+(?:19|20)\d{2}|(?:19|20)\d{2}-\d{1,2}-\d{1,2})",
            "article_header_english_published_date",
            "published",
        ),
        (
            r"(?:Created)(?:\s+in|\s+on)?\s*[:：-]?\s*"
            r"([A-Z][a-z]+\s+\d{1,2},\s+(?:19|20)\d{2}|(?:19|20)\d{2}-\d{1,2}-\d{1,2})",
            "article_header_english_created_date",
            "created",
        ),
        (
            r"(?:Last\s+updated|Updated)(?:\s+on)?\s*[:：-]?\s*"
            r"([A-Z][a-z]+\s+\d{1,2},\s+(?:19|20)\d{2}|(?:19|20)\d{2}-\d{1,2}-\d{1,2})",
            "article_header_english_updated_date",
            "updated",
        ),
    )
    found: list[tuple[int, str, str, str, str]] = []
    for pattern, source, semantic in patterns:
        for match in re.finditer(pattern, sample, flags=re.IGNORECASE):
            found.append(
                (
                    match.start(),
                    match.group(1),
                    source,
                    normalize_space(match.group(0)),
                    semantic,
                )
            )
    found.sort(key=lambda item: item[0])
    return tuple((value, source, raw, semantic) for _, value, source, raw, semantic in found)


def _article_start(body: str, title: str) -> str:
    value = body or ""
    clean_title = normalize_space(title)
    if clean_title:
        position = value.find(clean_title)
        if 0 <= position <= 12000:
            return value[position:]
    return value[:18000]


def normalize_publication_fact(value: str) -> tuple[str, str]:
    raw = normalize_space(value)
    if not raw:
        return "", "unparsed"

    chinese = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    date_match = re.fullmatch(
        r"((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})",
        chinese,
    )
    if date_match:
        try:
            return (
                datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3)),
                ).date().isoformat(),
                "date_only",
            )
        except ValueError:
            pass

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            basis = "utc_to_bjt" if parsed.utcoffset() == timedelta(0) else "offset_to_bjt"
            return parsed.astimezone(_BJT).date().isoformat(), basis
        return parsed.date().isoformat(), "naive_local"
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is not None:
            basis = "utc_to_bjt" if parsed.utcoffset() == timedelta(0) else "offset_to_bjt"
            return parsed.astimezone(_BJT).date().isoformat(), basis
        return parsed.date().isoformat(), "naive_local"
    except (TypeError, ValueError, OverflowError):
        pass

    for pattern in ("%B %d, %Y", "%b %d, %Y", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat(), "date_only"
        except ValueError:
            continue
    return "", "unparsed"


def normalize_publication_date(value: str) -> str:
    return normalize_publication_fact(value)[0]


def _conflict_values(
    selected: _Candidate,
    candidates: list[_Candidate],
) -> tuple[str, ...]:
    if selected.semantic not in _PRIMARY_SEMANTICS:
        return ()

    comparable = [
        item
        for item in candidates
        if item.normalized
        and item.semantic == selected.semantic
        and item.confidence >= 0.72
        and _PROVENANCE_RANK.get(item.provenance, 0) >= _PROVENANCE_RANK["acquisition_metadata"]
    ]
    if selected.article_local:
        local_values = {item.normalized for item in comparable if item.article_local}
        return tuple(sorted(local_values)) if len(local_values) > 1 else ()

    values = {item.normalized for item in comparable}
    if len(values) < 2:
        return ()
    parsed = []
    for value in values:
        try:
            parsed.append(datetime.fromisoformat(value).date())
        except ValueError:
            continue
    if len(parsed) < 2:
        return ()
    if (max(parsed) - min(parsed)).days > 7:
        return tuple(sorted(values))
    return ()


def _profile(
    candidates: list[_Candidate],
    *,
    selected: _Candidate | None,
    conflict_values: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    conflicts = set(conflict_values)
    for candidate in candidates:
        if selected is not None and candidate is selected:
            relation = "selected"
        elif (
            selected is not None
            and candidate.normalized
            and candidate.normalized == selected.normalized
        ):
            relation = "supports"
        elif candidate.normalized in conflicts and candidate.semantic == (selected.semantic if selected else ""):
            relation = "conflicts"
        elif candidate.semantic in _CONTEXT_ONLY_SEMANTICS or candidate.provenance == "url_path":
            relation = "contextual"
        else:
            relation = "alternative"
        rows.append(
            {
                "source": candidate.source,
                "semantic": candidate.semantic,
                "provenance": candidate.provenance,
                "article_local": candidate.article_local,
                "raw": candidate.raw,
                "normalized": candidate.normalized,
                "confidence": round(candidate.confidence, 4),
                "timezone_basis": candidate.timezone_basis,
                "relation": relation,
            }
        )
    return tuple(rows)


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


def _url_path_date(url: str) -> str:
    path = urlsplit(text(url)).path
    for pattern in (
        r"/((?:19|20)\d{2})-(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])(?:/|$)",
        r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?:/|$)",
        r"(?:/|[_-])((?:19|20)\d{2})(0[1-9]|1[0-2])([0-3]\d)(?:[_./-]|$)",
    ):
        match = re.search(pattern, path)
        if not match:
            continue
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).date().isoformat()
        except ValueError:
            continue
    return ""


__all__ = [
    "PUBLICATION_VERSION",
    "PublicationResolution",
    "normalize_publication_date",
    "normalize_publication_fact",
    "resolve_publication",
]
