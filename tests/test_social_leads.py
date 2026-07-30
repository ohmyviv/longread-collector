from __future__ import annotations

from longread_collector.classification import classify_candidate


def test_media_site_social_post_becomes_article_lead() -> None:
    result = classify_candidate(
        url="https://facebook.com/StateCollegeCom/posts/example",
        title="StateCollege.com",
        description=(
            "Environmental groups say the data-center bill is not substantive, "
            "and the newsroom has published a detailed account of the dispute."
        ),
    )
    assert result.page_role == "discovery_lead"
    assert result.candidate_disposition == "original_source_required"
    assert result.content_type == "reported_article"
    assert result.source_action == "find_original_article"


def test_party_policy_social_post_becomes_primary_document_lead() -> None:
    result = classify_candidate(
        url="https://facebook.com/nzgreenparty/posts/example",
        title="The government has no plan for deciding which data centres are in the public interest",
        description=(
            "The party proposes rules for where data centres should go, what "
            "resource-use conditions should apply, and who should pay."
        ),
    )
    assert result.page_role == "discovery_lead"
    assert result.candidate_disposition == "original_source_required"
    assert result.content_type == "primary_statement"
    assert result.source_action == "find_primary_document"


def test_short_news_agency_social_post_is_not_promoted_to_lead() -> None:
    result = classify_candidate(
        url="https://facebook.com/kenyanewsagency/posts/example",
        title="Kenya News Agency - KNA",
        description=(
            "AI is a useful support tool for traditional media, but human "
            "journalists remain essential."
        ),
    )
    assert result.page_role == "non_content"
    assert result.candidate_disposition == "reject"


def test_official_political_statement_without_document_signal_is_rejected() -> None:
    result = classify_candidate(
        url="https://facebook.com/president.official/posts/example",
        title="Official statement on security",
        description=(
            "The president issued a statement about current military losses "
            "and future mobilization."
        ),
    )
    assert result.page_role == "non_content"
    assert result.candidate_disposition == "reject"
