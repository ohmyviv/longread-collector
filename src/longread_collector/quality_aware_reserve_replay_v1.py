"""Offline quality-aware reserve replay for the frozen Chinese capacity cases.

Diagnostic only.  This module does not patch production ranking.  It preserves
persisted source-local order for every non-flagged candidate and asks what would
happen if only high-precision micro-market templates were demoted below ordinary
editorial candidates before body extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

REPLAY_VERSION = "quality-aware-reserve-replay-v1"
SOURCE_CAP = 4

_MAIN_FLOW_RE = re.compile(r"(?:主力资金|主力净(?:流入|流出))", re.I)
_NEAR5_RE = re.compile(r"近\s*5\s*日", re.I)
_NEAR5_CONTEXT_RE = re.compile(r"(?:大盘|估值|主力|震荡|市盈)", re.I)
_ETF_RE = re.compile(r"\bETF\b|etf", re.I)
_ETF_TRANSACTION_RE = re.compile(
    r"(?:净申购|净赎回|申赎|溢价率?|溢折率|规模缩水|高溢价)", re.I
)


@dataclass(frozen=True, slots=True)
class FrozenCapacityCase:
    run_id: str
    source_id: str
    title: str
    original_source_rank: int
    tier1_flagged_ranks_before: tuple[int, ...]
    expected_adjusted_rank: int


def tier1_micro_market_reason(title: str) -> str:
    """Return a high-precision pre-extraction demotion reason, if any.

    The detector intentionally does *not* reject generic ETF reporting.  It is
    limited to short-horizon single-stock/ETF transaction snapshots that were
    repeatedly observed to consume extraction capacity and then fail editorial
    eligibility.
    """
    text = str(title or "").strip()
    if not text:
        return ""
    if _MAIN_FLOW_RE.search(text):
        return "single_stock_main_flow_snapshot"
    if _NEAR5_RE.search(text) and _NEAR5_CONTEXT_RE.search(text):
        return "single_stock_short_horizon_snapshot"
    if _ETF_RE.search(text) and _ETF_TRANSACTION_RE.search(text):
        return "etf_transaction_snapshot"
    return ""


def adjusted_source_rank(
    original_rank: int,
    flagged_ranks_before: tuple[int, ...] | list[int],
) -> int:
    """Rank after flagged items ahead of the candidate are moved to the tail."""
    rank = max(1, int(original_rank))
    removed_before = sum(1 for flagged in set(flagged_ranks_before) if 0 < flagged < rank)
    return max(1, rank - removed_before)


def opportunity_status(adjusted_rank: int, *, source_cap: int = SOURCE_CAP) -> str:
    """Describe source-local extraction opportunity without inventing outcomes."""
    if adjusted_rank <= source_cap:
        return "deterministic_top4_membership"
    if adjusted_rank == source_cap + 1:
        return "first_same_source_reserve_candidate"
    return "still_outside_top4"


# Ranks are frozen from persisted ``selection.source_or_domain_rank`` in the
# immutable 8/19, 8/21 and 8/23 zh_midday snapshots.  Flag sets contain only
# Tier-1 high-precision micro-market templates ahead of the known-good Final.
FROZEN_CASES: tuple[FrozenCapacityCase, ...] = (
    FrozenCapacityCase(
        "COL-20260819-122210-BJT-zh_midday",
        "eeo",
        "东航率先松绑“退改签” 其他航司会跟进吗",
        17,
        (3, 4, 5, 6, 7, 8, 9, 10, 11),
        8,
    ),
    FrozenCapacityCase(
        "COL-20260821-122427-BJT-zh_midday",
        "yicai",
        "地平线借道博世，智驾芯片落地欧洲16国",
        17,
        (),
        17,
    ),
    FrozenCapacityCase(
        "COL-20260823-122354-BJT-zh_midday",
        "eeo",
        "海外收入减少11%，泡泡玛特王宁：2026是调",
        13,
        (1, 2, 3, 4, 5, 6, 7, 9),
        5,
    ),
)


def frozen_replay_summary() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in FROZEN_CASES:
        adjusted = adjusted_source_rank(
            case.original_source_rank, case.tier1_flagged_ranks_before
        )
        rows.append(
            {
                "run_id": case.run_id,
                "source_id": case.source_id,
                "title": case.title,
                "original_source_rank": case.original_source_rank,
                "tier1_flagged_before": len(case.tier1_flagged_ranks_before),
                "adjusted_source_rank": adjusted,
                "opportunity_status": opportunity_status(adjusted),
            }
        )
    return rows


__all__ = [
    "FROZEN_CASES",
    "REPLAY_VERSION",
    "SOURCE_CAP",
    "FrozenCapacityCase",
    "adjusted_source_rank",
    "frozen_replay_summary",
    "opportunity_status",
    "tier1_micro_market_reason",
]
