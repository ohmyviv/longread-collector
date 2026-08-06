from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.classification_v056l import (
    classify_candidate_v056l,
    sanitize_author_v056l,
)
from longread_collector.historical_dedupe_v056l import (
    apply_historical_primary_document_dedupe,
)
from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.post_extraction_gates_v056l import (
    apply_post_extraction_gates_v056l,
)
from longread_collector.publication_date_v056l import (
    extract_body_publication_date_v056l,
)

BJ = ZoneInfo("Asia/Shanghai")
COOKIE_AUTHOR = (
    "using this website, you agree to our use of cookies. This use includes "
    "personalization of content and ads, and traffic analysis"
)


def _body(seed: str, repeat: int = 50) -> str:
    return "\n\n".join(
        f"{seed} paragraph {i}. According to the report, researchers and officials "
        "said the evidence changes the policy debate. The analysis compares data, "
        "history, implementation constraints and competing explanations in detail."
        for i in range(repeat)
    )


def test_cookie_author_is_removed() -> None:
    assert sanitize_author_v056l(COOKIE_AUTHOR) == ""
    assert sanitize_author_v056l("Stephen M. Walt") == "Stephen M. Walt"


def test_complete_editorial_body_survives_corrupted_author() -> None:
    markdown = (
        "# Why the United States Keeps Losing Wars\n\n"
        "By Stephen M. Walt\n\n"
        "August 5, 2026\n\n"
        "## The strategic pattern\n\n"
        + _body("Foreign-policy analysis", 55)
    )
    result = classify_candidate_v056l(
        url="https://foreignpolicy.com/2026/08/05/example-analysis/",
        title="Why the United States Keeps Losing Wars",
        author=COOKIE_AUTHOR,
        markdown=markdown,
        verification_level="C",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert "metadata_recovery_v056l" in result.reason or "author_boilerplate" in result.reason


def test_live_election_results_are_rejected() -> None:
    markdown = (
        "# Michigan Primary-Election Live Results\n\n"
        "Live results and an interactive map. Precincts reporting: 82%. "
        "Estimated votes and race calls update throughout the night."
    )
    result = classify_candidate_v056l(
        url="https://www.newyorker.com/news/election-2026/michigan-primary-live-results",
        title="Michigan Primary-Election Live Results",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "live_election_results"


def test_course_promotion_is_rejected() -> None:
    markdown = (
        "# IEEE Course Teaches How to Use AI to Modernize Power Grids\n\n"
        "Participants will learn through six modules and a detailed curriculum. "
        "Enroll now to earn a continuing education certificate and CEUs."
    )
    result = classify_candidate_v056l(
        url="https://spectrum.ieee.org/ai-power-grid-course",
        title="IEEE Course Teaches How to Use AI to Modernize Power Grids",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "course_promotion"


def test_gated_report_landing_is_rejected() -> None:
    markdown = (
        "# The 2026 R&D Benchmark Report: Waste, AI and the Race to Market\n\n"
        "Download the full report to see the benchmark findings. Complete the form "
        "with your first name, last name, business email and company name. "
        "Submit the form to access the report."
    )
    result = classify_candidate_v056l(
        url="https://engineeringcontent.wiley.com/benchmark-report",
        title="The 2026 R&D Benchmark Report: Waste, AI and the Race to Market",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "gated_marketing_report"


def test_vendor_case_study_is_rejected() -> None:
    markdown = (
        "# Identifying the Root Cause of Electronics Failures With Simulation Apps\n\n"
        "Customer story and case study: engineers used a multiphysics software "
        "platform and simulation app to solve the problem. Learn more about the "
        "product suite and request a demo. This article originally appeared on "
        "the software vendor's website."
    )
    result = classify_candidate_v056l(
        url="https://spectrum.ieee.org/electronics-failure-simulation-apps",
        title="Identifying the Root Cause of Electronics Failures With Simulation Apps",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.content_type == "vendor_case_study"


def test_byline_date_is_parsed() -> None:
    markdown = (
        "# How a Solar Revolution in Farming Is Depleting World’s Groundwater\n\n"
        "[Fred Pearce](https://example.com/authors/fred-pearce)•February 27,2024\n\n"
        + _body("Groundwater reporting", 30)
    )
    evidence = extract_body_publication_date_v056l(markdown)
    assert evidence is not None
    assert evidence.value.date().isoformat() == "2024-02-27"
    assert evidence.source == "body_header_byline_date"


def test_fourteen_day_byline_date_is_inclusive() -> None:
    markdown = (
        "# After Decades of Drought, Water Is Rising in the African Sahel\n\n"
        "[Fred Pearce](https://example.com/authors/fred-pearce)•July 23,2026\n\n"
        + _body("Sahel environment feature", 45)
    )
    discovered = DiscoveredURL(
        url="https://e360.yale.edu/features/sahel-water",
        title="After Decades of Drought, Water Is Rising in the African Sahel",
    )
    article = ExtractedArticle(
        article_id="sahel-14-day-boundary",
        url=discovered.url,
        url_canonical=discovered.url,
        domain="e360.yale.edu",
        title=discovered.title,
        extraction_status="success",
        verification_level="B",
        content_markdown=markdown,
        content_chars=len(markdown),
        candidate_disposition="formal_candidate",
        classification_version="collector-v0.5.6l",
        classification_reason="reported_environment_feature",
        eligible_for_editor=True,
    )
    result = apply_post_extraction_gates_v056l(
        discovered,
        article,
        now=datetime(2026, 8, 6, 5, 0, tzinfo=BJ),
        body_date_extractor=extract_body_publication_date_v056l,
    )
    assert result["freshness_rejected"] is False
    assert article.candidate_disposition == "formal_candidate"
    assert article.published_at.startswith("2026-07-23")


def _document(article_id: str, url: str, relationship: str = "original") -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url=url,
        url_canonical=url,
        domain=url.split("/")[2],
        title="关于所谓产能过剩问题的中方立场中华人民共和国驻南非共和国大使馆",
        page_type="document",
        content_type="government_primary_document",
        candidate_disposition="special_candidate",
        special_candidate_type="primary_document",
        source_relationship=relationship,
        classification_version="collector-v0.5.6l",
        eligible_for_editor=False,
    )


def test_embassy_copy_is_rejected_against_central_original() -> None:
    article = _document(
        "south-africa-copy",
        "https://za.china-embassy.gov.cn/statement.htm",
    )
    historical = [{
        "article_id": "mofcom-original",
        "title": "关于所谓“产能过剩”问题的中方立场",
        "url_canonical": "https://www.mofcom.gov.cn/article/statement.htm",
        "page_type": "document",
        "content_type": "government_primary_document",
        "special_candidate_type": "primary_document",
        "source_relationship": "original",
        "canonical_source": "商务部",
        "first_seen_at_bj": "2026-07-28 10:00:00",
    }]
    changed = apply_historical_primary_document_dedupe(
        [(DiscoveredURL(url=article.url), article)],
        historical,
    )
    assert changed == 1
    assert article.candidate_disposition == "reject"
    assert article.duplicate_type == "same_content_cross_host"
    assert article.original_url.startswith("https://www.mofcom.gov.cn/")


def test_central_original_is_not_rejected_by_historical_embassy_copy() -> None:
    article = _document(
        "mofcom-new-original",
        "https://www.mofcom.gov.cn/article/statement.htm",
    )
    historical = [{
        "article_id": "embassy-copy",
        "title": "关于所谓“产能过剩”问题的中方立场中华人民共和国驻约旦哈希姆王国大使馆",
        "url_canonical": "https://jo.china-embassy.gov.cn/statement.htm",
        "page_type": "document",
        "content_type": "government_primary_document",
        "special_candidate_type": "primary_document",
        "source_relationship": "secondary_republish",
        "canonical_source": "中国驻约旦使馆",
        "first_seen_at_bj": "2026-07-27 10:00:00",
    }]
    changed = apply_historical_primary_document_dedupe(
        [(DiscoveredURL(url=article.url), article)],
        historical,
    )
    assert changed == 0
    assert article.candidate_disposition == "special_candidate"
