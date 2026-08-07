"""Unified acquisition and Firecrawl request budget ledger for v0.6 PR-5."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from types import MappingProxyType
from typing import Mapping

from ..contracts import RunContext


BUDGET_LEDGER_VERSION = "acquisition-budget-v0.6-pr5"


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    acquisition_items_started: int
    acquisition_item_limit: int
    firecrawl_requests_reserved: int
    firecrawl_daily_limit: int
    firecrawl_group_reserved: Mapping[str, int]
    firecrawl_group_limits: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "firecrawl_group_reserved",
            MappingProxyType(dict(self.firecrawl_group_reserved)),
        )
        object.__setattr__(
            self,
            "firecrawl_group_limits",
            MappingProxyType(dict(self.firecrawl_group_limits)),
        )


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    allowed: bool
    reason_code: str
    before: BudgetSnapshot
    after: BudgetSnapshot


class BudgetLedger:
    """Concurrency-safe hard budget accounting.

    Reservations happen *before* a request is sent. Failed paid requests remain
    reserved so concurrent tasks cannot exceed the hard request ceiling. The
    critical sections contain no I/O, so a small process-local mutex avoids
    binding the ledger to one asyncio event loop.
    """

    def __init__(
        self,
        context: RunContext,
        *,
        firecrawl_group_limits: Mapping[str, int] | None = None,
    ) -> None:
        self._item_limit = max(0, int(context.max_acquisition_attempts))
        self._daily_limit = max(0, int(context.firecrawl_daily_limit))
        self._group_limits = {
            str(key): max(0, int(value))
            for key, value in (firecrawl_group_limits or {}).items()
        }
        self._started_items: set[str] = set()
        self._firecrawl_reserved = 0
        self._group_reserved: dict[str, int] = {}
        self._lock = Lock()

    def _snapshot_unlocked(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            acquisition_items_started=len(self._started_items),
            acquisition_item_limit=self._item_limit,
            firecrawl_requests_reserved=self._firecrawl_reserved,
            firecrawl_daily_limit=self._daily_limit,
            firecrawl_group_reserved=self._group_reserved,
            firecrawl_group_limits=self._group_limits,
        )

    async def snapshot(self) -> BudgetSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    async def reserve_item(self, item_id: str) -> BudgetDecision:
        with self._lock:
            before = self._snapshot_unlocked()
            if item_id in self._started_items:
                return BudgetDecision(True, "item_already_reserved", before, before)
            if len(self._started_items) >= self._item_limit:
                return BudgetDecision(False, "acquisition_item_cap_exhausted", before, before)
            self._started_items.add(item_id)
            after = self._snapshot_unlocked()
            return BudgetDecision(True, "acquisition_item_reserved", before, after)

    async def reserve_firecrawl(self, group_id: str) -> BudgetDecision:
        group = str(group_id or "unknown")
        with self._lock:
            before = self._snapshot_unlocked()
            if self._firecrawl_reserved >= self._daily_limit:
                return BudgetDecision(False, "skipped_daily_cap", before, before)
            group_limit = self._group_limits.get(group)
            group_used = self._group_reserved.get(group, 0)
            if group_limit is not None and group_used >= group_limit:
                return BudgetDecision(False, "skipped_group_cap", before, before)
            self._firecrawl_reserved += 1
            self._group_reserved[group] = group_used + 1
            after = self._snapshot_unlocked()
            return BudgetDecision(True, "firecrawl_request_reserved", before, after)


__all__ = [
    "BUDGET_LEDGER_VERSION",
    "BudgetDecision",
    "BudgetLedger",
    "BudgetSnapshot",
]
