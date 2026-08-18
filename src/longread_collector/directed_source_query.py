from __future__ import annotations

import json
from typing import Any

DEFAULT_DIRECTED_QUERY_BY_LANGUAGE = {
    "zh": "最新 深度 调查 分析 长文",
    "en": "latest longform investigation analysis",
}


def _parser_config(source: dict[str, Any]) -> dict[str, Any]:
    raw = source.get("parser_config_json")
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def directed_query_for_source(source: dict[str, Any]) -> tuple[str, str]:
    """Resolve one directed fallback query without changing default behavior.

    Sources may opt into a custom Firecrawl directed-search query through the
    existing ``parser_config_json`` field using ``directed_search_query``.
    Missing, malformed, non-string, or blank overrides fall back exactly to the
    existing language default.

    Returns ``(query, provenance)`` where provenance is either
    ``source_override`` or ``language_default`` for auditability.
    """

    language = str(source.get("language", "en") or "en").strip().lower() or "en"
    config = _parser_config(source)
    override = config.get("directed_search_query")
    if isinstance(override, str):
        cleaned = " ".join(override.split()).strip()
        if cleaned:
            return cleaned, "source_override"
    return (
        DEFAULT_DIRECTED_QUERY_BY_LANGUAGE.get(
            language,
            DEFAULT_DIRECTED_QUERY_BY_LANGUAGE["en"],
        ),
        "language_default",
    )
