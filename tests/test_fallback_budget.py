import asyncio

from longread_collector.extraction import FallbackBudget


def test_fallback_budget_is_atomic() -> None:
    async def run() -> list[bool]:
        budget = FallbackBudget(remaining=3)
        return await asyncio.gather(*(budget.try_acquire() for _ in range(8)))

    results = asyncio.run(run())
    assert sum(results) == 3
