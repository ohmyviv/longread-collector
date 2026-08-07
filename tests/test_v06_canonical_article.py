import json
from pathlib import Path

import pytest

from longread_collector.v06.canonical import CanonicalArticleResolver
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    AssetClass,
    ContentMedium,
    DiscoveryRecord,
    EditorialGenre,
    PageSurface,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)

FIXTURE = Path(__file__).parent / "fixtures" / "v06_canonical_day1.json"


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260806-195235-BJT-zh_evening",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-06 17:50:00",
        started_at_bj="2026-08-06 19:52:35",
        collector_version="collector-v0.5.6m",
    )


def _case_objects(case):
    metadata = {
        **case["metadata"],
        "discovery": {
            "source_name": case.get("source_name", ""),
            **case["metadata"].get("discovery", {}),
        },
        "content_metrics": case["metrics"],
    }
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="legacy-adapter-v0.6-pr1",
        run_id=_context().run_id,
        item_id=case["id"],
        discovery_id=f"discovery-{case['id']}",
        url=case["url"],
        title_hint=case["title"],
        published_at_hints=(case["published_at"],),
        source_id=case.get("source_name", ""),
        discovery_method="production_cache_replay",
        raw_metadata=metadata,
    )
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="legacy-adapter-v0.6-pr1",
        run_id=_context().run_id,
        item_id=case["id"],
        status=TechnicalStatus.SUCCESS,
        body_text=case["body"],
        body_markdown=case["body"],
        raw_title=case["title"],
        raw_dates=(case["published_at"],),
        content_length=len(case["body"]),
        prose_length=case["metrics"]["body_prose_chars"],
        video_count=case["metrics"]["video_count"],
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )
    return record, bundle


@pytest.fixture(scope="module")
def cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case_id",
    [
        "turnintl_analysis",
        "turnintl_feature",
        "turnintl_interview",
        "cctv_transcript",
        "external_people_shell",
        "boc_media_republish",
        "pbc_primary_republish",
        "shanghai_primary_document",
    ],
)
def test_production_replay_canonical_facts(cases, case_id):
    case = next(item for item in cases if item["id"] == case_id)
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    expected = case["expected"]

    if "resolved_title" in expected:
        assert result.resolved_title == expected["resolved_title"]
    if "published_at" in expected:
        assert result.published_at == expected["published_at"]
    assert result.page_surface is PageSurface(expected["page_surface"])
    assert result.main_content_medium is ContentMedium(expected["medium"])
    if "genre" in expected:
        assert result.editorial_genre is EditorialGenre(expected["genre"])
    assert result.asset_class is AssetClass(expected["asset_class"])
    assert result.source_relationship is SourceRelationship(expected["relationship"])
    if "canonical_source" in expected:
        assert result.canonical_source == expected["canonical_source"]
    if "source_action" in expected:
        assert result.source_action is SourceAction(expected["source_action"])


def test_video_count_does_not_override_substantive_written_body(cases):
    resolver = CanonicalArticleResolver()
    for case_id in ("turnintl_analysis", "turnintl_feature", "turnintl_interview"):
        case = next(item for item in cases if item["id"] == case_id)
        record, bundle = _case_objects(case)
        result = resolver.canonicalize(_context(), record, bundle)
        assert bundle.video_count >= 11
        assert result.main_content_medium is ContentMedium.WRITTEN_ARTICLE
        assert result.page_surface is PageSurface.ARTICLE_PAGE


def test_broadcast_transcript_requires_semantic_program_signals(cases):
    case = next(item for item in cases if item["id"] == "cctv_transcript")
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert bundle.prose_length > 5000
    assert result.main_content_medium is ContentMedium.TELEVISION_TRANSCRIPT
    assert result.asset_class is AssetClass.TRANSCRIPT


def test_external_shell_is_source_action_not_editorial_reject(cases):
    case = next(item for item in cases if item["id"] == "external_people_shell")
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.page_surface is PageSurface.EXTERNAL_LINK_STUB
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url.startswith("https://www.peopleapp.com/")
    assert result.canonical_source == "人民日报"


def test_title_and_primary_source_are_recovered_from_body(cases):
    case = next(item for item in cases if item["id"] == "pbc_primary_republish")
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.resolved_title == "中国人民银行召开2026年下半年工作会议"
    assert result.canonical_source == "中国人民银行"
    assert result.hosting_source == "中共广东省委金融委员会办公室"
    assert result.source_action is SourceAction.FIND_PRIMARY_DOCUMENT


def test_publication_resolver_is_factual_not_freshness_policy(cases):
    case = next(item for item in cases if item["id"] == "shanghai_primary_document")
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert result.published_at == "2026-07-28"
    assert result.freshness_facts["policy_applied"] is False
    assert result.published_at_confidence >= 0.95


def test_canonicalizer_does_not_mutate_inputs(cases):
    case = next(item for item in cases if item["id"] == "boc_media_republish")
    record, bundle = _case_objects(case)
    before_title = record.title_hint
    before_body = bundle.body_markdown
    CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    assert record.title_hint == before_title
    assert bundle.body_markdown == before_body


def test_canonical_evidence_is_field_specific(cases):
    case = next(item for item in cases if item["id"] == "cctv_transcript")
    record, bundle = _case_objects(case)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)
    evidence_types = {item.evidence_type for item in result.evidence}
    assert "publication_date" in evidence_types
    assert "medium_resolution" in evidence_types
    assert "source_relationship" in evidence_types
    assert "editorial_genre" in evidence_types
