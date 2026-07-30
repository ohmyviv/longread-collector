from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CollectorRuntimeConfig:
    directed_source_scans_per_run: int = 2
    directed_source_results_per_query: int = 4
    directed_source_freshness: str = "qdr:d3"
    source_chase_max_per_run: int = 3
    source_chase_results_per_query: int = 4
    source_chase_freshness: str = "qdr:m"
    source_chase_max_depth: int = 1
    source_registry_writeback: bool = True
    shadow_ab_writeback: bool = True


def _as_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 100) -> int:
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


def load_collector_runtime_config(store: object) -> CollectorRuntimeConfig:
    worksheet = store.book.worksheet("collector_config")
    rows = worksheet.get_all_records()
    active = {
        str(row.get("config_key", "")).strip(): row.get("value")
        for row in rows
        if str(row.get("status", "")).strip().lower() == "active"
    }
    return CollectorRuntimeConfig(
        directed_source_scans_per_run=_as_int(
            active.get("directed_source_scans_per_run"), 2, maximum=10
        ),
        directed_source_results_per_query=_as_int(
            active.get("directed_source_results_per_query"), 4, minimum=1, maximum=10
        ),
        directed_source_freshness=str(
            active.get("directed_source_freshness") or "qdr:d3"
        ).strip(),
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
