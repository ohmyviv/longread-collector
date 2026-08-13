from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CollectorRuntimeConfig:
    max_urls_per_run: int = 32
    max_concurrency_no_jina_key: int = 2
    cache_hours: int = 168
    firecrawl_fallback_daily_limit: int = 3
    directed_source_scans_per_run: int = 2
    directed_source_results_per_query: int = 4
    directed_source_freshness: str = "qdr:d3"
    native_source_scans_per_run: int = 8
    native_source_results_per_source: int = 6
    native_source_timeout_seconds: int = 15
    native_source_concurrency: int = 10
    native_source_freshness_days: int = 3
    native_freshness_policy_enabled: bool = False
    native_freshness_max_per_run: int = 0
    native_freshness_sources_by_group: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    source_chase_max_per_run: int = 3
    source_chase_results_per_query: int = 4
    source_chase_freshness: str = "qdr:m"
    source_chase_max_depth: int = 1
    source_registry_writeback: bool = True
    shadow_ab_writeback: bool = True


def _as_int(
    value: Any,
    default: int,
    *,
    minimum: int = 0,
    maximum: int = 1000,
) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().upper()
    if normalized in {"TRUE", "1", "YES", "Y"}:
        return True
    if normalized in {"FALSE", "0", "NO", "N"}:
        return False
    return default


def _as_source_groups(value: Any) -> dict[str, tuple[str, ...]]:
    if isinstance(value, dict):
        raw = value
    else:
        try:
            raw = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    if not isinstance(raw, dict):
        return {}

    result: dict[str, tuple[str, ...]] = {}
    for group, source_values in raw.items():
        group_id = str(group or "").strip()
        if not group_id:
            continue
        if isinstance(source_values, str):
            values = [
                item.strip()
                for item in source_values.replace(",", "|").split("|")
                if item.strip()
            ]
        elif isinstance(source_values, (list, tuple)):
            values = [str(item).strip() for item in source_values if str(item).strip()]
        else:
            continue
        result[group_id] = tuple(dict.fromkeys(values))
    return result


def load_collector_runtime_config(store: object) -> CollectorRuntimeConfig:
    worksheet = store.book.worksheet("collector_config")
    rows = worksheet.get_all_records()
    active = {
        str(row.get("config_key", "")).strip(): row.get("value")
        for row in rows
        if str(row.get("status", "")).strip().lower() == "active"
    }
    runtime = CollectorRuntimeConfig(
        max_urls_per_run=_as_int(
            active.get("max_urls_per_run"), 32, minimum=1, maximum=100
        ),
        max_concurrency_no_jina_key=_as_int(
            active.get("max_concurrency_no_jina_key"), 2, minimum=1, maximum=20
        ),
        cache_hours=_as_int(
            active.get("cache_hours"), 168, minimum=1, maximum=24 * 30
        ),
        firecrawl_fallback_daily_limit=_as_int(
            active.get("firecrawl_fallback_daily_limit"), 3, maximum=100
        ),
        directed_source_scans_per_run=_as_int(
            active.get("directed_source_scans_per_run"), 2, maximum=20
        ),
        directed_source_results_per_query=_as_int(
            active.get("directed_source_results_per_query"), 4, minimum=1, maximum=10
        ),
        directed_source_freshness=str(
            active.get("directed_source_freshness") or "qdr:d3"
        ).strip(),
        native_source_scans_per_run=_as_int(
            active.get("native_source_scans_per_run"), 8, minimum=1, maximum=50
        ),
        native_source_results_per_source=_as_int(
            active.get("native_source_results_per_source"), 6, minimum=1, maximum=20
        ),
        native_source_timeout_seconds=_as_int(
            active.get("native_source_timeout_seconds"), 15, minimum=3, maximum=60
        ),
        native_source_concurrency=_as_int(
            active.get("native_source_concurrency"), 10, minimum=1, maximum=30
        ),
        native_source_freshness_days=_as_int(
            active.get("native_source_freshness_days"), 3, minimum=1, maximum=14
        ),
        native_freshness_policy_enabled=_as_bool(
            active.get("native_freshness_policy_enabled"), False
        ),
        native_freshness_max_per_run=_as_int(
            active.get("native_freshness_max_per_run"), 0, minimum=0, maximum=50
        ),
        native_freshness_sources_by_group=_as_source_groups(
            active.get("native_freshness_sources_by_group")
        ),
        source_chase_max_per_run=_as_int(
            active.get("source_chase_max_per_run"), 3, maximum=10
        ),
        source_chase_results_per_query=_as_int(
            active.get("source_chase_results_per_query"), 4, minimum=1, maximum=10
        ),
        source_chase_freshness=str(
            active.get("source_chase_freshness") or "qdr:m"
        ).strip(),
        source_chase_max_depth=_as_int(
            active.get("source_chase_max_depth"), 1, maximum=1
        ),
        source_registry_writeback=_as_bool(
            active.get("source_registry_writeback"), True
        ),
        shadow_ab_writeback=_as_bool(active.get("shadow_ab_writeback"), True),
    )

    # Environment variables remain bootstrap defaults for GitHub Actions. Once
    # the Sheet is reachable, active collector_config values become authoritative.
    settings = getattr(store, "settings", None)
    if settings is not None:
        settings.max_urls_per_run = runtime.max_urls_per_run
        settings.cache_hours = runtime.cache_hours
        settings.firecrawl_fallback_daily_limit = (
            runtime.firecrawl_fallback_daily_limit
        )
        if not getattr(settings, "jina_api_key", None):
            settings.max_concurrency = runtime.max_concurrency_no_jina_key
    return runtime
