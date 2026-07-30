from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable

from .audit import record_auxiliary_error
from .models import DiscoveredURL, ExtractedArticle


def _as_int(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def update_source_registry_metrics(
    store: object,
    *,
    attempted_source_ids: Iterable[str],
    discovered: list[DiscoveredURL],
    articles: list[ExtractedArticle],
    completed_at: datetime,
) -> bool:
    """Update source diagnostics without blocking the main cache write."""
    try:
        attempted = {
            source_id for source_id in attempted_source_ids if source_id
        }
        if not attempted:
            return True
        discovered_counts = Counter(
            str(item.metadata.get("source_id", ""))
            for item in discovered
            if item.metadata.get("source_id")
        )
        extracted_counts = Counter()
        for item, article in zip(discovered, articles, strict=True):
            source_id = str(item.metadata.get("source_id", ""))
            if source_id and article.extraction_status == "success":
                extracted_counts[source_id] += 1

        worksheet = store.book.worksheet("source_registry")
        rows = worksheet.get_all_values()
        now = completed_at.strftime("%Y-%m-%d %H:%M:%S")
        for row_number, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            source_id = str(row[0]).strip()
            if source_id not in attempted:
                continue
            existing_discovered = _as_int(
                row[19] if len(row) > 19 else 0
            )
            existing_extracted = _as_int(
                row[20] if len(row) > 20 else 0
            )
            worksheet.update(
                range_name=f"R{row_number}:X{row_number}",
                values=[[
                    now,
                    row[18] if len(row) > 18 else "",
                    existing_discovered + discovered_counts.get(source_id, 0),
                    existing_extracted + extracted_counts.get(source_id, 0),
                    row[21] if len(row) > 21 else 0,
                    row[22] if len(row) > 22 else "",
                    now,
                ]],
                value_input_option="USER_ENTERED",
            )
        return True
    except Exception as exc:  # pragma: no cover - provider failures
        record_auxiliary_error(store, "source_registry_metrics", exc)
        return False
