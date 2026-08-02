"""v0.5.6 PR-C: publication evidence and general page gates."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime
from pathlib import Path
from typing import Any

from . import pipeline_v056b as _pipeline_v056b
from .extraction import FallbackBudget
from .freshness_policy_v056 import (
    FRESHNESS_POLICY_VERSION,
    begin_freshness_clock,
    current_freshness_time,
    end_freshness_clock,
)
from .freshness_v056 import FRESHNESS_VERSION
from .models import DiscoveredURL, ExtractedArticle
from .page_gate_policy_v056 import PAGE_GATE_POLICY_VERSION
from .page_gates_v056 import PAGE_GATE_VERSION
from .pipeline_v056b import NativeCollectorPipeline as _BasePipeline
from .post_extraction_gates_v056 import (
    POST_EXTRACTION_GATE_VERSION,
    apply_post_extraction_gates,
)
from .prefilter_v056c import PREFILTER_VERSION, filter_discovered
from .ranked_freshness_v056 import RANKING_FRESHNESS_VERSION

# Keep PR-B snapshot/reserve instrumentation while replacing only its core
# page/freshness filtering function.
_pipeline_v056b._core_filter = filter_discovered

_PR_C_MARKER = (
    f"prefilter_version={PREFILTER_VERSION}; "
    f"page_gate_version={PAGE_GATE_VERSION}; "
    f"page_gate_policy_version={PAGE_GATE_POLICY_VERSION}; "
    f"freshness_evidence_version={FRESHNESS_VERSION}; "
    f"freshness_policy_version={FRESHNESS_POLICY_VERSION}; "
    f"ranking_freshness_version={RANKING_FRESHNESS_VERSION}; "
    f"post_extraction_gate_version={POST_EXTRACTION_GATE_VERSION}"
)
if _PR_C_MARKER not in _pipeline_v056b._SELECTION_MARKER:
    _pipeline_v056b._SELECTION_MARKER = (
        f"{_pipeline_v056b._SELECTION_MARKER}; {_PR_C_MARKER}"
    )

_POST_GATE_AUDIT: ContextVar[dict[str, int] | None] = ContextVar(
    "post_gate_audit_v056c", default=None
)


def begin_post_gate_audit() -> Token:
    return _POST_GATE_AUDIT.set(
        {
            "articles_checked": 0,
            "page_rejected": 0,
            "freshness_rejected": 0,
            "failed_extraction_skipped": 0,
        }
    )


def current_post_gate_audit() -> dict[str, int]:
    return dict(_POST_GATE_AUDIT.get() or {})


def end_post_gate_audit(token: Token) -> None:
    _POST_GATE_AUDIT.reset(token)


class NativeCollectorPipeline(_BasePipeline):
    """Run PR-A and PR-B with PR-C page/date policy in shadow mode."""

    async def _extract_batch(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        articles = await super()._extract_batch(discovered, fallback_budget)
        audit = _POST_GATE_AUDIT.get()
        now = current_freshness_time()
        for item, article in zip(discovered, articles, strict=True):
            result = apply_post_extraction_gates(item, article, now=now)
            if audit is not None:
                audit["articles_checked"] += 1
                audit["page_rejected"] += int(result["page_rejected"])
                audit["freshness_rejected"] += int(result["freshness_rejected"])
                audit["failed_extraction_skipped"] += int(
                    result["skipped_for_failed_extraction"]
                )
        return articles

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        started = datetime.now(self.tz)
        freshness_token = begin_freshness_clock(started)
        audit_token = begin_post_gate_audit()
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            result.update(
                {
                    "prefilter_version": PREFILTER_VERSION,
                    "page_gate_version": PAGE_GATE_VERSION,
                    "page_gate_policy_version": PAGE_GATE_POLICY_VERSION,
                    "freshness_evidence_version": FRESHNESS_VERSION,
                    "freshness_policy_version": FRESHNESS_POLICY_VERSION,
                    "ranking_freshness_version": RANKING_FRESHNESS_VERSION,
                    "post_extraction_gate_version": POST_EXTRACTION_GATE_VERSION,
                    "post_gate_audit": current_post_gate_audit(),
                }
            )
            return result
        finally:
            end_post_gate_audit(audit_token)
            end_freshness_clock(freshness_token)


__all__ = [
    "NativeCollectorPipeline",
    "begin_post_gate_audit",
    "current_post_gate_audit",
    "end_post_gate_audit",
]
