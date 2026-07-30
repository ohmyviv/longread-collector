from longread_collector.extraction import (
    _author_from_content,
    _date_from_url_or_content,
    _verification,
)
from longread_collector.models import DiscoveredURL
from longread_collector.quality import (
    content_quality_reason,
    discovery_reject_reason,
    filter_discovered,
)


def test_discovery_filter_rejects_social_homepage_and_job() -> None:
    items = [
        DiscoveredURL(url="https://facebook.com/example/posts/1", title="Post"),
        DiscoveredURL(url="https://example.com/", title="Example"),
        DiscoveredURL(url="https://jobs.example.com/job/123", title="Research Writer"),
        DiscoveredURL(
            url="https://example.com/analysis/deep-story",
            title="Deep story",
        ),
    ]
    accepted, rejected = filter_discovered(items, max_urls=10)
    assert [item.url for item in accepted] == [
        "https://example.com/analysis/deep-story"
    ]
    assert {item["reason"] for item in rejected} >= {
        "social_not_standalone",
        "homepage",
        "job_page",
    }


def test_discovery_filter_preserves_social_source_lead() -> None:
    item = DiscoveredURL(
        url="https://instagram.com/p/example",
        title="A new investigation",
        description=(
            "A new investigation from ProPublica and Drilled examines the "
            "infrastructure behind the project."
        ),
    )
    accepted, rejected = filter_discovered([item], max_urls=10)
    assert accepted == [item]
    assert rejected == []


def test_content_quality_rejects_captcha_even_when_long() -> None:
    content = (
        "# Are you a robot?\nPlease confirm you are a human by completing "
        "the captcha challenge.\n" + ("navigation " * 1000)
    )
    valid, reason, _ = content_quality_reason(
        "https://example.com/articles/123",
        "Just a moment...",
        content,
    )
    assert not valid
    assert reason in {"blocked_or_auth", "blocked_login_or_captcha_page"}


def test_content_quality_accepts_article_prose() -> None:
    paragraph = (
        "This is a substantive paragraph explaining a complex public-policy "
        "issue with evidence and context. " * 3
    )
    content = "# A serious investigation\n\n" + "\n\n".join([paragraph] * 5)
    valid, reason, prose_chars = content_quality_reason(
        "https://example.com/2026/07/25/serious-investigation",
        "A serious investigation",
        content,
    )
    assert valid
    assert reason == "valid_article_body"
    assert prose_chars > 1200


def test_metadata_fallbacks_extract_author_and_date() -> None:
    content = "# Story\n\nBy Jane Doe\n\nPublished July 25, 2026\n\nBody"
    assert _author_from_content(content) == "Jane Doe"
    assert (
        _date_from_url_or_content("https://example.com/story", content)
        == "July 25, 2026"
    )
    assert (
        _date_from_url_or_content("https://example.com/2026/07/26/story", "")
        == "2026-07-26"
    )


def test_b_level_allows_valid_full_body_when_author_missing() -> None:
    level, reason = _verification(
        title="A long investigation",
        author="",
        date="2026-07-25",
        content="x" * 5000,
        description="summary",
        min_chars=1200,
        valid_body=True,
        quality_reason="valid_article_body",
    )
    assert level == "B"
    assert reason == "full_body_date_verified_author_missing"


def test_query_level_reject_reason_is_empty_for_article_path() -> None:
    assert (
        discovery_reject_reason(
            "https://example.com/features/a-story",
            "A Story",
        )
        == ""
    )
