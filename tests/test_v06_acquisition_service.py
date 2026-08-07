import asyncio

from longread_collector.v06.acquisition import AcquisitionService, BudgetLedger
from longread_collector.v06.acquisition.types import ExtractorPayload
from longread_collector.v06.audit.metrics import summarize_stage_events
from longread_collector.v06.contracts import (
    DiscoveryRecord,
    GateAction,
    GateDecision,
    RunContext,
    StageEventType,
    TechnicalStatus,
)


class FakeExtractor:
    def __init__(self, name: str, payload: ExtractorPayload | Exception, *, paid: bool = False):
        self.name = name
        self.payload = payload
        self.paid = paid
        self.calls = 0

    async def extract(self, record: DiscoveryRecord) -> ExtractorPayload:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _context(*, max_attempts: int = 32, firecrawl_limit: int = 3) -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="RUN-PR5",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-07 17:50:00",
        started_at_bj="2026-08-07 17:50:01",
        collector_version="collector-v0.6-pr5",
        max_acquisition_attempts=max_attempts,
        firecrawl_daily_limit=firecrawl_limit,
    )


def _record(item_id: str = "item-1", title: str = "深度报道") -> DiscoveryRecord:
    return DiscoveryRecord(
        schema_version="v06-contracts-v1",
        stage_version="discovery-test",
        run_id="RUN-PR5",
        item_id=item_id,
        discovery_id=f"d-{item_id}",
        url=f"https://example.com/{item_id}",
        title_hint=title,
        published_at_hints=("2026-08-07",),
    )


def _gate(item_id: str = "item-1") -> GateDecision:
    return GateDecision(
        schema_version="v06-contracts-v1",
        stage_version="gate-test",
        run_id="RUN-PR5",
        item_id=item_id,
        action=GateAction.ACQUIRE,
        reason_code="test_acquire",
        confidence=1.0,
    )


def _body(paragraphs: int = 3, chars: int = 450) -> str:
    return "\n\n".join(
        ("这是连续正文，包含事实、背景、分析和采访材料。" * 40)[:chars]
        for _ in range(paragraphs)
    )


def _payload(name: str, body: str, **kwargs) -> ExtractorPayload:
    return ExtractorPayload(
        extractor=name,
        markdown=body,
        title=kwargs.pop("title", "深度报道"),
        latency_ms=kwargs.pop("latency_ms", 10),
        credits_used=kwargs.pop("credits_used", 0.0),
        http_status=kwargs.pop("http_status", 200),
        **kwargs,
    )


def test_jina_sufficient_stops_before_direct_and_firecrawl() -> None:
    jina = FakeExtractor("jina", _payload("jina", _body()))
    direct = FakeExtractor("direct_html", _payload("direct_html", _body()))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body(), credits_used=1), paid=True)
    context = _context()
    ledger = BudgetLedger(context)
    service = AcquisitionService((jina, direct, firecrawl))

    run = asyncio.run(service.acquire(context, _record(), _gate(), ledger))

    assert run.bundle.status is TechnicalStatus.SUCCESS
    assert run.bundle.sufficient_for_editorial_judgment is True
    assert [a.extractor for a in run.bundle.attempts] == ["jina"]
    assert jina.calls == 1
    assert direct.calls == 0
    assert firecrawl.calls == 0
    snapshot = asyncio.run(ledger.snapshot())
    assert snapshot.firecrawl_requests_reserved == 0


def test_training_event_body_is_sufficient_to_stop_without_firecrawl() -> None:
    training = (
        "全市镇街党工委书记能力建设专题培训班开班。\n\n"
        "开班仪式上有关负责人讲话并介绍课程安排和参训人员。" * 10
        + "\n\n培训班设置专题教学、交流研讨和结业环节。" * 10
    )
    jina = FakeExtractor("jina", _payload("jina", training, title="专题培训班开班"))
    direct = FakeExtractor("direct_html", _payload("direct_html", _body()))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body(), credits_used=1), paid=True)
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context,
            _record(title="专题培训班开班"),
            _gate(),
            ledger,
        )
    )

    assert run.bundle.sufficient_for_editorial_judgment is True
    assert direct.calls == 0
    assert firecrawl.calls == 0


def test_direct_html_recovery_stops_before_firecrawl() -> None:
    jina = FakeExtractor("jina", _payload("jina", "只有很短的一段。"))
    direct = FakeExtractor("direct_html", _payload("direct_html", _body()))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body(), credits_used=1), paid=True)
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )

    assert [a.extractor for a in run.bundle.attempts] == ["jina", "direct_html"]
    assert run.bundle.best_attempt_id == run.bundle.attempts[1].attempt_id
    assert run.bundle.sufficient_for_editorial_judgment is True
    assert firecrawl.calls == 0


def test_firecrawl_only_runs_after_zero_cost_extractors_are_insufficient() -> None:
    jina = FakeExtractor("jina", _payload("jina", "短正文。"))
    direct = FakeExtractor("direct_html", _payload("direct_html", "仍然很短。"))
    firecrawl = FakeExtractor(
        "firecrawl",
        _payload("firecrawl", _body(), credits_used=1),
        paid=True,
    )
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )

    assert [a.extractor for a in run.bundle.attempts] == [
        "jina",
        "direct_html",
        "firecrawl",
    ]
    assert firecrawl.calls == 1
    snapshot = asyncio.run(ledger.snapshot())
    assert snapshot.firecrawl_requests_reserved == 1
    metrics = summarize_stage_events(run.events)
    assert metrics.firecrawl_requests_sent == 1
    assert metrics.firecrawl_requests_succeeded == 1
    assert metrics.extractor_request_counts["firecrawl"] == 1


def test_firecrawl_daily_cap_creates_skipped_attempt_without_request() -> None:
    jina = FakeExtractor("jina", _payload("jina", "短正文。"))
    direct = FakeExtractor("direct_html", _payload("direct_html", "仍然很短。"))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body()), paid=True)
    context = _context(firecrawl_limit=0)
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )

    assert firecrawl.calls == 0
    assert run.bundle.attempts[-1].extractor == "firecrawl"
    assert run.bundle.attempts[-1].status is TechnicalStatus.SKIPPED
    assert run.bundle.attempts[-1].request_sent is False
    metrics = summarize_stage_events(run.events)
    assert metrics.firecrawl_requests_sent == 0
    assert metrics.firecrawl_requests_skipped_daily_cap == 1


def test_firecrawl_group_cap_is_enforced_before_request() -> None:
    jina = FakeExtractor("jina", _payload("jina", "短正文。"))
    direct = FakeExtractor("direct_html", _payload("direct_html", "仍然很短。"))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body()), paid=True)
    context = _context()
    ledger = BudgetLedger(context, firecrawl_group_limits={"zh_evening": 0})

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )

    assert firecrawl.calls == 0
    metrics = summarize_stage_events(run.events)
    assert metrics.firecrawl_requests_skipped_group_cap == 1


def test_external_link_shell_stops_for_source_chase_without_firecrawl() -> None:
    payload = _payload(
        "jina",
        "当前页面只提供原文入口。",
        outbound_links=("https://peopleapp.example/original",),
        metadata={"external_link_stub": True},
    )
    jina = FakeExtractor("jina", payload)
    direct = FakeExtractor("direct_html", _payload("direct_html", _body()))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body()), paid=True)
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )

    assert run.bundle.sufficient_for_source_chase is True
    assert run.bundle.sufficient_for_editorial_judgment is False
    assert direct.calls == 0
    assert firecrawl.calls == 0


def test_item_cap_prevents_33rd_acquisition_before_any_extractor_call() -> None:
    extractor = FakeExtractor("jina", _payload("jina", _body()))
    context = _context(max_attempts=1)
    ledger = BudgetLedger(context)
    service = AcquisitionService((extractor,))

    first = asyncio.run(service.acquire(context, _record("item-1"), _gate("item-1"), ledger))
    second = asyncio.run(service.acquire(context, _record("item-2"), _gate("item-2"), ledger))

    assert first.bundle.status is TechnicalStatus.SUCCESS
    assert second.bundle.status is TechnicalStatus.SKIPPED
    assert second.events[0].reason_code == "acquisition_item_cap_exhausted"
    assert extractor.calls == 1


def test_failed_extractor_falls_through_and_request_failure_is_audited() -> None:
    jina = FakeExtractor("jina", RuntimeError("jina failed"))
    direct = FakeExtractor("direct_html", _payload("direct_html", _body()))
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct)).acquire(context, _record(), _gate(), ledger)
    )

    assert run.bundle.status is TechnicalStatus.SUCCESS
    attempt_events = [e for e in run.events if e.event_type is StageEventType.EXTRACTOR_ATTEMPT]
    assert attempt_events[0].attributes["request_outcome"] == "request_failed"
    assert attempt_events[1].attributes["request_outcome"] == "request_succeeded"


def test_attempt_events_carry_budget_and_information_gain_evidence() -> None:
    jina = FakeExtractor("jina", _payload("jina", "短正文。"))
    direct = FakeExtractor("direct_html", _payload("direct_html", "仍然很短。"))
    firecrawl = FakeExtractor("firecrawl", _payload("firecrawl", _body(), credits_used=1), paid=True)
    context = _context()
    ledger = BudgetLedger(context)

    run = asyncio.run(
        AcquisitionService((jina, direct, firecrawl)).acquire(
            context, _record(), _gate(), ledger
        )
    )
    fc_event = next(
        event
        for event in run.events
        if event.event_type is StageEventType.EXTRACTOR_ATTEMPT
        and event.attributes["extractor"] == "firecrawl"
    )
    assert fc_event.attributes["budget_before"]["firecrawl_requests_reserved"] == 0
    assert fc_event.attributes["budget_after"]["firecrawl_requests_reserved"] == 1
    assert fc_event.attributes["expected_information_gain"] > 0
    assert fc_event.cost == 1.0
