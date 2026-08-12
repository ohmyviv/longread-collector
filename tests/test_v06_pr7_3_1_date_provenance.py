from __future__ import annotations

from longread_collector.models import DiscoveredURL, ExtractedArticle
from longread_collector.v06.canonical import (
    CANONICAL_SERVICE_VERSION,
    PUBLICATION_VERSION,
    CanonicalArticleResolver,
)
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    Evidence,
    GateAction,
    RunContext,
    StageName,
    TechnicalStatus,
)
from longread_collector.v06.legacy import (
    PUBLICATION_EVIDENCE_BRIDGE_VERSION,
    LegacyV056mAdapter,
)
from longread_collector.v06.shadow.shared import share_control_acquisition


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260809-230000-BJT-intl_early-pr731-replay",
        group_id="intl_early",
        scheduled_at_bj="2026-08-09 23:00:00",
        started_at_bj="2026-08-09 23:06:28",
        collector_version="collector-v0.6-pr7.3.1",
    )


def _evidence(
    item_id: str,
    ordinal: int,
    *,
    value: str,
    source: str,
    confidence: str,
    raw: str,
    role: str = "published",
    priority: int = 0,
) -> Evidence:
    return Evidence(
        evidence_id=f"{item_id}-legacy-publication-{ordinal:02d}",
        evidence_type="legacy_publication_date_candidate",
        source_stage=StageName.ACQUISITION,
        field="publication_date_candidate",
        value={
            "value": value,
            "source": source,
            "confidence": confidence,
            "raw": raw,
            "role": role,
            "priority": priority,
        },
        confidence={"high": 0.98, "medium": 0.86, "low": 0.58}[confidence],
        extractor=PUBLICATION_EVIDENCE_BRIDGE_VERSION,
    )


def _record(
    *,
    item_id: str,
    url: str,
    title: str,
    raw_metadata: dict | None = None,
    hints: tuple[str, ...] = (),
):
    from longread_collector.v06.contracts import DiscoveryRecord

    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        title_hint=title,
        published_at_hints=hints,
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata=raw_metadata or {},
    )


def test_cen_related_card_standalone_date_no_longer_overrides_page_metadata() -> None:
    item_id = "cen-snail-natural-regression"
    title = "How snails use chemistry to modify their mucus materials"
    record = _record(
        item_id=item_id,
        url="https://cen.acs.org/materials/biobased-materials/snails-use-chemistry-modify-mucus/104/web/2026/08",
        title=title,
    )
    body = (
        f"# {title}\n\n"
        "Mineral chemistry, protein networks, and physical processing help generate everything.\n\n"
        "by Anirban Mukhopadhyay, special to C&EN\n\n"
        "August 7, 2026 3 min read\n\n"
        + ("Article reporting and analysis. " * 120)
        + "\n\nRelated\n\nAI-designed superglue retains extreme strength under water\n\n"
        "August 7, 2025\n"
    )
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        raw_dates=("2025-08-07T00:00:00+08:00",),
        content_length=len(body),
        prose_length=len(body),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
        evidence=(
            _evidence(
                item_id,
                1,
                value="2025-08-07T00:00:00+08:00",
                source="body_header_standalone_date",
                confidence="high",
                raw="August 7, 2025",
                priority=110,
            ),
            _evidence(
                item_id,
                2,
                value="2026-08-07T00:00:00+08:00",
                source="page_metadata_published",
                confidence="medium",
                raw="2026-08-07",
                priority=75,
            ),
            _evidence(
                item_id,
                3,
                value="2025-08-07T00:00:00+08:00",
                source="discovery_metadata",
                confidence="medium",
                raw="2025-08-07T00:00:00+08:00",
                priority=70,
            ),
        ),
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-07"
    assert result.freshness_facts["publication_conflict"] is False
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "page_metadata_published"
    assert selected["provenance"] == "page_metadata"
    bad = next(row for row in profile if row["source"] == "body_header_standalone_date")
    assert bad["normalized"] == "2025-08-07"
    assert bad["article_local"] is False
    assert bad["provenance"] == "acquisition_metadata"
    assert bad["confidence"] == 0.58


def test_same_day_page_metadata_survives_url_date_demotion() -> None:
    item_id = "new-humanitarian-same-day-url"
    title = "South Africa feels the economic cost of anti-migrant xenophobia"
    record = _record(
        item_id=item_id,
        url="https://www.thenewhumanitarian.org/analysis/2026/08/05/south-africa-feels-economic-cost-anti-migrant-xenophobia",
        title=title,
        hints=("2026-08-05T00:00:00+08:00",),
        raw_metadata={
            "freshness": {
                "published_at_resolved": "2026-08-05T00:00:00+08:00",
                "published_at_source": "url_path",
                "published_at_confidence": "low",
            }
        },
    )
    body = f"# {title}\n\n5 August 2026\n\n" + ("Field reporting. " * 160)
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        raw_dates=("2026-08-05T21:59:54+08:00",),
        content_length=len(body),
        prose_length=len(body),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
        evidence=(
            _evidence(
                item_id,
                1,
                value="2026-08-05T21:59:54+08:00",
                source="page_metadata_published",
                confidence="medium",
                raw="2026-08-05T14:59:54+0100",
                priority=75,
            ),
            _evidence(
                item_id,
                2,
                value="2026-08-05T00:00:00+08:00",
                source="url_path",
                confidence="low",
                raw="2026-08-05",
                priority=30,
            ),
        ),
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-05"
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "page_metadata_published"
    assert selected["provenance"] == "page_metadata"
    url_rows = [row for row in profile if row["provenance"] == "url_path"]
    assert url_rows
    assert all(row["relation"] == "contextual" for row in url_rows)


def test_legacy_bridge_and_shared_acquisition_preserve_structured_date_evidence() -> None:
    title = "Preserve page publication provenance"
    discovered = DiscoveredURL(
        url="https://publisher.example/2026/08/05/story",
        title=title,
        published_at="2026-08-05",
        discovery_method="section_scan",
        query_or_source="source:fixture",
        metadata={"source_id": "fixture"},
    )
    article = ExtractedArticle(
        article_id="bridge-item",
        url=discovered.url,
        url_canonical=discovered.url,
        domain="publisher.example",
        title=title,
        published_at="2026-08-05T00:00:00+08:00",
        canonical_source="Fixture Publisher",
        hosting_source="Fixture Publisher",
        content_markdown=f"# {title}\n\n" + ("Long article body. " * 150),
        content_chars=3000,
        extractor_used="jina",
        extraction_status="success",
        verification_level="B",
        eligible_for_editor=True,
        classification_version="fixture",
        metadata={
            "freshness": {
                "evidence": [
                    {
                        "value": "2026-08-05T12:00:00+08:00",
                        "source": "page_metadata_published",
                        "confidence": "medium",
                        "priority": 75,
                        "raw": "2026-08-05T04:00:00Z",
                        "role": "published",
                    }
                ]
            }
        },
    )

    adapted = LegacyV056mAdapter().adapt_item(
        context=_context(),
        discovered=discovered,
        article=article,
        created_at_bj=_context().started_at_bj,
    )
    bridged = [
        evidence
        for evidence in adapted.acquisition.evidence
        if evidence.evidence_type == "legacy_publication_date_candidate"
    ]
    assert len(bridged) == 1
    assert bridged[0].value["source"] == "page_metadata_published"

    shared = share_control_acquisition(
        adapted.acquisition,
        shadow_item_id="shadow-bridge-item",
        gate_action=GateAction.ACQUIRE,
        created_at_bj=_context().started_at_bj,
        parent_event_id="gate-event",
    )
    assert shared.bundle.attempts == ()
    assert shared.bundle.total_cost == 0.0
    assert any(
        evidence.evidence_type == "legacy_publication_date_candidate"
        for evidence in shared.bundle.evidence
    )
    assert [evidence.evidence_type for evidence in shared.event.evidence] == [
        "shared_control_acquisition"
    ]


def test_date_provenance_regressions_run_under_current_pr738_runtime() -> None:
    from longread_collector.v06.shadow.pipeline import PARALLEL_SHADOW_PIPELINE_VERSION

    assert PUBLICATION_VERSION == "canonical-publication-v0.6-pr7.3.7"
    assert CANONICAL_SERVICE_VERSION == "canonical-article-resolver-v0.6-pr7.3.9"
    assert PARALLEL_SHADOW_PIPELINE_VERSION == "collector-v0.6-pr7.3.9"
