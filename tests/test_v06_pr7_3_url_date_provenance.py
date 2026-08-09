from __future__ import annotations

from longread_collector.v06.canonical import CanonicalArticleResolver
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    RunContext,
    TechnicalStatus,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260809-pr73-url-provenance",
        group_id="pr73-url-provenance",
        scheduled_at_bj="2026-08-09 17:55:00",
        started_at_bj="2026-08-09 17:55:00",
        collector_version="collector-v0.6-pr7.3",
    )


def test_legacy_resolved_url_path_date_is_demoted_back_to_context() -> None:
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="legacy-url-path-date",
        discovery_id="discovery-legacy-url-path-date",
        url="https://example.com/n1/2026/0807/story.html",
        title_hint="Legacy URL date only",
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata={
            "freshness": {
                "published_at_resolved": "2026-08-07T00:00:00+08:00",
                "published_at_source": "url_path_legacy_date",
                "published_at_confidence": "medium",
            }
        },
    )
    body = "# Legacy URL date only\nNo article-local publication date is stated."
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=record.item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=record.title_hint,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == ""
    assert result.freshness_facts["publication_evidence_status"] == "non_publication_only"
    profile = result.freshness_facts["publication_evidence_profile"]
    assert len(profile) == 1
    assert profile[0]["source"] == "url_path_date"
    assert profile[0]["normalized"] == "2026-08-07"
    assert profile[0]["provenance"] == "url_path"
    assert profile[0]["relation"] == "contextual"
