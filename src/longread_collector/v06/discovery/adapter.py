"""Read-only adaptation of existing discovery outputs into v0.6 contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from ...normalization import canonicalize_url
from ..audit.events import make_stage_event
from ..contracts import (
    DiscoveryRecord,
    Evidence,
    FlowStatus,
    RunContext,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)

DISCOVERY_ADAPTER_VERSION = "discovery-adapter-v0.6-pr6"
CONTRACT_SCHEMA_VERSION = "v06-contracts-v1"


@dataclass(frozen=True, slots=True)
class DiscoveryAdaptation:
    record: DiscoveryRecord
    event: StageEvent


def _value(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _metadata(item: Any) -> Mapping[str, Any]:
    value = _value(item, "metadata", {})
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(url: str) -> str:
    try:
        return canonicalize_url(url)
    except Exception:
        return _text(url)


def _confidence_value(value: Any, default: float) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    normalized = _text(value).lower()
    if normalized in {"high", "authoritative", "verified"}:
        return 0.96
    if normalized in {"medium", "moderate"}:
        return 0.75
    if normalized in {"low", "weak"}:
        return 0.45
    return default


def _route_date_confidence(method: str) -> float:
    normalized = _text(method).lower()
    if normalized in {"rss", "atom"}:
        return 0.94
    if normalized == "news_sitemap":
        return 0.97
    if normalized == "sitemap":
        # Generic sitemap dates are often modification times.
        return 0.72
    if normalized in {"section_scan", "homepage"}:
        return 0.68
    if normalized == "firecrawl_search":
        return 0.45
    return 0.60


def _unique(values: list[str]) -> tuple[str, ...]:
    output: list[str] = []
    for value in values:
        clean = _text(value)
        if clean and clean not in output:
            output.append(clean)
    return tuple(output)


def _publication_hints(item: Any, metadata: Mapping[str, Any]) -> tuple[str, ...]:
    values = [_text(_value(item, "published_at", ""))]
    for key in (
        "published_at",
        "publishedAt",
        "publishedTime",
        "published_date",
        "datePublished",
        "date",
    ):
        values.append(_text(metadata.get(key)))
    freshness = metadata.get("freshness")
    if isinstance(freshness, Mapping):
        values.append(_text(freshness.get("published_at_resolved")))
        evidence = freshness.get("evidence")
        if isinstance(evidence, (list, tuple)):
            for entry in evidence:
                if isinstance(entry, Mapping) and _text(entry.get("role")).lower() == "published":
                    values.append(_text(entry.get("value")))
    return _unique(values)


def _publication_evidence(
    *,
    item_id: str,
    method: str,
    hints: tuple[str, ...],
    metadata: Mapping[str, Any],
) -> tuple[Evidence, ...]:
    if not hints:
        return ()
    route_confidence = _route_date_confidence(method)
    explicit_confidence = metadata.get("published_at_confidence")
    freshness = metadata.get("freshness")
    if isinstance(freshness, Mapping):
        explicit_confidence = freshness.get(
            "published_at_confidence",
            explicit_confidence,
        )
    first_confidence = _confidence_value(explicit_confidence, route_confidence)
    evidence: list[Evidence] = []
    for ordinal, hint in enumerate(hints, start=1):
        confidence = first_confidence if ordinal == 1 else min(first_confidence, 0.82)
        evidence.append(
            Evidence(
                evidence_id=f"{item_id}-discovery-date-{ordinal:02d}",
                evidence_type="publication_hint",
                source_stage=StageName.DISCOVERY,
                field="published_at_hint",
                value=hint,
                confidence=confidence,
                extractor=method,
            )
        )
    return tuple(evidence)


def _external_link(metadata: Mapping[str, Any]) -> str:
    for key in (
        "external_link",
        "external_url",
        "original_url",
        "source_url",
        "outbound_primary_url",
    ):
        value = _text(metadata.get(key))
        if value.startswith(("http://", "https://")):
            return value
    return ""


class DiscoveryAdapter:
    """Adapt legacy/current discovery result shapes without importing their model."""

    stage_version = DISCOVERY_ADAPTER_VERSION

    def adapt(
        self,
        context: RunContext,
        item: Any,
        *,
        ordinal: int = 0,
        created_at_bj: str = "",
    ) -> DiscoveryAdaptation:
        metadata = _metadata(item)
        url = _text(_value(item, "url", ""))
        method = _text(_value(item, "discovery_method", "")) or _text(
            metadata.get("native_method")
        ) or "unknown"
        query_or_source = _text(_value(item, "query_or_source", "")) or _text(
            _value(item, "query_id", "")
        )
        rank = int(_value(item, "rank", 0) or 0)
        canonical = _canonical(url)
        item_seed = f"{canonical}|{method}|{query_or_source}|{rank}|{ordinal}"
        item_id = hashlib.sha256(item_seed.encode("utf-8")).hexdigest()[:20]
        discovery_id = hashlib.sha256(
            f"{context.run_id}|{item_seed}".encode("utf-8")
        ).hexdigest()[:24]
        hints = _publication_hints(item, metadata)
        source_id = _text(metadata.get("source_id")) or query_or_source
        title = _text(_value(item, "title", ""))
        description = _text(_value(item, "description", ""))
        external_link = _external_link(metadata)

        evidence: list[Evidence] = [
            Evidence(
                evidence_id=f"{item_id}-discovery-route",
                evidence_type="discovery_route",
                source_stage=StageName.DISCOVERY,
                field="discovery_method",
                value={
                    "method": method,
                    "source_id": source_id,
                    "endpoint": _text(metadata.get("native_endpoint")),
                    "priority_tier": _text(metadata.get("priority_tier")),
                },
                confidence=1.0,
                extractor=method,
            )
        ]
        evidence.extend(
            _publication_evidence(
                item_id=item_id,
                method=method,
                hints=hints,
                metadata=metadata,
            )
        )
        if external_link:
            evidence.append(
                Evidence(
                    evidence_id=f"{item_id}-external-link",
                    evidence_type="external_link_hint",
                    source_stage=StageName.DISCOVERY,
                    field="external_link_hint",
                    value=external_link,
                    confidence=0.85,
                    extractor=method,
                )
            )

        record = DiscoveryRecord(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=self.stage_version,
            run_id=context.run_id,
            item_id=item_id,
            discovery_id=discovery_id,
            url=url,
            canonical_url_hint=canonical,
            title_hint=title,
            description_hint=description,
            published_at_hints=hints,
            source_id=source_id,
            discovery_method=method,
            query_or_section=query_or_source,
            rank=rank,
            route_status=TechnicalStatus.SUCCESS,
            external_link_hint=external_link,
            raw_metadata=metadata,
            evidence=tuple(evidence),
        )
        event = make_stage_event(
            run_id=context.run_id,
            item_id=item_id,
            stage=StageName.DISCOVERY,
            event_type=StageEventType.DISCOVERY_RESULT,
            stage_version=self.stage_version,
            technical_status=TechnicalStatus.SUCCESS,
            flow_status=FlowStatus.PASS,
            reason_code="discovery_record_adapted",
            created_at_bj=created_at_bj or context.started_at_bj,
            ordinal=ordinal,
            attributes={
                "url": url,
                "canonical_url_hint": canonical,
                "source_id": source_id,
                "discovery_method": method,
                "rank": rank,
                "published_hint_count": len(hints),
                "external_link_hint": external_link,
            },
            evidence=tuple(evidence),
        )
        return DiscoveryAdaptation(record=record, event=event)


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "DISCOVERY_ADAPTER_VERSION",
    "DiscoveryAdaptation",
    "DiscoveryAdapter",
]
