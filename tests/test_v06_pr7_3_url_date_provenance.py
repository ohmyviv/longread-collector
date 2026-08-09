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


def _bundle(item_id: str, title: str, body: str) -> AcquisitionBundle:
    return AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )


def test_legacy_resolved_url_path_date_is_demoted_back_to_context() -> None:
    title = "Legacy URL date only"
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="legacy-url-path-date",
        discovery_id="discovery-legacy-url-path-date",
        url="https://example.com/n1/2026/0807/story.html",
        title_hint=title,
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
    body = f"# {title}\nNo article-local publication date is stated."

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title, body)
    )

    assert result.published_at == ""
    assert result.freshness_facts["publication_evidence_status"] == "non_publication_only"
    profile = result.freshness_facts["publication_evidence_profile"]
    assert len(profile) == 1
    assert profile[0]["source"] == "url_path_date"
    assert profile[0]["normalized"] == "2026-08-07"
    assert profile[0]["provenance"] == "url_path"
    assert profile[0]["relation"] == "contextual"


def test_frozen_existing_body_evidence_is_not_overwritten_by_header_recovery() -> None:
    title = "Existing local date wins"
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="frozen-existing-body-date",
        discovery_id="discovery-frozen-existing-body-date",
        url="https://publisher.example/story/123",
        title_hint=title,
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata={
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
    body = (
        f"# {title}\n"
        "**2026年08月07日08:12**来源：示例媒体\n"
        "正文。"
    )

    result = CanonicalArticleResolver().canonicalize(
        _context(), record, _bundle(record.item_id, title, body)
    )

    assert result.published_at == "2026-08-05"
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "body_header_chinese_byline_date"
    assert selected["normalized"] == "2026-08-05"
    assert all(row["source"] != "body_header_chinese_source_timestamp" for row in profile)
