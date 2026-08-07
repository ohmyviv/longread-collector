import asyncio

from longread_collector.v06.acquisition import BudgetLedger
from longread_collector.v06.contracts import RunContext


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="budget-run",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-07 17:50:00",
        started_at_bj="2026-08-07 17:50:01",
        collector_version="collector-v0.6-pr5",
        max_acquisition_attempts=32,
        firecrawl_daily_limit=3,
    )


def test_concurrent_firecrawl_reservations_never_exceed_daily_cap() -> None:
    ledger = BudgetLedger(_context())

    async def scenario():
        decisions = await asyncio.gather(
            *(ledger.reserve_firecrawl("zh_evening") for _ in range(12))
        )
        snapshot = await ledger.snapshot()
        return decisions, snapshot

    decisions, snapshot = asyncio.run(scenario())
    assert sum(decision.allowed for decision in decisions) == 3
    assert snapshot.firecrawl_requests_reserved == 3
    assert all(
        decision.reason_code in {"firecrawl_request_reserved", "skipped_daily_cap"}
        for decision in decisions
    )


def test_concurrent_group_reservations_never_exceed_group_cap() -> None:
    ledger = BudgetLedger(_context(), firecrawl_group_limits={"zh_evening": 1})

    async def scenario():
        decisions = await asyncio.gather(
            *(ledger.reserve_firecrawl("zh_evening") for _ in range(8))
        )
        snapshot = await ledger.snapshot()
        return decisions, snapshot

    decisions, snapshot = asyncio.run(scenario())
    assert sum(decision.allowed for decision in decisions) == 1
    assert snapshot.firecrawl_group_reserved["zh_evening"] == 1
    assert sum(decision.reason_code == "skipped_group_cap" for decision in decisions) == 7
