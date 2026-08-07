"""Evidence helpers shared by the v0.6 canonical layer."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from ..contracts import Evidence, StageName

CANONICAL_STAGE_VERSION = "canonical-v0.6-pr2"


def nested(mapping: Mapping[str, Any] | None, *path: str, default: Any = None) -> Any:
    current: Any = mapping or {}
    for key in path:
        if not isinstance(current, Mapping):
            return default
        current = current.get(key, default)
    return current


def text(value: Any) -> str:
    return str(value or "").strip()


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", text(value)).strip()


def host(url: str) -> str:
    return urlsplit(text(url)).netloc.lower().removeprefix("www.")


def different_host(left: str, right: str) -> bool:
    a, b = host(left), host(right)
    return bool(a and b and a != b)


def body_heading(metadata: Mapping[str, Any]) -> str:
    return text(nested(metadata, "content_identity", "body_heading"))


def body_prose_chars(metadata: Mapping[str, Any], fallback: int = 0) -> int:
    value = nested(metadata, "content_metrics", "body_prose_chars", default=fallback)
    try:
        return max(0, int(value or fallback))
    except (TypeError, ValueError):
        return max(0, int(fallback or 0))


def heading_count(metadata: Mapping[str, Any]) -> int:
    value = nested(metadata, "content_metrics", "heading_count", default=0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def video_count(metadata: Mapping[str, Any]) -> int:
    value = nested(metadata, "content_metrics", "video_count", default=0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def external_link(metadata: Mapping[str, Any]) -> str:
    for path in (
        ("discovery", "external_link"),
        ("discovery", "external_target_url"),
        ("content_identity", "external_target_url"),
    ):
        value = text(nested(metadata, *path))
        if value.startswith(("http://", "https://")):
            return value
    return ""


def make_evidence(
    item_id: str,
    evidence_type: str,
    field: str,
    value: Any,
    *,
    confidence: float,
    excerpt: str = "",
    extractor: str = "canonical_pr2",
) -> Evidence:
    seed = f"{item_id}|{evidence_type}|{field}|{normalize_space(value)}"
    evidence_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return Evidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        source_stage=StageName.CANONICAL,
        field=field,
        value=value,
        confidence=max(0.0, min(1.0, float(confidence))),
        excerpt=excerpt[:500],
        extractor=extractor,
    )


def first_match(patterns: tuple[str, ...], value: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return normalize_space(match.group(1))
    return ""


__all__ = [
    "CANONICAL_STAGE_VERSION",
    "body_heading",
    "body_prose_chars",
    "different_host",
    "external_link",
    "first_match",
    "heading_count",
    "host",
    "make_evidence",
    "nested",
    "normalize_space",
    "text",
    "video_count",
]
