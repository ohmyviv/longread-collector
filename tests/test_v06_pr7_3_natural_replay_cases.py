from __future__ import annotations

from longread_collector.v06.canonical import CanonicalArticleResolver
from longread_collector.v06.contracts import (
    AcquisitionBundle,
    DiscoveryRecord,
    RunContext,
    SourceAction,
    SourceRelationship,
    TechnicalStatus,
)


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260809-041344-BJT-pre_report-pr73-replay",
        group_id="pr73-natural-replay",
        scheduled_at_bj="2026-08-09 03:57:00",
        started_at_bj="2026-08-09 04:13:44",
        collector_version="collector-v0.6-pr7.3",
    )


def test_people_daily_republish_recovers_local_date_and_original_link() -> None:
    title = "“紧紧抓住那些惠及面广、牵一发而动全身的工作” --新闻报道-中国共产党新闻网"
    record = DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture-natural-replay",
        run_id=_context().run_id,
        item_id="people-daily-natural-replay",
        discovery_id="discovery-people-daily-natural-replay",
        url="http://cpc.people.com.cn/n1/2026/0808/c64387-40775983.html",
        title_hint=title,
        published_at_hints=("Sat, 08 Aug 2026 00:40:49 GMT",),
        source_id="fixture",
        discovery_method="fixture",
        raw_metadata={
            "freshness": {
                "published_at_resolved": "2026-08-08T08:40:49+08:00",
                "published_at_source": "page_metadata_published",
                "published_at_confidence": "medium",
            },
            "source_resolution": {"resolved": "people"},
        },
    )
    body = (
        f"# {title}\n\n"
        "## ——突出重点推进健康中国建设观察\n\n"
        "本报记者 白剑峰 申少铁 陆凡冰\n\n"
        "**2026年08月08日08:12**来源："
        "[人民网－人民日报](http://paper.people.com.cn/rmrb/pc/content/202608/08/content_30173729.html)\n\n"
        "8月8日，我国迎来第十八个全民健身日。\n"
        "一人健康是立身之本，人民健康是立国之基。\n"
        "新时代以来，健康中国建设持续推进。\n"
        "《 人民日报 》（ 2026年08月08日 01 版）\n"
    )
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="fixture-natural-replay",
        run_id=_context().run_id,
        item_id=record.item_id,
        status=TechnicalStatus.SUCCESS,
        body_text=body,
        body_markdown=body,
        raw_title=title,
        raw_dates=("Sat, 08 Aug 2026 00:40:49 GMT",),
        content_length=len(body),
        prose_length=len("".join(body.split())),
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=True,
    )

    result = CanonicalArticleResolver().canonicalize(_context(), record, bundle)

    assert result.published_at == "2026-08-08"
    assert result.freshness_facts["publication_conflict"] is False
    profile = result.freshness_facts["publication_evidence_profile"]
    selected = next(row for row in profile if row["relation"] == "selected")
    assert selected["source"] == "body_header_chinese_source_timestamp"
    assert selected["provenance"] == "article_local_metadata"
    assert selected["semantic"] == "published"

    assert result.source_relationship is SourceRelationship.SECONDARY_REPUBLISH
    assert result.source_action is SourceAction.REPLACE_WITH_ORIGINAL
    assert result.canonical_content_url == (
        "http://paper.people.com.cn/rmrb/pc/content/202608/08/content_30173729.html"
    )
    assert result.original_publisher == "人民日报"
    assert result.canonical_source == "人民日报"
    assert any(item.evidence_type == "explicit_source_link" for item in result.evidence)
