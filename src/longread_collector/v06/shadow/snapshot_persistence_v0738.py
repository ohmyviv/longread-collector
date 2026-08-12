"""PR-7.3.8 lossless all-cell Discovery snapshot persistence.

PR-7.3.5 protected oversized ``metadata_json`` values from Google Sheets' 50k
single-cell limit. The 2026-08-12 scheduled ``pre_report`` Natural Shadow failed
with the same Sheets error even though the overflow sheet was never created,
proving that a different main-sheet field exceeded the limit. This version
applies the same lossless manifest/chunk contract to every snapshot cell while
keeping the main-sheet schema and overflow-sheet schema stable.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo

from ... import recall_instrumentation as _recall
from ...models import DiscoveredURL, ExtractedArticle
from ...normalization import canonicalize_url, domain_from_url
from .snapshot_persistence_v0735 import (
    SNAPSHOT_METADATA_CHUNK_SIZE,
    SNAPSHOT_METADATA_INLINE_LIMIT,
    SNAPSHOT_OVERFLOW_HEADERS,
    SNAPSHOT_OVERFLOW_SHEET,
)

SNAPSHOT_PERSISTENCE_VERSION = "snapshot-persistence-v0.6-pr7.3.8"
_OVERFLOW_BATCH_ROWS = 100
_INSTALLED = False


def _sheet_cell_units(value: str) -> int:
    """Return a defensive UTF-16 code-unit count for Sheet cell sizing."""

    return len(value.encode("utf-16-le")) // 2


def _ensure_overflow_sheet(store: Any) -> Any:
    try:
        ws = store.book.worksheet(SNAPSHOT_OVERFLOW_SHEET)
    except Exception:
        ws = store.book.add_worksheet(
            title=SNAPSHOT_OVERFLOW_SHEET,
            rows=20000,
            cols=len(SNAPSHOT_OVERFLOW_HEADERS),
        )
        ws.append_row(SNAPSHOT_OVERFLOW_HEADERS, value_input_option="RAW")
        ws.freeze(rows=1)
    header = ws.row_values(1)
    if header != SNAPSHOT_OVERFLOW_HEADERS:
        raise ValueError(
            f"{SNAPSHOT_OVERFLOW_SHEET} header mismatch: "
            f"expected {len(SNAPSHOT_OVERFLOW_HEADERS)} columns, got {len(header)}"
        )
    return ws


def _overflow_storage(
    *,
    row_snapshot_id: str,
    run_id: str,
    field_name: str,
    value: object,
) -> tuple[object, list[list[object]]]:
    """Return an inline value or a lossless manifest plus chunk rows.

    Non-string scalar values stay typed while small. Oversized values are stored
    exactly as the string that would otherwise be sent to Sheets. Metadata keeps
    the PR-7.3.5 row snapshot identity; newly supported non-metadata cells use a
    field-specific overflow id so multiple oversized cells in one row cannot
    collide, even when their payloads are identical.
    """

    text = "" if value is None else str(value)
    if (
        len(text) <= SNAPSHOT_METADATA_INLINE_LIMIT
        and _sheet_cell_units(text) <= SNAPSHOT_METADATA_INLINE_LIMIT
    ):
        return value, []

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if field_name == "metadata_json":
        # Preserve the PR-7.3.5 manifest/chunk identity contract exactly: the
        # overflow snapshot_id is the same ID written in the main snapshot row.
        overflow_id = row_snapshot_id
        manifest_key = "_snapshot_metadata_overflow"
    else:
        overflow_id = hashlib.sha256(
            f"{row_snapshot_id}|{field_name}".encode("utf-8")
        ).hexdigest()[:24]
        manifest_key = "_snapshot_cell_overflow"
    chunks = [
        text[offset : offset + SNAPSHOT_METADATA_CHUNK_SIZE]
        for offset in range(0, len(text), SNAPSHOT_METADATA_CHUNK_SIZE)
    ]
    chunk_count = len(chunks)
    manifest_payload = {
        "version": SNAPSHOT_PERSISTENCE_VERSION,
        "sheet": SNAPSHOT_OVERFLOW_SHEET,
        "snapshot_id": overflow_id,
        "sha256": digest,
        "chars": len(text),
        "utf16_units": _sheet_cell_units(text),
        "chunks": chunk_count,
    }
    if field_name != "metadata_json":
        manifest_payload.update(
            {
                "row_snapshot_id": row_snapshot_id,
                "field": field_name,
            }
        )
    manifest = json.dumps(
        {manifest_key: manifest_payload},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    overflow_rows = [
        [
            overflow_id,
            run_id,
            digest,
            len(text),
            index,
            chunk_count,
            chunk,
        ]
        for index, chunk in enumerate(chunks, start=1)
    ]
    return manifest, overflow_rows


def _append_overflow_rows(ws: Any, rows: list[list[object]]) -> None:
    for start in range(0, len(rows), _OVERFLOW_BATCH_ROWS):
        batch = rows[start : start + _OVERFLOW_BATCH_ROWS]
        ws.append_rows(
            batch,
            value_input_option="RAW",
            table_range="A:G",
        )


def _guard_row_cells(
    *,
    row_snapshot_id: str,
    run_id: str,
    row: list[object],
) -> tuple[list[object], list[list[object]]]:
    guarded: list[object] = []
    overflow_rows: list[list[object]] = []
    for field_name, value in zip(_recall.SNAPSHOT_HEADERS, row, strict=True):
        stored, chunks = _overflow_storage(
            row_snapshot_id=row_snapshot_id,
            run_id=run_id,
            field_name=field_name,
            value=value,
        )
        guarded.append(stored)
        overflow_rows.extend(chunks)
    return guarded, overflow_rows


def hardened_append_snapshot_rows(
    store: Any,
    *,
    run_id: str,
    pair_list: list[tuple[DiscoveredURL, ExtractedArticle]],
    state: _recall.SnapshotCaptureState,
) -> int:
    """Persist the full Discovery snapshot with lossless protection on every cell."""

    if not state.discoveries:
        return 0

    processed: dict[str, tuple[DiscoveredURL, ExtractedArticle]] = {}
    for discovered, article in pair_list:
        processed[canonicalize_url(discovered.url)] = (discovered, article)

    captured_at = datetime.now(ZoneInfo(store.settings.timezone)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows: list[list[object]] = []
    overflow_rows: list[list[object]] = []

    for ordinal, captured in enumerate(state.discoveries, start=1):
        item = captured.item
        canonical = canonicalize_url(item.url)
        processed_pair = processed.get(canonical)
        article = processed_pair[1] if processed_pair else None
        snapshot_id = hashlib.sha256(
            f"{run_id}|{canonical}|{ordinal}".encode("utf-8")
        ).hexdigest()[:24]
        metadata = dict(item.metadata or {})
        metadata_payload = json.dumps(
            metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        raw_row: list[object] = [
            snapshot_id,
            run_id,
            captured_at,
            state.query_group,
            str(metadata.get("source_id", "")),
            item.discovery_method,
            item.query_or_source,
            item.url,
            canonical,
            domain_from_url(canonical),
            item.title,
            _recall.normalize_title(item.title),
            item.description,
            item.published_at,
            article.language if article else item.language,
            item.rank,
            captured.prefilter_status,
            captured.prefilter_reject_reason,
            article.article_id if article else "",
            article.extraction_status if article else "",
            article.extractor_used if article else "",
            str(bool(article and article.eligible_for_editor)).upper(),
            article.candidate_disposition if article else "",
            article.reject_reason if article else "",
            article.canonical_source if article else "",
            article.content_cluster_id if article else "",
            article.source_relationship if article else "",
            article.original_url if article else "",
            metadata_payload,
        ]
        guarded_row, item_overflow_rows = _guard_row_cells(
            row_snapshot_id=snapshot_id,
            run_id=run_id,
            row=raw_row,
        )
        rows.append(guarded_row)
        overflow_rows.extend(item_overflow_rows)

    # Chunks are persisted first. Any overflow or main-row failure propagates to
    # the existing recall wrapper, which records snapshot_error and keeps
    # full_snapshot_invariant false. Orphaned chunks are uniquely run/cell scoped.
    if overflow_rows:
        overflow_ws = _ensure_overflow_sheet(store)
        _append_overflow_rows(overflow_ws, overflow_rows)

    ws = _recall._ensure_snapshot_sheet(store)
    ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A:AC")
    return len(rows)


def install_snapshot_persistence_hardening() -> None:
    """Install the PR-7.3.8 all-cell writer into the frozen recall hook."""

    global _INSTALLED
    if _INSTALLED:
        return
    _recall._append_snapshot_rows = hardened_append_snapshot_rows
    _INSTALLED = True


__all__ = [
    "SNAPSHOT_METADATA_CHUNK_SIZE",
    "SNAPSHOT_METADATA_INLINE_LIMIT",
    "SNAPSHOT_OVERFLOW_HEADERS",
    "SNAPSHOT_OVERFLOW_SHEET",
    "SNAPSHOT_PERSISTENCE_VERSION",
    "hardened_append_snapshot_rows",
    "install_snapshot_persistence_hardening",
]
