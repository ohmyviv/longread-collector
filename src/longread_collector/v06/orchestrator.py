"""Protocol-only v0.6 orchestrator skeleton.

PR-0 intentionally contains no executable collector integration.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    AcquisitionBundle,
    CanonicalArticle,
    DiscoveryRecord,
    EditorialAssessment,
    GateDecision,
    RunContext,
    SelectionDecision,
)


class DiscoveryPort(Protocol):
    async def discover(self, context: RunContext) -> tuple[DiscoveryRecord, ...]: ...


class AcquisitionGatePort(Protocol):
    def decide(
        self,
        context: RunContext,
        record: DiscoveryRecord,
    ) -> GateDecision: ...


class AcquisitionPort(Protocol):
    async def acquire(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        decision: GateDecision,
    ) -> AcquisitionBundle: ...


class CanonicalizerPort(Protocol):
    def canonicalize(
        self,
        context: RunContext,
        record: DiscoveryRecord,
        bundle: AcquisitionBundle,
    ) -> CanonicalArticle: ...


class EditorialJudgePort(Protocol):
    def assess(
        self,
        context: RunContext,
        article: CanonicalArticle,
    ) -> EditorialAssessment: ...


class PortfolioSelectorPort(Protocol):
    def select(
        self,
        context: RunContext,
        articles: tuple[CanonicalArticle, ...],
        assessments: tuple[EditorialAssessment, ...],
    ) -> tuple[SelectionDecision, ...]: ...


__all__ = [
    "AcquisitionGatePort",
    "AcquisitionPort",
    "CanonicalizerPort",
    "DiscoveryPort",
    "EditorialJudgePort",
    "PortfolioSelectorPort",
]
