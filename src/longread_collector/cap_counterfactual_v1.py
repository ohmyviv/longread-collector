"""Offline source-cap counterfactual helpers.

This module is diagnostic only.  It does not change ranked selection constants or
runtime allocation.  Its main purpose is to make the interaction between the
native source cap and the independent absolute host cap explicit.
"""
from __future__ import annotations

from dataclasses import dataclass

COUNTERFACTUAL_VERSION = "source-cap-counterfactual-v1"


@dataclass(frozen=True, slots=True)
class CapReplayCase:
    collector_run_id: str
    source_id: str
    title: str
    source_rank: int
    editorial_priority: int
    baseline_initial_selected: int


def effective_single_host_cap(*, native_source_cap: int, absolute_host_cap: int) -> int:
    """Maximum simultaneous capacity for a native source living on one host."""
    return min(max(0, int(native_source_cap)), max(0, int(absolute_host_cap)))


# Frozen from the 2026-08-19 / 21 / 23 zh_midday snapshots.  These are the
# three Chinese Final items that were discovered but blocked before extraction.
FROZEN_CASES: tuple[CapReplayCase, ...] = (
    CapReplayCase(
        "COL-20260819-122210-BJT-zh_midday",
        "eeo",
        "东航率先松绑“退改签” 其他航司会跟进吗",
        17,
        73,
        22,
    ),
    CapReplayCase(
        "COL-20260821-122427-BJT-zh_midday",
        "yicai",
        "地平线借道博世，智驾芯片落地欧洲16国",
        17,
        45,
        19,
    ),
    CapReplayCase(
        "COL-20260823-122354-BJT-zh_midday",
        "eeo",
        "海外收入减少11%，泡泡玛特王宁：2026是调",
        13,
        73,
        23,
    ),
)


def cap_only_recovery_ceiling(
    *,
    source_caps: tuple[int, ...] = (4, 6, 8),
    absolute_host_cap: int = 4,
) -> dict[int, int]:
    """Return the known-good recovery ceiling for a source-cap-only change.

    With a single-host native source and the host cap fixed at four, raising the
    source cap above four cannot increase capacity.  The frozen cases therefore
    remain unrecovered under 4/6/8 unless another constraint or the ranking
    policy changes too.
    """
    result: dict[int, int] = {}
    baseline_effective = effective_single_host_cap(
        native_source_cap=4, absolute_host_cap=absolute_host_cap
    )
    for cap in source_caps:
        effective = effective_single_host_cap(
            native_source_cap=cap, absolute_host_cap=absolute_host_cap
        )
        result[cap] = 0 if effective == baseline_effective else -1
    return result


__all__ = [
    "COUNTERFACTUAL_VERSION",
    "FROZEN_CASES",
    "CapReplayCase",
    "cap_only_recovery_ceiling",
    "effective_single_host_cap",
]
