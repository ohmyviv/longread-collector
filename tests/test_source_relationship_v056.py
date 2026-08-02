from __future__ import annotations

from longread_collector.source_relationship_v056 import detect_wire_evidence


def test_thomson_reuters_foundation_design_credit_is_not_wire_evidence() -> None:
    result = detect_wire_evidence(
        url="https://mediafreedomcoalition.org/reports/media-freedom.pdf",
        markdown=(
            "This independent report was commissioned by the MFC Secretariat. "
            "Designed by the Thomson Reuters Foundation. The views are the author's."
        ),
    )
    assert result.strong is False
    assert result.service == "Reuters"
    assert result.negative_context is True
    assert result.evidence_type == "negative_context_only"


def test_reuters_reference_or_body_mention_is_not_wire_evidence() -> None:
    result = detect_wire_evidence(
        url="https://www.bellingcat.com/news/2026/08/01/investigation/",
        markdown=(
            "Our investigation used satellite images and company records. "
            "Reuters reported a related allegation in 2024. References follow."
        ),
    )
    assert result.strong is False
    assert result.service == "Reuters"


def test_structured_reuters_author_is_strong_evidence() -> None:
    result = detect_wire_evidence(
        url="https://example.com/world/reuters-story.html",
        author="Reuters",
        markdown="A complete syndicated report.",
    )
    assert result.strong is True
    assert result.service == "Reuters"
    assert result.evidence_type == "structured_author"


def test_reuters_dateline_is_strong_evidence() -> None:
    result = detect_wire_evidence(
        url="https://example.com/world/story.html",
        markdown="LONDON (Reuters) - Governments agreed on a new framework on Monday.",
    )
    assert result.strong is True
    assert result.service == "Reuters"
    assert result.evidence_type == "wire_dateline"


def test_associated_press_author_is_strong_evidence() -> None:
    result = detect_wire_evidence(
        url="https://example.com/politics/story.html",
        author="The Associated Press",
    )
    assert result.strong is True
    assert result.service == "AP"
    assert result.evidence_type == "structured_author"


def test_direct_wire_domains_are_original_publishers() -> None:
    reuters = detect_wire_evidence(url="https://www.reuters.com/world/story-2026-08-01/")
    ap = detect_wire_evidence(url="https://apnews.com/article/abcdef")
    assert reuters.strong is True and reuters.direct_publisher is True
    assert ap.strong is True and ap.direct_publisher is True
