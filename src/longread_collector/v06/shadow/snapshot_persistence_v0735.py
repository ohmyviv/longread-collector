"""PR-7.3.5 hardening for Natural Shadow snapshot persistence.

Google Sheets limits a single cell to 50,000 characters. Discovery metadata is
normally compact, but an unusually large metadata payload can exceed that limit
and cause the entire ``collector_discovery_snapshot`` append to fail. This module
preserves the existing main-sheet schema and moves only oversized ``metadata_json``
payloads into a lossless chunk sheet with a hash-verified manifest.
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

SNAPSHOT_PERSISTENCE_VERSION = "snapshot-persistence-v0.6-pr7.3.5"
SNAPSHOT_OVERFLOW_SHEET = "collector_discovery_snapshot_overflow"
SNAPSHOT_OVERFLOW_HEADERS = [
    "snapshot_id",
    "collector_run_id",
    "payload_sha256",
    "payload_chars",
    "chunk_index",
    "chunk_count",
    "metadata_chunk",
]

# Keep well below the documented 50k cell ceiling. The inline threshold is lower
# than the chunk size only so normal metadata stays untouched while overflow
# manifests retain ample headroom for future fields.
SNAPSHOT_METADATA_INLINE_LIMIT = 45_000
SNAPSHOT_METADATA_CHUNK_SIZE = 40_000
_OVERFLOW_BATCH_ROWS = 100
_INSTALLED = False


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


def _metadata_storage(
    *,
    snapshot_id: str,
    run_id: str,
    metadata: dict[str, Any],
) -> tuple[str, list[list[object]]]:
    payload = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    if len(payload) <= SNAPSHOT_METADATA_INLINE_LIMIT:
        return payload, []

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    chunks = [
        payload[offset : offset + SNAPSHOT_METADATA_CHUNK_SIZE]
        for offset in range(0, len(payload), SNAPSHOT_METADATA_CHUNK_SIZE)
    ]
    chunk_count = len(chunks)
    manifest = json.dumps(
        {
            "_snapshot_metadata_overflow": {
                "version": SNAPSHOT_PERSISTENCE_VERSION,
                "sheet": SNAPSHOT_OVERFLOW_SHEET,
                "snapshot_id": snapshot_id,
                "sha256": digest,
                "chars": len(payload),
                "chunks": chunk_count,
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    overflow_rows = [
        [
            snapshot_id,
            run_id,
            digest,
            len(payload),
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


def hardened_append_snapshot_rows(
    store: Any,
    *,
    run_id: str,
    pair_list: list[tuple[DiscoveredURL, ExtractedArticle]],
    state: _recall.SnapshotCaptureState,
) -> int:
    """Persist the full discovery snapshot without truncating oversized metadata.

    Overflow chunks are written before the main rows. Any failure propagates to
    the existing recall wrapper, which marks ``snapshot_error`` and therefore
    prevents ``full_snapshot_invariant`` from passing. Partial overflow rows may
    remain after a failed API call, but they are uniquely scoped by run/snapshot
    IDs and can never be mistaken for a successful persisted snapshot.
    """

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
        metadata_cell, item_overflow_rows = _metadata_storage(
            snapshot_id=snapshot_id,
            run_id=run_id,
            metadata=metadata,
        )
        overflow_rows.extend(item_overflow_rows)

        rows.append(
            [
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
                metadata_cell,
            ]
        )

    if overflow_rows:
        overflow_ws = _ensure_overflow_sheet(store)
        _append_overflow_rows(overflow_ws, overflow_rows)

    ws = _recall._ensure_snapshot_sheet(store)
    ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A:AC")
    return len(rows)


def install_snapshot_persistence_hardening() -> None:
    """Install the hardened writer into the already-frozen recall hook."""

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
