from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url

LOGGER = logging.getLogger(__name__)

SNAPSHOT_HEADERS = [
    "snapshot_id", "collector_run_id", "captured_at_bj", "query_group", "source_id",
    "discovery_method", "query_or_source", "url", "url_canonical", "domain", "title",
    "title_norm", "description", "published_at", "language", "discovered_rank",
    "prefilter_status", "prefilter_reject_reason", "article_id", "extraction_status",
    "extractor_used", "eligible_for_editor", "candidate_disposition", "reject_reason",
    "canonical_source", "content_cluster_id", "source_relationship", "original_url",
    "metadata_json",
]


@dataclass
class CapturedDiscovery:
    item: DiscoveredURL
    prefilter_status: str
    prefilter_reject_reason: str = ""


@dataclass
class SnapshotCaptureState:
    query_group: str
    discoveries: list[CapturedDiscovery] = field(default_factory=list)
    snapshot_error: str = ""


_CAPTURE_STATE: ContextVar[SnapshotCaptureState | None] = ContextVar(
    "longread_snapshot_capture_state", default=None
)
_INSTALLED = False


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(char for char in normalized if char.isalnum())


def begin_snapshot_capture(query_group: str) -> Token:
    return _CAPTURE_STATE.set(SnapshotCaptureState(query_group=query_group or "all"))


def current_snapshot_capture() -> SnapshotCaptureState | None:
    return _CAPTURE_STATE.get()


def end_snapshot_capture(token: Token) -> None:
    _CAPTURE_STATE.reset(token)


def _ensure_snapshot_sheet(store: Any) -> Any:
    try:
        ws = store.book.worksheet("collector_discovery_snapshot")
    except Exception:
        ws = store.book.add_worksheet(
            title="collector_discovery_snapshot", rows=10000, cols=len(SNAPSHOT_HEADERS)
        )
        ws.append_row(SNAPSHOT_HEADERS, value_input_option="RAW")
        ws.freeze(rows=1)
    header = ws.row_values(1)
    if header != SNAPSHOT_HEADERS:
        raise ValueError(
            "collector_discovery_snapshot header mismatch: "
            f"expected {len(SNAPSHOT_HEADERS)} columns, got {len(header)}"
        )
    return ws


def _append_snapshot_rows(
    store: Any,
    *,
    run_id: str,
    pair_list: list[tuple[DiscoveredURL, ExtractedArticle]],
    state: SnapshotCaptureState,
) -> int:
    if not state.discoveries:
        return 0

    processed: dict[str, tuple[DiscoveredURL, ExtractedArticle]] = {}
    for discovered, article in pair_list:
        processed[canonicalize_url(discovered.url)] = (discovered, article)

    captured_at = datetime.now(ZoneInfo(store.settings.timezone)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows: list[list[object]] = []
    for ordinal, captured in enumerate(state.discoveries, start=1):
        item = captured.item
        canonical = canonicalize_url(item.url)
        processed_pair = processed.get(canonical)
        article = processed_pair[1] if processed_pair else None
        snapshot_id = hashlib.sha256(
            f"{run_id}|{canonical}|{ordinal}".encode("utf-8")
        ).hexdigest()[:24]
        metadata = dict(item.metadata or {})
        rows.append([
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
            normalize_title(item.title),
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
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        ])

    ws = _ensure_snapshot_sheet(store)
    ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A:AC")
    return len(rows)


def install_recall_snapshot_hooks(pipeline_module: Any, store_cls: type) -> None:
    """Instrument v0.5 discovery without duplicating the collection pipeline."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_filter = pipeline_module.filter_discovered
    original_upsert = store_cls.upsert_articles

    def wrapped_filter(
        discovered: list[DiscoveredURL],
        *,
        max_urls: int,
        max_per_domain: int = 2,
    ):
        accepted, rejected = original_filter(
            discovered, max_urls=max_urls, max_per_domain=max_per_domain
        )
        state = _CAPTURE_STATE.get()
        if state is not None:
            accepted_counts: dict[str, int] = {}
            for accepted_item in accepted:
                canonical = canonicalize_url(accepted_item.url)
                accepted_counts[canonical] = accepted_counts.get(canonical, 0) + 1
            rejection_queues: dict[str, list[str]] = {}
            for rejected_item in rejected:
                canonical = canonicalize_url(str(rejected_item.get("url", "")))
                rejection_queues.setdefault(canonical, []).append(
                    str(rejected_item.get("reason", ""))
                )
            for item in discovered:
                canonical = canonicalize_url(item.url)
                if accepted_counts.get(canonical, 0) > 0:
                    accepted_counts[canonical] -= 1
                    status, reason = "accepted_for_extraction", ""
                elif rejection_queues.get(canonical):
                    status = "prefilter_rejected"
                    reason = rejection_queues[canonical].pop(0)
                else:
                    status, reason = "not_selected_capacity", "max_urls_cap"
                state.discoveries.append(
                    CapturedDiscovery(
                        item=item,
                        prefilter_status=status,
                        prefilter_reject_reason=reason,
                    )
                )
        return accepted, rejected

    def wrapped_upsert(
        self: Any,
        run_id: str,
        pairs: Iterable[tuple[DiscoveredURL, ExtractedArticle]],
    ) -> int:
        pair_list = list(pairs)
        written = original_upsert(self, run_id, pair_list)
        state = _CAPTURE_STATE.get()
        if state is not None:
            try:
                _append_snapshot_rows(
                    self, run_id=run_id, pair_list=pair_list, state=state
                )
            except Exception as exc:
                state.snapshot_error = f"{type(exc).__name__}: {exc}"[:1000]
                LOGGER.exception("Failed to append collector discovery snapshot")
        return written

    pipeline_module.filter_discovered = wrapped_filter
    store_cls.upsert_articles = wrapped_upsert
    _INSTALLED = True
