from datetime import datetime
from zoneinfo import ZoneInfo

from longread_collector.v06.contracts import (
    DiscoveryRecord,
    Evidence,
    GateAction,
    StageName,
    TechnicalStatus,
)
from longread_collector.v06.gates import AcquisitionGateService, GateContext

BJ = ZoneInfo("Asia/Shanghai")


def _record(
    *,
    item_id: str,
    url: str,
    title: str,
    date_values: tuple[tuple[str, float], ...] = (),
) -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="fixture",
        run_id="run-pr6-edges",
        item_id=item_id,
        discovery_id=f"discovery-{item_id}",
        url=url,
        canonical_url_hint=url,
        title_hint=title,
        source_id="fixture",
        discovery_method="fixture",
        query_or_section="fixture",
        rank=1,
        route_status=TechnicalStatus.SUCCESS,
        published_at_hints=tuple(value for value, _ in date_values),
        evidence=tuple(
            Evidence(
                evidence_id=f"{item_id}-date-{index}",
                evidence_type="publication_hint",
                source_stage=StageName.DISCOVERY,
                field="published_at_hint",
                value=value,
                confidence=confidence,
            )
            for index, (value, confidence) in enumerate(date_values, start=1)
        ),
    )


def _context() -> GateContext:
    return GateContext(now_bj=datetime(2026, 8, 7, 12, 0, tzinfo=BJ))


def test_deep_article_under_topic_path_is_not_taxonomy_hard_rejected():
    record = _record(
        item_id="topic-article",
        url="https://example.com/topics/ai/deep-reported-feature.html",
        title="A deeply reported feature about AI",
    )
    decision = AcquisitionGateService().decide(record, _context()).decision
    assert decision.action is GateAction.ACQUIRE


def test_shallow_topic_index_remains_deterministic_hard_reject():
    record = _record(
        item_id="topic-index",
        url="https://example.com/topics/ai",
        title="AI",
    )
    decision = AcquisitionGateService().decide(record, _context()).decision
    assert decision.action is GateAction.HARD_REJECT
    assert decision.reason_code == "category_tag_topic_index_route"


def test_high_confidence_stale_date_plus_credible_conflicting_date_defers():
    record = _record(
        item_id="mixed-date-conflict",
        url="https://example.com/article/conflicted.html",
        title="Article with unresolved publication metadata",
        date_values=(("2026-06-01", 0.98), ("2026-08-06", 0.70)),
    )
    decision = AcquisitionGateService().decide(record, _context()).decision
    assert decision.action is GateAction.DEFER
    assert decision.reason_code == "publication_date_conflict"
