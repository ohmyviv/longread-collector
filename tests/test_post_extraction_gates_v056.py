from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.post_extraction_gates_v056 import (
    apply_post_extraction_gates,
)

BJ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=BJ)


def discovered(
    url: str,
    title: str,
    *,
    published_at: str = "",
    native: bool = True,
) -> DiscoveredURL:
    metadata = {}
    if native:
        metadata = {
            "purpose": "native_source_scan",
            "source_id": "registered",
            "source_name": "Registered",
            "native_method": "section_scan",
        }
    return DiscoveredURL(
        url=url,
        title=title,
        published_at=published_at,
        discovery_method="section_scan" if native else "firecrawl_search",
        metadata=metadata,
    )


def article(
    item: DiscoveredURL,
    *,
    title: str | None = None,
    published_at: str = "",
    disposition: str = "formal_candidate",
    description: str = "",
) -> ExtractedArticle:
    return ExtractedArticle(
        article_id="a1",
        url=item.url,
        url_canonical=item.url,
        domain="example.com",
        title=title or item.title,
        description=description,
        published_at=published_at,
        extraction_status="success",
        extractor_used="jina",
        candidate_disposition=disposition,
        eligible_for_editor=disposition != "reject",
        classification_version="test-v056",
        classification_reason="initial-classification",
    )


def test_body_date_rejects_old_ordinary_article() -> None:
    item = discovered(
        "https://example.com/articles/old-report.html",
        "An ordinary news report",
    )
    extracted = article(item, published_at="2019-03-04")
    result = apply_post_extraction_gates(item, extracted, now=NOW)
    assert result["freshness_rejected"] is True
    assert extracted.candidate_disposition == "reject"
    assert extracted.reject_reason == "stale_article_over_14d"
    assert extracted.eligible_for_editor is False
    assert extracted.metadata["freshness"]["published_at_resolved"].startswith(
        "2019-03-04"
    )


def test_body_title_rejects_buying_guide() -> None:
    item = discovered(
        "https://www.wired.com/gallery/best-organic-mattresses/",
        "Page title unavailable",
        native=False,
    )
    extracted = article(
        item,
        title="The Best Organic Mattresses We've Tested",
        published_at="2026-08-01",
        description="We may earn a commission from links on this page.",
    )
    result = apply_post_extraction_gates(item, extracted, now=NOW)
    assert result["page_rejected"] is True
    assert extracted.reject_reason == "commerce_or_buying_guide"
    assert extracted.page_type == "commerce_or_buying_guide"


def test_recent_new_yorker_feature_remains_formal_candidate() -> None:
    item = discovered(
        "https://www.newyorker.com/magazine/2026/08/03/a-feature",
        "How Artificial Intelligence Changed the Way We Think",
        published_at="2026-08-01",
    )
    extracted = article(item, published_at="2026-08-01")
    result = apply_post_extraction_gates(item, extracted, now=NOW)
    assert result["page_rejected"] is False
    assert result["freshness_rejected"] is False
    assert extracted.candidate_disposition == "formal_candidate"
    assert extracted.eligible_for_editor is True


def test_old_academic_paper_remains_special_candidate() -> None:
    item = discovered(
        "https://academic.oup.com/journal/article/42/1/100/123456",
        "A systematic review of environmental policy",
        published_at="2024-05-01",
        native=False,
    )
    extracted = article(
        item,
        published_at="2024-05-01",
        disposition="special_candidate",
    )
    result = apply_post_extraction_gates(item, extracted, now=NOW)
    assert result["freshness_rejected"] is False
    assert extracted.candidate_disposition == "special_candidate"


def test_failed_extraction_is_not_reclassified_by_post_gate() -> None:
    item = discovered(
        "https://example.com/articles/failure.html",
        "A failed extraction",
    )
    extracted = article(item)
    extracted.extraction_status = "failed"
    extracted.candidate_disposition = "reject"
    extracted.eligible_for_editor = False
    extracted.reject_reason = "reader_failed"
    result = apply_post_extraction_gates(item, extracted, now=NOW)
    assert result["skipped_for_failed_extraction"] is True
    assert extracted.reject_reason == "reader_failed"
