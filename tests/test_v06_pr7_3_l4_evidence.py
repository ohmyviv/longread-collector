from __future__ import annotations

from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    PUBLICATION_VERSION,
    SOURCE_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EDITORIAL_JUDGE_VERSION


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260809-164300-BJT-pr73",
        group_id="pr73",
        scheduled_at_bj="2026-08-09 16:40:00",
        started_at_bj="2026-08-09 16:43:00",
        collector_version="collector-v0.6-pr7.3",
    )


def _record(
    item_id: str,
    *,
    url: str | None = None,
    title: str = "Evidence test article",
    hints: tuple[str, ...] = (),
    metadata: dict | None = None,
) -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url or f"https://mirror.example/{item_id}",
        title_hint=title,
        published_at_hints=hints,
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata=metadata or {},
    )


def _bundle(
    item_id: str,
    *,
    title: str = "Evidence test article",
    body: str = "",
    author: str = "",
    dates: tuple[str, ...] = (),
    canonical_links: tuple[str, ...] = (),
) -> AcquisitionBundle:
    text = body or f"# {title}\nA substantive acquired article body."
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=text,
        body_markdown=text,
        raw_title=title,
        raw_author=author,
        raw_dates=dates,
        raw_canonical_links=canonical_links,
        content_length=len(text),
        prose_length=len("".join(text.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_utc_timestamp_is_normalized_to_beijing_calendar_date() -> None:
    record = _record("utc-boundary")
    bundle = _bundle(
        record.item_id,
        dates=("2026-08-08T17:30:00Z",),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-09"
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["timezone_basis"] == "utc_to_bjt"
    assert selected["provenance"] == "acquisition_metadata"


def test_updated_date_is_context_not_a_conflict_with_published_date() -> None:
    title = "Published and updated"
    record = _record("published-updated", title=title)
    bundle = _bundle(
        record.item_id,
        title=title,
        body=(
            f"# {title}\n"
            "Published on August 1, 2026\n"
            "Updated on August 8, 2026\n"
            "Long-form analysis follows."
        ),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-01"
    assert result.freshness_facts["publication_conflict"] is False
    profile = result.freshness_facts["publication_evidence_profile"]
    updated = next(row for row in profile if row["semantic"] == "updated")
    assert updated["relation"] == "contextual"


def test_same_semantic_article_local_conflict_remains_explicit() -> None:
    title = "Conflicting publication dates"
    record = _record(
        "publication-conflict",
        title=title,
        metadata={
            "freshness": {
                "body_publication_evidence": {
                    "value": "2026-08-05",
                    "source": "body_header_chinese_byline_date",
                    "confidence": "high",
                    "raw": "日期：2026-08-05",
                }
            }
        },
    )
    bundle = _bundle(
        record.item_id,
        title=title,
        body=f"# {title}\n发布时间：2026-08-07\n正文。",
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.freshness_facts["publication_conflict"] is True
    assert set(result.freshness_facts["publication_conflict_values"]) == {
        "2026-08-05",
        "2026-08-07",
    }
    assert result.published_at_confidence <= 0.45


def test_url_date_is_persisted_but_not_promoted_by_itself() -> None:
    record = _record(
        "url-only-date",
        url="https://example.com/2026/08-07/url-only-date",
    )
    bundle = _bundle(record.item_id)
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == ""
    assert result.freshness_facts["publication_evidence_status"] == "non_publication_only"
    profile = result.freshness_facts["publication_evidence_profile"]
    assert profile[0]["source"] == "url_path_date"
    assert profile[0]["relation"] == "contextual"


def test_external_canonical_link_resolves_secondary_republish() -> None:
    record = _record(
        "external-canonical",
        url="https://mirror.example/articles/123",
    )
    bundle = _bundle(
        record.item_id,
        canonical_links=("https://original.example/story/123",),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == "https://original.example/story/123"
    assert result.original_publisher == "original.example"
    assert any(item.evidence_type == "canonical_link_relation" for item in result.evidence)


def test_same_host_canonical_link_does_not_create_republish_relation() -> None:
    record = _record(
        "same-host-canonical",
        url="https://publisher.example/story?id=123",
    )
    bundle = _bundle(
        record.item_id,
        canonical_links=("https://publisher.example/story/123",),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.source_action is SourceAction.NONE


def test_parent_subdomain_canonical_link_remains_same_source() -> None:
    record = _record(
        "same-site-canonical",
        url="https://m.publisher.example/story/123",
    )
    bundle = _bundle(
        record.item_id,
        canonical_links=("https://publisher.example/story/123",),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.source_action is SourceAction.NONE


def test_reuters_signature_on_non_wire_host_is_wire_republish() -> None:
    title = "Syndicated world report"
    record = _record(
        "wire-republish",
        url="https://localpaper.example/world/123",
        title=title,
    )
    bundle = _bundle(
        record.item_id,
        title=title,
        author="Reuters",
        body=f"# {title}\nLONDON (Reuters) - Governments agreed on a framework.",
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.WIRE_REPUBLISH
    assert result.source_action is SourceAction.FIND_ORIGINAL_ARTICLE
    assert result.original_publisher == "Reuters"
    assert result.canonical_source == "Reuters"
    assert any(item.evidence_type == "wire_service_evidence" for item in result.evidence)


def test_thomson_reuters_foundation_credit_does_not_create_wire_republish() -> None:
    record = _record(
        "wire-negative-control",
        url="https://research.example/report/123",
    )
    bundle = _bundle(
        record.item_id,
        body=(
            "# Independent report\n"
            "This report was commissioned independently. "
            "Designed by the Thomson Reuters Foundation. "
            "The views are the author's."
        ),
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.ORIGINAL
    assert result.original_publisher != "Reuters"


def test_explicit_translation_source_is_translated_republish() -> None:
    record = _record(
        "translated-republish",
        url="https://translator.example/articles/456",
    )
    bundle = _bundle(
        record.item_id,
        body="# 中文译文\n编译自：Financial Times\n正文。",
    )
    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.source_relationship is SourceRelationship.TRANSLATED_REPUBLISH
    assert result.source_action is SourceAction.FIND_ORIGINAL_ARTICLE
    assert result.original_publisher == "Financial Times"
    assert any(item.evidence_type == "translation_source_evidence" for item in result.evidence)


def test_pr73_is_l4_only_and_keeps_pr72_editorial_judge_frozen() -> None:
    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3"
    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3"
    assert SOURCE_VERSION == "canonical-source-v0.6-pr7.3"
    assert EDITORIAL_JUDGE_VERSION == "editorial-judge-v0.6-pr7.2"
