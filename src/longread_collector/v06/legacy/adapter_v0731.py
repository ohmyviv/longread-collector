"""PR-7.3.1 legacy-to-v0.6 publication-evidence bridge.

The frozen v0.5.6m control already records structured post-extraction date
candidates in ``article.metadata['freshness']['evidence']``.  The original v0.6
compatibility adapter flattened those facts into ``AcquisitionBundle.raw_dates``
and therefore lost source/role/confidence provenance.  This wrapper preserves
that evidence for L4 without changing legacy control behavior or performing any
network I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ...models import DiscoveredURL, ExtractedArticle
from ..contracts import Evidence, RunContext, StageName
from .adapter import (
    LegacyAdaptedItem,
    LegacyAdaptedRun,
    LegacyV056mAdapter as _BaseLegacyV056mAdapter,
)

LEGACY_ADAPTER_VERSION = "v06-legacy-v056m-adapter-v2-pr7.3.1"
PUBLICATION_EVIDENCE_BRIDGE_VERSION = "legacy-publication-evidence-bridge-v0.6-pr7.3.1"
_PUBLICATION_EVIDENCE_TYPE = "legacy_publication_date_candidate"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _confidence(value: Any) -> float:
    label = _text(value).lower()
    if label == "high":
        return 0.98
    if label == "medium":
        return 0.86
    if label == "low":
        return 0.58
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.72


def _candidate_key(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(value.get("value")),
        _text(value.get("source")),
        _text(value.get("role")) or "published",
    )


def _publication_candidates(article: ExtractedArticle) -> tuple[Mapping[str, Any], ...]:
    freshness = article.metadata.get("freshness", {})
    if not isinstance(freshness, Mapping):
        return ()

    rows: list[Mapping[str, Any]] = []
    raw_rows = freshness.get("evidence", ())
    if isinstance(raw_rows, (list, tuple)):
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            value = _text(raw.get("value"))
            source = _text(raw.get("source"))
            if not value or not source:
                continue
            rows.append(raw)

    body = freshness.get("body_publication_evidence", {})
    if isinstance(body, Mapping) and _text(body.get("value")):
        body_row = {
            "value": _text(body.get("value")),
            "source": _text(body.get("source")) or "body_publication_evidence",
            "confidence": _text(body.get("confidence")) or "medium",
            "raw": _text(body.get("raw")) or _text(body.get("value")),
            "role": "published",
            "priority": 110,
        }
        existing = {_candidate_key(row) for row in rows}
        if _candidate_key(body_row) not in existing:
            rows.insert(0, body_row)

    return tuple(rows)


def _publication_evidence(
    *,
    item_id: str,
    article: ExtractedArticle,
) -> tuple[Evidence, ...]:
    output: list[Evidence] = []
    seen: set[tuple[str, str, str]] = set()
    for ordinal, row in enumerate(_publication_candidates(article), start=1):
        key = _candidate_key(row)
        if key in seen:
            continue
        seen.add(key)
        value = {
            "value": key[0],
            "source": key[1],
            "role": key[2],
            "confidence": _text(row.get("confidence")) or "medium",
            "priority": row.get("priority", 0),
            "raw": _text(row.get("raw")) or key[0],
        }
        output.append(
            Evidence(
                evidence_id=f"{item_id}-legacy-publication-{ordinal:02d}",
                evidence_type=_PUBLICATION_EVIDENCE_TYPE,
                source_stage=StageName.ACQUISITION,
                field="publication_date_candidate",
                value=value,
                confidence=_confidence(value["confidence"]),
                excerpt=(
                    f"source={value['source']}; role={value['role']}; "
                    f"priority={value['priority']}"
                ),
                extractor=PUBLICATION_EVIDENCE_BRIDGE_VERSION,
            )
        )
    return tuple(output)


class LegacyV056mAdapter(_BaseLegacyV056mAdapter):
    """Preserve v0.5.6m date provenance while keeping all legacy facts intact."""

    def adapt_item(
        self,
        *,
        context: RunContext,
        discovered: DiscoveredURL,
        article: ExtractedArticle,
        created_at_bj: str = "",
    ) -> LegacyAdaptedItem:
        adapted = super().adapt_item(
            context=context,
            discovered=discovered,
            article=article,
            created_at_bj=created_at_bj,
        )
        publication = _publication_evidence(item_id=adapted.acquisition.item_id, article=article)
        if not publication:
            return adapted
        acquisition = replace(
            adapted.acquisition,
            evidence=(*adapted.acquisition.evidence, *publication),
        )
        return replace(adapted, acquisition=acquisition)


__all__ = [
    "LEGACY_ADAPTER_VERSION",
    "PUBLICATION_EVIDENCE_BRIDGE_VERSION",
    "LegacyAdaptedItem",
    "LegacyAdaptedRun",
    "LegacyV056mAdapter",
]
