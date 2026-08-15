from longread_collector.v06.contracts import (
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    PageSurface,
)
from longread_collector.v06.eligibility import (
    ELIGIBILITY_VERSION,
    EligibilityReason,
    StandardLongreadDisposition,
)
from longread_collector.v06.eligibility_e1 import (
    E1_ELIGIBILITY_VERSION,
    E1IdentityEvidence,
    E1IdentityKind,
    evaluate_standard_longread_eligibility_e1,
    resolve_e1_identity,
)
from longread_collector.v06.eligibility_e2 import (
    LengthEvidenceQuality,
    SubstantiveLengthEvidence,
    assess_e2_measurement,
)
from longread_collector.v06.eligibility_e2_replay import (
    LengthReplayRow,
    replay_length_threshold,
)


def _article(*, item_id="case"):
    return CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="canonical-source-v0.6-pr7.3.9",
        run_id="COL-E1E2-OFFLINE",
        item_id=item_id,
        content_id=f"content-{item_id}",
        display_url=f"https://example.invalid/{item_id}",
        page_surface=PageSurface.ARTICLE_PAGE,
        main_content_medium=ContentMedium.WRITTEN_ARTICLE,
        asset_class=AssetClass.MEDIA_ARTICLE,
    )


def test_e1_routes_exact_arxiv_document_urls_special_even_if_legacy_facts_say_article():
    for url in (
        "https://arxiv.org/abs/2608.07077",
        "https://arxiv.org/pdf/2608.07069",
        "https://arxiv.org/html/2608.05466",
    ):
        result = evaluate_standard_longread_eligibility_e1(
            _article(),
            E1IdentityEvidence(url=url, title="A research paper", source="arXiv"),
        )
        assert result.stage_version == E1_ELIGIBILITY_VERSION
        assert result.disposition is StandardLongreadDisposition.ROUTE_SPECIAL
        assert result.reasons == (EligibilityReason.ACADEMIC_ASSET,)


def test_e1_does_not_route_journalism_about_an_arxiv_paper():
    result = evaluate_standard_longread_eligibility_e1(
        _article(),
        E1IdentityEvidence(
            url="https://www.wired.com/story/researchers-published-a-paper-on-arxiv/",
            title="What a new arXiv paper gets right about reasoning",
            source="WIRED",
        ),
    )
    assert result.stage_version == ELIGIBILITY_VERSION
    assert result.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD


def test_e1_resolves_the_two_reviewed_guardian_day_briefings():
    fixtures = (
        (
            "https://www.theguardian.com/world/2026/aug/04/tuesday-briefing-inside-the-rights-heated-climate-denial-debate",
            "Tuesday briefing: Inside the right's heated climate-denial debate",
        ),
        (
            "https://www.theguardian.com/world/2026/aug/05/wednesday-briefing-how-misinformation-and-a-hardened-immigration-policy-turned-ceuta-into-europes-latest-flashpoint",
            "Wednesday briefing: How misinformation and a hardened immigration policy turned Ceuta into Europe's latest flashpoint",
        ),
    )
    for url, title in fixtures:
        resolution = resolve_e1_identity(
            E1IdentityEvidence(
                url=url,
                title=title,
                source="The Guardian",
                author="The Guardian briefing team",
            )
        )
        assert resolution.kind is E1IdentityKind.RECURRING_BRIEFING
        result = evaluate_standard_longread_eligibility_e1(
            _article(),
            E1IdentityEvidence(url=url, title=title, source="The Guardian"),
        )
        assert result.stage_version == E1_ELIGIBILITY_VERSION
        assert result.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
        assert result.reasons == (EligibilityReason.ROUNDUP_IDENTITY,)


def test_e1_does_not_blacklist_guardian_or_generic_briefing_words():
    for evidence in (
        E1IdentityEvidence(
            url="https://www.theguardian.com/environment/2026/aug/15/deep-analysis",
            title="A deep analysis of Britain's climate politics",
            source="The Guardian",
        ),
        E1IdentityEvidence(
            url="https://example.com/analysis",
            title="Tuesday briefing: a long-form history of intelligence briefings",
            source="Example Magazine",
        ),
    ):
        result = evaluate_standard_longread_eligibility_e1(_article(), evidence)
        assert result.stage_version == ELIGIBILITY_VERSION
        assert result.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD


def test_e1_video_requires_explicit_page_evidence_and_abstains_without_it():
    historical_video = E1IdentityEvidence(
        url="https://m.bjnews.com.cn/detail/1785199934129721.html",
        title="起底“隐形杀手”防晒衣：实测4件全翻车，厂家嘲讽记者“傻瓜”",
        source="新京报",
    )
    unresolved = resolve_e1_identity(historical_video)
    assert unresolved.kind is E1IdentityKind.UNRESOLVED
    fallback = evaluate_standard_longread_eligibility_e1(_article(), historical_video)
    assert fallback.stage_version == ELIGIBILITY_VERSION
    assert fallback.disposition is StandardLongreadDisposition.ELIGIBLE_STANDARD

    explicit = evaluate_standard_longread_eligibility_e1(
        _article(),
        E1IdentityEvidence(
            url=historical_video.url,
            title=historical_video.title,
            source=historical_video.source,
            explicit_video_page=True,
        ),
    )
    assert explicit.stage_version == E1_ELIGIBILITY_VERSION
    assert explicit.disposition is StandardLongreadDisposition.INELIGIBLE_STANDARD
    assert explicit.reasons == (EligibilityReason.VIDEO_MEDIUM,)


def test_e2_legacy_body_chars_are_measurement_only_not_hard_gate_evidence():
    assessment = assess_e2_measurement(
        SubstantiveLengthEvidence(
            chars=9000,
            source="final_items.body_chars_read",
            legacy_body_chars_read=True,
        )
    )
    assert assessment.quality is LengthEvidenceQuality.LEGACY_APPROXIMATE
    assert assessment.hard_gate_eligible is False
    assert assessment.reason_code == "legacy_body_chars_read_provenance_incomplete"


def test_e2_truncated_body_cannot_support_a_hard_gate():
    assessment = assess_e2_measurement(
        SubstantiveLengthEvidence(
            chars=2800,
            source="acquisition.prose_chars",
            body_complete=False,
            extraction_truncated=True,
            boilerplate_removed=True,
        )
    )
    assert assessment.quality is LengthEvidenceQuality.INCOMPLETE
    assert assessment.hard_gate_eligible is False


def test_e2_complete_clean_body_is_measurement_eligible_but_no_threshold_is_applied():
    assessment = assess_e2_measurement(
        SubstantiveLengthEvidence(
            chars=3100,
            source="offline_clean_body",
            body_complete=True,
            extraction_truncated=False,
            boilerplate_removed=True,
            paragraph_count=18,
            heading_count=2,
            prose_ratio=0.91,
        )
    )
    assert assessment.quality is LengthEvidenceQuality.TRUSTED_SUBSTANTIVE
    assert assessment.hard_gate_eligible is True
    assert assessment.structural_measurement_observed is True
    assert assessment.chars == 3100


def test_e2_threshold_replay_exposes_short_capture_vs_known_hit_loss():
    rows = (
        LengthReplayRow("short-2600", "不应推荐", True, 2600),
        LengthReplayRow("short-4200", "不应推荐", True, 4200),
        LengthReplayRow("short-9000", "一般", True, 9000),
        LengthReplayRow("hit-3000", "值得", False, 3000),
        LengthReplayRow("hit-4200", "强烈值得", False, 4200),
        LengthReplayRow("hit-5200", "值得", False, 5200),
        LengthReplayRow("hit-12000", "值得", False, 12000),
    )
    replay = replay_length_threshold(rows, 9500)
    assert replay.human_short_count == 3
    assert replay.human_short_captured == 3
    assert replay.human_short_capture_rate == 1.0
    assert replay.hit_count == 4
    assert replay.hit_lost == 3
    assert replay.known_hit_loss_rate == 0.75


def test_e2_threshold_replay_preserves_unknown_lengths():
    replay = replay_length_threshold(
        (
            LengthReplayRow("briefing", "不应推荐", False, None),
            LengthReplayRow("hit", "值得", False, 5000),
        ),
        4000,
    )
    assert replay.total_rows == 2
    assert replay.observed_length_rows == 1
    assert replay.unknown_length_rows == 1
    assert replay.hit_lost == 0
