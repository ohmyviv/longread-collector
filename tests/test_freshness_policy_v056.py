from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.freshness_policy_v056 import (
    evaluate_freshness_policy,
    resolve_publication_evidence,
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
    native_method: str = "rss",
    metadata: dict | None = None,
) -> DiscoveredURL:
    values = dict(metadata or {})
    if native:
        values.update(
            {
                "purpose": "native_source_scan",
                "source_id": "registered-source",
                "source_name": "Registered Source",
                "native_method": native_method,
            }
        )
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at=published_at,
        discovery_method="rss" if native else "firecrawl_search",
        query_or_source="source:registered-source" if native else "open-query",
        metadata=values,
    )


def test_capture_time_never_becomes_publication_date() -> None:
    candidate = item(
        "https://example.com/articles/unknown-date.html",
        "Investigation into a public institution",
        native=True,
        metadata={
            "captured_at_bj": "2026-08-02 11:00:00",
            "first_seen_at_bj": "2026-08-02 11:00:00",
        },
    )
    result = resolve_publication_evidence(candidate)
    assert result["published_at_resolved"] == ""
    assert result["published_at_source"] == "unknown"
    assert sorted(result["ignored_non_publication_fields"]) == [
        "captured_at_bj",
        "first_seen_at_bj",
    ]


def test_generic_sitemap_lastmod_is_modified_not_published() -> None:
    candidate = item(
        "https://example.com/2019/03/04/commentary.html",
        "An old commentary",
        published_at="2026-08-02",
        native=True,
        native_method="sitemap",
    )
    result = resolve_publication_evidence(candidate)
    assert result["published_at_source"] == "url_path"
    assert result["published_at_resolved"].startswith("2019-03-04")
    assert result["date_modified_at"].startswith("2026-08-02")


def test_rss_date_remains_high_confidence() -> None:
    candidate = item(
        "https://example.com/articles/current.html",
        "A current investigation",
        published_at="Sat, 01 Aug 2026 08:00:00 +0800",
        native=True,
    )
    result = resolve_publication_evidence(candidate)
    assert result["published_at_source"] == "rss_feed"
    assert result["published_at_confidence"] == "high"


def test_freshness_tracks_are_conservative() -> None:
    recent = item(
        "https://example.com/2026/08/01/news/current.html",
        "Current reported article",
        published_at="2026-08-01",
        native=True,
    )
    five_day_native = item(
        "https://example.com/2026/07/28/news/report.html",
        "Reported article from a registered source",
        published_at="2026-07-28",
        native=True,
    )
    five_day_open = item(
        "https://open.example.org/2026/07/28/news/report.html",
        "Routine company update",
        published_at="2026-07-28",
    )
    ten_day_deep = item(
        "https://example.com/2026/07/23/investigation/report.html",
        "In-depth investigation into industrial pollution",
        published_at="2026-07-23",
        native=True,
    )
    old = item(
        "https://example.com/2015/04/01/news/report.html",
        "Old ordinary news report",
        published_at="2015-04-01",
        native=True,
    )

    assert evaluate_freshness_policy(recent, now=NOW).track == "ordinary_72h"
    assert evaluate_freshness_policy(five_day_native, now=NOW).allowed is True
    assert evaluate_freshness_policy(five_day_open, now=NOW).reject_reason == (
        "stale_4_7d_without_quality_signal"
    )
    assert evaluate_freshness_policy(ten_day_deep, now=NOW).track == (
        "deep_read_8_14d"
    )
    assert evaluate_freshness_policy(old, now=NOW).reject_reason == (
        "stale_article_over_14d"
    )


def test_unknown_date_is_deferred_for_native_and_structured_candidates() -> None:
    native_article = item(
        "https://example.com/articles/unknown-date.html",
        "A reported article without date metadata",
        native=True,
    )
    pre = evaluate_freshness_policy(native_article, phase="prefilter", now=NOW)
    post = evaluate_freshness_policy(native_article, phase="post_extraction", now=NOW)
    assert pre.allowed is True
    assert pre.track == "ordinary_unknown_native"
    assert pre.exception_reason == "registered_candidate_pending_body_date"
    assert post.allowed is True
    assert post.exception_reason == "registered_article_without_resolved_date"
    assert native_article.metadata["freshness"]["unknown_date_policy"] == (
        "defer_with_penalty"
    )

    open_structured = item(
        "https://economicsobservatory.com/how-geopolitical-risks-affect-economy",
        "How are geopolitical risks affecting the world economy?",
    )
    open_pre = evaluate_freshness_policy(
        open_structured, phase="prefilter", now=NOW
    )
    assert open_pre.allowed is True
    assert open_pre.track == "ordinary_unknown_open_structured"
    assert open_pre.score_penalty < pre.score_penalty

    unstructured = item(
        "https://example.com/about",
        "General information",
    )
    rejected = evaluate_freshness_policy(unstructured, phase="prefilter", now=NOW)
    assert rejected.allowed is False
    assert rejected.reject_reason == "freshness_unknown_insufficient_evidence"


def test_unknown_special_documents_cover_reports_chapters_and_academic_hosts() -> None:
    cfr = item(
        "https://www.cfr.org/task-force-report/us-economic-security",
        "U.S. Economic Security",
    )
    chapter = item(
        "https://www.nationalacademies.org/read/26403/chapter/3",
        "A report chapter on infectious disease monitoring",
    )
    iop = item(
        "https://iopscience.iop.org/article/10.1088/2634-4505/acbc95",
        "A journal article on environmental systems",
    )
    for candidate in (cfr, chapter, iop):
        decision = evaluate_freshness_policy(candidate, now=NOW)
        assert decision.allowed is True
        assert decision.track == "special_document"
        assert decision.unknown is True


def test_old_academic_and_government_documents_use_special_track() -> None:
    academic = item(
        "https://academic.oup.com/journal/article/42/1/100/123456",
        "A systematic review of environmental policy",
        published_at="2024-05-01",
    )
    guidance = item(
        "https://agency.gov.cn/guidance/privacy-guidance.pdf",
        "人工智能隐私保护指导文件",
        published_at="2024-01-01",
    )
    assert evaluate_freshness_policy(academic, now=NOW).track == "special_document"
    assert evaluate_freshness_policy(guidance, now=NOW).track == "special_document"


def test_prefilter_rejects_old_ordinary_but_keeps_old_special() -> None:
    old = item(
        "https://example.com/2018/04/01/news.html",
        "Historical routine news",
        published_at="2018-04-01",
        native=True,
    )
    special = item(
        "https://agency.gov.cn/research-report/2024-guidance.pdf",
        "Artificial intelligence privacy guidance document",
        published_at="2024-01-01",
        native=True,
    )
    accepted, rejected = filter_discovered([old, special], max_urls=2)
    assert [entry.url for entry in accepted] == [special.url]
    assert rejected == [{"url": old.url, "reason": "stale_article_over_14d"}]
    assert old.metadata["selection"]["selection_status"] == (
        "freshness_gate_reject"
    )
