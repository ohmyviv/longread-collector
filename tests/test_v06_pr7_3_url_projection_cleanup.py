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
        run_id="COL-20260809-pr73-url-projection-cleanup",
        group_id="pr73-url-projection-cleanup",
        scheduled_at_bj="2026-08-09 19:45:00",
        started_at_bj="2026-08-09 19:45:00",
        collector_version="collector-v0.6-pr7.3",
    )


def _record(*, published_at_hints: tuple[str, ...]) -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="url-projection-cleanup",
        discovery_id="discovery-url-projection-cleanup",
        url="https://example.com/n1/2026/0807/story.html",
        title_hint="URL projection cleanup",
        published_at_hints=published_at_hints,
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


def _bundle(*, raw_dates: tuple[str, ...]) -> AcquisitionBundle:
    body = "# URL projection cleanup\nNo article-local publication date is stated."
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="url-projection-cleanup",
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title="URL projection cleanup",
        raw_dates=raw_dates,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_url_derived_date_cannot_reenter_through_adapter_projections() -> None:
    """Mirror the full-parallel shape that exposed the Final Review blocker."""

    record = _record(
        published_at_hints=("2026-08-07T00:00:00+08:00",),
    )
    bundle = _bundle(
        raw_dates=("2026-08-07T00:00:00+08:00",),
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == ""
    assert result.freshness_facts["publication_evidence_status"] == "non_publication_only"
    profile = result.freshness_facts["publication_evidence_profile"]
    assert profile == (
        {
            "source": "url_path_date",
            "semantic": "unknown",
            "provenance": "url_path",
            "article_local": False,
            "raw": "/2026/08/07/",
            "normalized": "2026-08-07",
            "confidence": 0.48,
            "timezone_basis": "date_only",
            "relation": "contextual",
        },
    )


def test_projection_cleanup_keeps_a_different_acquisition_date() -> None:
    record = _record(
        published_at_hints=("2026-08-07",),
    )
    bundle = _bundle(
        raw_dates=(
            "2026-08-07T00:00:00+08:00",
            "2026-08-09T00:00:00+08:00",
        ),
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-09"
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "acquisition_raw_date"
    assert selected["normalized"] == "2026-08-09"
    assert not any(
        row["provenance"] in {"acquisition_metadata", "discovery_metadata"}
        and row["normalized"] == "2026-08-07"
        for row in profile
    )
    assert any(
        row["provenance"] == "url_path"
        and row["normalized"] == "2026-08-07"
        and row["relation"] == "contextual"
        for row in profile
    )
