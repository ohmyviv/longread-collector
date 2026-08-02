from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.freshness_v056 import (
    evaluate_freshness,
    resolve_publication_date,
)
from longread_collector.models import DiscoveredURL
from longread_collector.prefilter_v056c import filter_discovered

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=BJ)


def item(
    url: str,
    title: str,
    *,
    published_at: str = "",
    description: str = "",
    native: bool = False,
    metadata: dict | None = None,
) -> DiscoveredURL:
    values = dict(metadata or {})
    if native:
        values.update(
            {
                "purpose": "native_source_scan",
                "source_id": "source-a",
                "native_method": "rss",
            }
        )
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at=published_at,
        discovery_method="rss" if native else "firecrawl_search",
        metadata=values,
    )


def test_rss_date_is_high_confidence_and_capture_time_is_not_fallback() -> None:
    candidate = item(
        "https://example.com/2026/08/01/investigation.html",
        "A detailed investigation into public procurement",
        published_at="Sat, 01 Aug 2026 08:00:00 +0800",
        native=True,
        metadata={
            "captured_at_bj": "2026-08-02 11:00:00",
            "first_seen_at_bj": "2026-08-02 11:00:00",
        },
    )
    result = resolve_publication_date(candidate)
    assert result["published_at_source"] == "rss_feed"
    assert result["published_at_confidence"] == "high"
    assert result["published_at_resolved"].startswith("2026-08-01")
    assert sorted(result["ignored_non_publication_fields"]) == [
        "captured_at_bj",
        "first_seen_at_bj",
    ]


def test_capture_time_alone_leaves_publication_unknown() -> None:
    candidate = item(
        "https://example.com/story/unknown-date.html",
        "A reported feature without a publication date",
        metadata={"captured_at_bj": "2026-08-02 11:00:00"},
    )
    result = resolve_publication_date(candidate)
    assert result["published_at_resolved"] == ""
    assert result["published_at_source"] == "unknown"
    assert result["freshness_unknown"] is True


def test_conflicting_date_evidence_is_auditable() -> None:
    candidate = item(
        "https://example.com/articles/conflict.html",
        "A current policy analysis",
        published_at="2026-08-01",
        native=True,
        metadata={"structured": {"datePublished": "2026-07-20"}},
    )
    result = resolve_publication_date(candidate)
    assert result["published_at_source"] == "rss_feed"
    assert "structured_date_published=2026-07-20" in result["date_conflict_reason"]


def test_seven_day_article_is_allowed() -> None:
    candidate = item(
        "https://example.com/2026/07/28/feature.html",
        "A reported feature on climate adaptation",
        published_at="2026-07-28",
        native=True,
    )
    decision = evaluate_freshness(candidate, now=NOW)
    assert decision.allowed is True
    assert decision.track == "ordinary_7d"
    assert decision.age_days == 5


def test_eight_to_fourteen_days_requires_explicit_depth_signal() -> None:
    deep = item(
        "https://example.com/2026/07/22/investigation.html",
        "In-depth investigation into industrial pollution",
        published_at="2026-07-22",
        native=True,
    )
    ordinary = item(
        "https://other.example.com/2026/07/22/news.html",
        "Company reports quarterly results",
        published_at="2026-07-22",
        native=True,
    )
    deep_decision = evaluate_freshness(deep, now=NOW)
    ordinary_decision = evaluate_freshness(ordinary, now=NOW)
    assert deep_decision.allowed is True
    assert deep_decision.track == "deep_read_8_14d"
    assert deep_decision.exception_reason == "explicit_depth_signal"
    assert ordinary_decision.allowed is False
    assert ordinary_decision.reject_reason == "stale_8_14d_without_depth"


def test_old_ordinary_article_is_rejected() -> None:
    candidate = item(
        "https://example.com/2019/03/04/commentary.html",
        "An old commentary on economic reform",
        published_at="2019-03-04",
        native=True,
    )
    decision = evaluate_freshness(candidate, now=NOW)
    assert decision.allowed is False
    assert decision.reject_reason == "stale_article_over_14d"


def test_old_academic_or_primary_document_uses_special_track() -> None:
    candidate = item(
        "https://academic.oup.com/journal/article/42/1/100/123456",
        "A systematic review of environmental policy",
        published_at="2024-05-01",
    )
    decision = evaluate_freshness(candidate, now=NOW)
    assert decision.allowed is True
    assert decision.track == "special_document"


def test_unknown_open_page_requires_strong_article_evidence() -> None:
    weak = item(
        "https://example.com/information",
        "General information",
    )
    strong = item(
        "https://example.org/articles/investigation-into-water-markets.html",
        "Investigation into the hidden market for water rights",
        description="A long reported feature based on interviews and public records.",
    )
    weak_decision = evaluate_freshness(weak, now=NOW)
    strong_decision = evaluate_freshness(strong, now=NOW)
    assert weak_decision.allowed is False
    assert weak_decision.reject_reason == "freshness_unknown_weak_open_evidence"
    assert strong_decision.allowed is True
    assert strong_decision.unknown is True
    assert strong_decision.score_penalty < 0


def test_prefilter_rejects_stale_article_but_keeps_old_special_document() -> None:
    stale = item(
        "https://example.com/2018/04/01/news.html",
        "A historical news report",
        published_at="2018-04-01",
        native=True,
    )
    special = item(
        "https://government.example.gov/reports/2024-guidance.pdf",
        "Artificial intelligence and privacy guidance",
        published_at="2024-01-01",
        native=True,
    )
    accepted, rejected = filter_discovered([stale, special], max_urls=2)
    assert [entry.url for entry in accepted] == [special.url]
    assert rejected == [{"url": stale.url, "reason": "stale_article_over_14d"}]
    assert stale.metadata["selection"]["published_at_source"] == "rss_feed"
    assert special.metadata["selection"]["freshness_track"] == "special_document"
