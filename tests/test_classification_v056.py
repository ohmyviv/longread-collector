from __future__ import annotations

from longread_collector.classification_v056 import classify_candidate_v056


def classify(
    url: str,
    title: str,
    *,
    description: str = "",
    author: str = "",
    markdown: str = "",
    verification_level: str = "A",
    content_chars: int = 5000,
):
    return classify_candidate_v056(
        url=url,
        title=title,
        description=description,
        author=author,
        markdown=markdown,
        published_at="2026-08-01",
        verification_level=verification_level,
        content_chars=content_chars,
    )


def test_media_freedom_report_is_special_not_reuters_source_chase() -> None:
    result = classify(
        "https://mediafreedomcoalition.org/wp-content/uploads/2024/12/MFC-Final-Report.pdf",
        "Why Media Freedom Matters",
        markdown=(
            "Independent research report commissioned by the MFC Secretariat. "
            "Designed by the Thomson Reuters Foundation. The views are the author's."
        ),
    )
    assert result.candidate_disposition == "special_candidate"
    assert result.special_candidate_type == "institutional_research_report"
    assert result.source_relationship == "original"
    assert result.original_publisher == ""


def test_bellingcat_article_mentioning_reuters_remains_original() -> None:
    result = classify(
        "https://www.bellingcat.com/news/2026/08/01/cartel-investigation/",
        "Welcome to Dubai: Cartel Visas Revealed",
        markdown=(
            "This investigation is based on leaked visa records and interviews. "
            "Reuters reported a related case in 2024. " + "evidence " * 700
        ),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "original"
    assert result.original_publisher == ""


def test_true_reuters_republish_requires_original() -> None:
    result = classify(
        "https://example.com/world/syndicated-story.html",
        "Governments agree on a new climate framework",
        author="Reuters",
        markdown="A complete syndicated report. " + "reporting " * 400,
    )
    assert result.candidate_disposition == "original_source_required"
    assert result.source_relationship == "wire_republish"
    assert result.original_publisher == "Reuters"
    assert result.wire_service == "Reuters"
    assert result.reason == "reuters_strong_wire_structured_author_v056"


def test_direct_reuters_article_is_original_formal_candidate() -> None:
    result = classify(
        "https://www.reuters.com/world/europe/story-2026-08-01/",
        "Governments agree on a new climate framework",
        author="Reuters",
        markdown="Original Reuters reporting. " + "reporting " * 400,
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.source_relationship == "original"
    assert result.original_publisher == "Reuters"


def test_true_ap_republish_requires_original() -> None:
    result = classify(
        "https://example.com/politics/ap-story.html",
        "Court ruling reshapes voting access",
        author="The Associated Press",
        markdown="A complete syndicated report. " + "reporting " * 400,
    )
    assert result.candidate_disposition == "original_source_required"
    assert result.original_publisher == "Associated Press"
    assert result.wire_service == "AP"


def test_new_yorker_feature_is_not_rejected_for_missing_depth_words() -> None:
    result = classify(
        "https://www.newyorker.com/news/the-lede/why-is-europe-burning",
        "Why Is Europe Burning?",
        markdown="A reported magazine feature. " + "paragraph " * 500,
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.reason == "registered_high_quality_article_structure_v056"


def test_yale_e360_feature_is_not_rejected() -> None:
    result = classify(
        "https://e360.yale.edu/features/india-grasslands-conservation",
        "‘Wastelands’ No More: India Charts a Future for Its Grasslands",
        markdown="A reported environmental feature. " + "paragraph " * 500,
    )
    assert result.candidate_disposition == "formal_candidate"


def test_academic_paper_uses_stable_special_type() -> None:
    result = classify(
        "https://www.ncbi.nlm.nih.gov/articles/PMC1234567/",
        "Renewable energy as a solution to climate change",
        markdown="Abstract Methods Results References " + "study " * 300,
    )
    assert result.candidate_disposition == "special_candidate"
    assert result.page_type == "academic_paper"
    assert result.special_candidate_type == "academic_paper"


def test_government_privacy_guidance_is_special() -> None:
    result = classify(
        "https://privacy.gov.example/guidance/artificial-intelligence-and-privacy.pdf",
        "Artificial Intelligence and Privacy – Issues and Challenges",
        markdown="Official regulatory guidance for public agencies.",
    )
    assert result.candidate_disposition == "special_candidate"
    assert result.special_candidate_type == "regulatory_guidance"


def test_oecd_report_chapter_is_special() -> None:
    result = classify(
        "https://www.oecd.org/reports/digital-government-journey-2026/chapter-4.html",
        "How artificial intelligence is accelerating the digital government journey",
        markdown="Chapter 4 of the OECD analytical report. " + "analysis " * 300,
    )
    assert result.candidate_disposition == "special_candidate"
    assert result.special_candidate_type == "report_chapter"


def test_university_paper_summary_requires_original_paper() -> None:
    result = classify(
        "https://research.university.edu/news/city-bubbles-study.html",
        "研究揭示中国城市外国旅居者的社会空间表征",
        markdown=(
            "该研究成果发表于 Journal of Urban Studies，论文 DOI: "
            "10.1234/example.2026.001。页面介绍了论文主要结论。"
        ),
    )
    assert result.candidate_disposition == "original_source_required"
    assert result.page_type == "academic_summary"
    assert result.source_relationship == "secondary_summary"
    assert result.reason == "academic_summary_requires_original_v056"


def test_newsletter_still_rejected() -> None:
    result = classify(
        "https://www.theatlantic.com/newsletters/archive/2026/08/natures-stories/",
        "Nature’s Most Extraordinary Stories Newsletter",
        content_chars=3000,
    )
    assert result.candidate_disposition == "reject"
