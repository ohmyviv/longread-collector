from longread_collector.v06.contracts import (
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    PageSurface,
)
from longread_collector.v06.eligibility import (
    ELIGIBILITY_VERSION,
    EligibilityEvidence,
    EligibilityReason,
    StandardLongreadDisposition,
    evaluate_standard_longread_eligibility,
)
from longread_collector.v06.eligibility_replay import (
    EligibilityReplayRow,
    summarize_eligibility_replay,
)


def _article(
    *,
    item_id="case",
    surface=PageSurface.ARTICLE_PAGE,
    medium=ContentMedium.WRITTEN_ARTICLE,
    asset=AssetClass.MEDIA_ARTICLE,
):
    return CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="canonical-source-v0.6-pr7.3.9",
        run_id="COL-E0-OFFLINE",
        item_id=item_id,
        content_id=f"content-{item_id}",
        display_url=f"https://example.invalid/{item_id}",
        page_surface=surface,
        main_content_medium=medium,
        asset_class=asset,
    )


def test_standard_written_article_is_eligible():
    result = evaluate_standard_longread_eligibility(_article())
    assert result.stage_version == ELIGIBILITY_VERSION
    assert result.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD
    assert result.reasons == (EligibilityReason.STANDARD_WRITTEN_ARTICLE,)
    assert result.eligible_for_standard is True


def test_video_page_is_ineligible_but_embedded_video_is_not_inferred_here():
    video_page = evaluate_standard_longread_eligibility(
        _article(medium=ContentMedium.VIDEO_PAGE)
    )
    assert video_page.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
    assert EligibilityReason.VIDEO_MEDIUM in video_page.reasons

    # E0 consumes resolved medium facts; it never treats a written article as a
    # video page merely because some upstream extractor observed an embed.
    written = evaluate_standard_longread_eligibility(_article())
    assert written.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD


def test_academic_paper_routes_special_from_either_fact_axis():
    by_asset = evaluate_standard_longread_eligibility(
        _article(asset=AssetClass.ACADEMIC_PAPER)
    )
    by_medium = evaluate_standard_longread_eligibility(
        _article(medium=ContentMedium.ACADEMIC_PAPER)
    )
    for result in (by_asset, by_medium):
        assert result.disposition is StandardLongreadDisposition.ROUTE_SPECIAL
        assert EligibilityReason.ACADEMIC_ASSET in result.reasons
        assert result.eligible_for_standard is False


def test_primary_document_routes_special_instead_of_being_quality_penalized():
    result = evaluate_standard_longread_eligibility(
        _article(
            surface=PageSurface.DOCUMENT_PAGE,
            medium=ContentMedium.PRIMARY_DOCUMENT,
            asset=AssetClass.PRIMARY_DOCUMENT,
        )
    )
    assert result.disposition is StandardLongreadDisposition.ROUTE_SPECIAL
    assert EligibilityReason.PRIMARY_DOCUMENT_ASSET in result.reasons


def test_roundup_identity_is_an_explicit_product_fact():
    result = evaluate_standard_longread_eligibility(
        _article(), EligibilityEvidence(roundup_identity=True)
    )
    assert result.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
    assert result.reasons == (EligibilityReason.ROUNDUP_IDENTITY,)


def test_non_article_surfaces_are_not_standard_longreads():
    for surface in (
        PageSurface.EXTERNAL_LINK_STUB,
        PageSurface.LISTING,
        PageSurface.HOMEPAGE,
        PageSurface.LOGIN,
        PageSurface.CAPTCHA,
        PageSurface.SOCIAL_POST,
    ):
        result = evaluate_standard_longread_eligibility(_article(surface=surface))
        assert result.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
        assert EligibilityReason.NON_ARTICLE_SURFACE in result.reasons


def test_data_card_and_event_listing_are_not_standard_longreads():
    for medium in (ContentMedium.DATA_CARD, ContentMedium.EVENT_LISTING):
        result = evaluate_standard_longread_eligibility(_article(medium=medium))
        assert result.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
        assert EligibilityReason.DATA_OR_EVENT_MEDIUM in result.reasons


def test_unknown_and_paywall_surfaces_defer_instead_of_guessing():
    for surface in (PageSurface.UNKNOWN, PageSurface.PAYWALL):
        result = evaluate_standard_longread_eligibility(_article(surface=surface))
        assert result.disposition is StandardLongreadDisposition.UNKNOWN
        assert EligibilityReason.PAYWALL_OR_UNKNOWN_SURFACE in result.reasons


def test_unresolved_medium_or_asset_defers():
    result = evaluate_standard_longread_eligibility(
        _article(medium=ContentMedium.UNKNOWN, asset=AssetClass.UNKNOWN)
    )
    assert result.disposition is StandardLongreadDisposition.UNKNOWN
    assert EligibilityReason.UNRESOLVED_MEDIUM_OR_ASSET in result.reasons


def test_length_is_measurement_only_even_when_extremely_small():
    result = evaluate_standard_longread_eligibility(
        _article(),
        EligibilityEvidence(
            substantive_length_chars=900,
            substantive_length_source="offline_fixture",
        ),
    )
    assert result.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD
    assert EligibilityReason.LENGTH_MEASUREMENT_ONLY in result.reasons
    assert result.length_measurement_observed is True
    assert result.substantive_length_chars == 900
    assert result.substantive_length_source == "offline_fixture"


def test_negative_length_measurement_is_rejected_as_invalid_evidence():
    try:
        EligibilityEvidence(substantive_length_chars=-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative length evidence must fail")


def test_replay_summary_separates_asset_capture_from_hit_loss():
    rows = [
        EligibilityReplayRow(
            review_id="hit-1",
            review_label="值得",
            attribution_bucket="hit",
            failure_subtype="",
            disposition=StandardLongreadDisposition.ELIGIBLE_STANDARD,
        ),
        EligibilityReplayRow(
            review_id="paper-1",
            review_label="不应推荐",
            attribution_bucket="upstream_eligibility",
            failure_subtype="academic_paper",
            disposition=StandardLongreadDisposition.ROUTE_SPECIAL,
        ),
        EligibilityReplayRow(
            review_id="video-1",
            review_label="不应推荐",
            attribution_bucket="upstream_eligibility",
            failure_subtype="video",
            disposition=StandardLongreadDisposition.INELIGIBLE_STANDARD,
        ),
        EligibilityReplayRow(
            review_id="briefing-1",
            review_label="不应推荐",
            attribution_bucket="upstream_eligibility",
            failure_subtype="daily_briefing",
            disposition=StandardLongreadDisposition.INELIGIBLE_STANDARD,
        ),
    ]
    summary = summarize_eligibility_replay(rows)
    assert summary.total == 4
    assert summary.hit_count == 1
    assert summary.hit_lost_from_standard == 0
    assert summary.known_hit_loss_rate == 0.0
    assert summary.wrong_medium_asset_count == 3
    assert summary.wrong_medium_asset_removed_from_standard == 3
    assert summary.wrong_medium_asset_kept_standard == 0
    assert summary.wrong_medium_asset_capture_rate == 1.0
    assert summary.route_special_count == 1
    assert summary.ineligible_standard_count == 2


def test_replay_marks_noneligible_hit_as_explicit_loss():
    summary = summarize_eligibility_replay(
        [
            EligibilityReplayRow(
                review_id="known-hit",
                review_label="强烈值得",
                attribution_bucket="hit",
                failure_subtype="",
                disposition=StandardLongreadDisposition.UNKNOWN,
            )
        ]
    )
    assert summary.hit_count == 1
    assert summary.hit_lost_from_standard == 1
    assert summary.known_hit_loss_rate == 1.0
