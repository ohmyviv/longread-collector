"""Explicit context injected into the v0.6 Acquisition Gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class GateContext:
    """Facts/policy inputs that the gate may use without external I/O."""

    now_bj: datetime
    ordinary_max_age_days: int = 14
    known_duplicate_urls: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.ordinary_max_age_days < 0:
            raise ValueError("ordinary_max_age_days must be non-negative")
        object.__setattr__(
            self,
            "known_duplicate_urls",
            frozenset(str(value or "").strip() for value in self.known_duplicate_urls if value),
        )


__all__ = ["GateContext"]
