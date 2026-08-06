from __future__ import annotations

from longread_collector.historical_dedupe_v056l import HistoricalPrimaryDocumentDedupe
from longread_collector.models import DiscoveredURL, ExtractedArticle


class _Worksheet:
    def __init__(self) -> None:
        self.calls = 0

    def get_all_records(self) -> list[dict[str, str]]:
        self.calls += 1
        return []


class _Book:
    def __init__(self, worksheet: _Worksheet) -> None:
        self._worksheet = worksheet

    def worksheet(self, name: str) -> _Worksheet:
        assert name == "article_cache"
        return self._worksheet


class _Store:
    def __init__(self, worksheet: _Worksheet) -> None:
        self.book = _Book(worksheet)


def _document(article_id: str, url: str, title: str) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url=url,
        url_canonical=url,
        domain=url.split("/")[2],
        title=title,
        page_type="document",
        content_type="government_primary_document",
        candidate_disposition="special_candidate",
        special_candidate_type="primary_document",
        source_relationship="original",
        classification_version="collector-v0.5.6l",
        eligible_for_editor=False,
    )


def test_history_is_loaded_once_and_run_rows_cover_reserve_batches() -> None:
    worksheet = _Worksheet()
    manager = HistoricalPrimaryDocumentDedupe(_Store(worksheet))

    original = _document(
        "mofcom-original",
        "https://www.mofcom.gov.cn/article/statement.htm",
        "关于所谓产能过剩问题的中方立场",
    )
    assert manager.apply([(DiscoveredURL(url=original.url), original)]) == 0

    carrier = _document(
        "embassy-carrier",
        "https://za.china-embassy.gov.cn/statement.htm",
        "关于所谓产能过剩问题的中方立场中华人民共和国驻南非共和国大使馆",
    )
    assert manager.apply([(DiscoveredURL(url=carrier.url), carrier)]) == 1

    assert worksheet.calls == 1
    assert manager.load_count == 1
    assert carrier.candidate_disposition == "reject"
    assert carrier.duplicate_type == "same_content_cross_host"
    assert carrier.original_url == original.url
