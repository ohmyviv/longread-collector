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
        run_id="COL-20260809-pr73-date-profile",
        group_id="pr73-date-profile",
        scheduled_at_bj="2026-08-09 17:45:00",
        started_at_bj="2026-08-09 17:45:00",
        collector_version="collector-v0.6-pr7.3",
    )


def test_colocated_issued_and_published_dates_both_survive_profile() -> None:
    title = "上海市政策文件"
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id="shanghai-colocated-dates",
        discovery_id="discovery-shanghai-colocated-dates",
        url="https://www.shanghai.gov.cn/policy/example.html",
        title_hint=title,
        source_id="fixture",
        discovery_method="fixture",
    )
    body = (
        f"# {title}\n"
        "印发日期：2026-07-28 发布日期：2026-08-05\n"
        "政策正文。"
    )
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id=_context().run_id,
        item_id=record.item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-07-28"
    profile = result.freshness_facts["publication_evidence_profile"]
    article_rows = [row for row in profile if row["provenance"] == "article_header"]

    issued = next(row for row in article_rows if row["semantic"] == "issued")
    published = next(row for row in article_rows if row["semantic"] == "published")

    assert issued["normalized"] == "2026-07-28"
    assert issued["relation"] == "selected"
    assert published["normalized"] == "2026-08-05"
    assert published["relation"] == "alternative"
    assert result.freshness_facts["publication_conflict"] is False
