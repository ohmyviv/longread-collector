from __future__ import annotations

from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.sheets import (
    ARTICLE_HEADERS,
    GoogleSheetStore,
    _is_retryable_sheet_error,
    _retry_sheet_call,
)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class FakeSheetError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"sheet error {status_code}")
        self.response = FakeResponse(status_code)


class FakeArticleWorksheet:
    def __init__(self, rows: list[list[str]]) -> None:
        self.rows = rows
        self.get_all_values_calls = 0
        self.row_values_calls = 0
        self.append_rows_calls = 0
        self.batch_update_calls = 0
        self.batch_payload = None

    def get_all_values(self):
        self.get_all_values_calls += 1
        return self.rows

    def row_values(self, row_no: int):
        self.row_values_calls += 1
        raise AssertionError("N+1 row_values must not be used")

    def append_rows(self, rows, **kwargs):
        self.append_rows_calls += 1
        self.rows.extend(rows)

    def batch_update(self, batch, **kwargs):
        self.batch_update_calls += 1
        self.batch_payload = batch


class FakeBook:
    def __init__(self, article_ws: FakeArticleWorksheet) -> None:
        self.article_ws = article_ws

    def worksheet(self, title: str):
        assert title == "article_cache"
        return self.article_ws


def _store(article_ws: FakeArticleWorksheet) -> GoogleSheetStore:
    store = object.__new__(GoogleSheetStore)
    store.book = FakeBook(article_ws)
    store.settings = SimpleNamespace(cache_hours=168)
    store.tz = ZoneInfo("Asia/Shanghai")
    return store


def _existing_row(article_id: str, source: str = "EEO") -> list[str]:
    row = [""] * len(ARTICLE_HEADERS)
    row[0] = article_id
    row[1] = "2026-08-26 10:00:00"
    row[12] = source
    row[27] = "2026-08-20 09:00:00"
    row[30] = "old-selected-run"
    row[31] = "kept"
    row[32] = "historical note"
    return row


def _article(article_id: str, url: str, source: str = "EEO") -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url=url,
        url_canonical=url,
        domain="example.com",
        title="A sufficiently descriptive long-form article title",
        canonical_source=source,
        hosting_source=source,
        extraction_status="success",
        verification_level="A",
        content_markdown="body " * 1000,
        content_chars=5000,
        classification_version="test",
        candidate_disposition="formal_candidate",
        eligible_for_editor=True,
    )


def test_retry_only_transient_429_503_and_uses_bounded_backoff() -> None:
    assert _is_retryable_sheet_error(FakeSheetError(429))
    assert _is_retryable_sheet_error(FakeSheetError(503))
    assert not _is_retryable_sheet_error(FakeSheetError(400))

    calls = 0
    sleeps: list[float] = []

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise FakeSheetError(429)
        return "ok"

    assert _retry_sheet_call(operation, delays=(0.1, 0.2), sleep_fn=sleeps.append) == "ok"
    assert calls == 3
    assert sleeps == [0.1, 0.2]


def test_nonretryable_error_fails_immediately() -> None:
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        raise FakeSheetError(400)

    with pytest.raises(FakeSheetError):
        _retry_sheet_call(operation, delays=(0.1, 0.2), sleep_fn=lambda _: None)
    assert calls == 1


def test_upsert_existing_articles_uses_one_cache_read_and_one_batch_update() -> None:
    ws = FakeArticleWorksheet(
        [ARTICLE_HEADERS, _existing_row("a1"), _existing_row("a2")]
    )
    store = _store(ws)
    pairs = [
        (
            DiscoveredURL(url="https://example.com/a1", rank=1),
            _article("a1", "https://example.com/a1"),
        ),
        (
            DiscoveredURL(url="https://example.com/a2", rank=2),
            _article("a2", "https://example.com/a2"),
        ),
    ]

    assert store.upsert_articles("RUN-1", pairs) == 2
    assert ws.get_all_values_calls == 1
    assert ws.row_values_calls == 0
    assert ws.append_rows_calls == 0
    assert ws.batch_update_calls == 1
    assert len(ws.batch_payload) == 2
    assert [item["range"] for item in ws.batch_payload] == ["A2:AV2", "A3:AV3"]

    # Historical fields that the old row_values path preserved remain intact.
    first_update = ws.batch_payload[0]["values"][0]
    assert first_update[27] == "2026-08-20 09:00:00"
    assert first_update[30] == "old-selected-run"
    assert first_update[31] == "kept"
    assert first_update[32] == "historical note"


def test_upsert_mixed_new_and_existing_keeps_single_cache_read() -> None:
    ws = FakeArticleWorksheet([ARTICLE_HEADERS, _existing_row("a1")])
    store = _store(ws)
    pairs = [
        (
            DiscoveredURL(url="https://example.com/a1", rank=1),
            _article("a1", "https://example.com/a1"),
        ),
        (
            DiscoveredURL(url="https://example.com/new", rank=2),
            _article("new", "https://example.com/new", source="New Source"),
        ),
    ]

    assert store.upsert_articles("RUN-2", pairs) == 2
    assert ws.get_all_values_calls == 1
    assert ws.row_values_calls == 0
    assert ws.append_rows_calls == 1
    assert ws.batch_update_calls == 1
