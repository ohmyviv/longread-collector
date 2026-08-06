"""Final-projection interface for legacy compatibility.

A concrete projector is intentionally deferred until the v0.6 policy contract
is implemented. PR-0 must not write legacy terminal state.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import (
    CanonicalArticle,
    EditorialAssessment,
    FinalProjection,
    SelectionDecision,
)


class FinalProjectorPort(Protocol):
    def project(
        self,
        article: CanonicalArticle,
        assessment: EditorialAssessment,
        decision: SelectionDecision,
    ) -> FinalProjection: ...


__all__ = ["FinalProjectorPort"]
