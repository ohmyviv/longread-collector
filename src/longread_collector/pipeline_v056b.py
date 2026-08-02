"""v0.5.6 PR-B: reserve-aware native/open selection on top of PR-A."""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from . import pipeline_v05 as _pipeline_v05
from . import pipeline_v055 as _pipeline_v055
from .extraction import FallbackBudget
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url
from .pipeline_v056a import NativeCollectorPipeline as _BasePipeline
from .prefilter_v056 import PREFILTER_VERSION, filter_discovered as _core_filter
from .ranked_selection_v056 import (
    ABSOLUTE_HOST_CAP,
    NATIVE_BUCKET_TARGET,
    NATIVE_SOURCE_CAP,
    OPEN_BUCKET_TARGET,
    OPEN_DOMAIN_CAP,
    RESERVE_STATUSES,
    SELECTION_VERSION,
)
from .recall_instrumentation import CapturedDiscovery, current_snapshot_capture
from .selection_plan_v056 import clear_selection_plan, current_selection_plan
from .staged_reserve_v056 import (
    RESERVE_STAGE_SLOTS,
    build_second_stage,
    split_first_stage,
)


_SELECTION_AUDIT: ContextVar[dict[str, Any] | None] = ContextVar(
    "v056_selection_audit", default=None
)


def begin_selection_audit() -> Token:
    return _SELECTION_AUDIT.set(
        {
            "selection_calls": 0,
            "selected": 0,
            "selected_native": 0,
            "selected_open": 0,
            "capacity_backfill": 0,
            "reserve_counts": Counter(),
            "page_rejects": 0,
            "first_stage_attempts": 0,
            "second_stage_attempts": 0,
            "failed_first_stage": 0,
            "reserve_promotions": 0,
            "deferred_not_extracted": 0,
        }
    )


def current_selection_audit() -> dict[str, Any]:
    audit = _SELECTION_AUDIT.get() or {}
    result = dict(audit)
    if isinstance(result.get("reserve_counts"), Counter):
        result["reserve_counts"] = dict(result["reserve_counts"])
    return result


def end_selection_audit(token: Token) -> None:
    _SELECTION_AUDIT.reset(token)


def _capture_snapshot_result(
    discovered: list[Any],
    accepted: list[Any],
    rejected: list[dict[str, str]],
) -> None:
    """Capture reserve states without misclassifying them as page rejection."""
    state = current_snapshot_capture()
    if state is None:
        return

    accepted_counts: dict[str, int] = {}
    for accepted_item in accepted:
        canonical = canonicalize_url(accepted_item.url)
        accepted_counts[canonical] = accepted_counts.get(canonical, 0) + 1

    rejection_queues: dict[str, list[str]] = {}
    for rejected_item in rejected:
        canonical = canonicalize_url(str(rejected_item.get("url", "")))
        rejection_queues.setdefault(canonical, []).append(
            str(rejected_item.get("reason", ""))
        )

    for item in discovered:
        canonical = canonicalize_url(item.url)
        selection = item.metadata.get("selection", {})
        if accepted_counts.get(canonical, 0) > 0:
            accepted_counts[canonical] -= 1
            status, reason = "accepted_for_extraction", ""
        elif rejection_queues.get(canonical):
            status = "prefilter_rejected"
            reason = rejection_queues[canonical].pop(0)
        else:
            selection_status = str(selection.get("selection_status", ""))
            status = "not_selected_capacity"
            reason = (
                selection_status
                if selection_status in RESERVE_STATUSES
                else "final_not_selected"
            )
        state.discoveries.append(
            CapturedDiscovery(
                item=item,
                prefilter_status=status,
                prefilter_reject_reason=reason,
            )
        )


def _update_snapshot_status(
    item: DiscoveredURL,
    *,
    status: str,
    reason: str,
) -> None:
    state = current_snapshot_capture()
    if state is None:
        return
    canonical = canonicalize_url(item.url)
    for captured in state.discoveries:
        if canonicalize_url(captured.item.url) != canonical:
            continue
        captured.prefilter_status = status
        captured.prefilter_reject_reason = reason
        return


def filter_discovered(
    discovered: list[Any],
    *,
    max_urls: int,
    max_per_domain: int = OPEN_DOMAIN_CAP,
):
    accepted, rejected = _core_filter(
        discovered,
        max_urls=max_urls,
        max_per_domain=max_per_domain,
    )
    _capture_snapshot_result(discovered, accepted, rejected)

    audit = _SELECTION_AUDIT.get()
    if audit is not None:
        audit["selection_calls"] += 1
        audit["selected"] += len(accepted)
        audit["selected_native"] += sum(
            str(item.metadata.get("selection", {}).get("selection_bucket"))
            == "native"
            for item in accepted
        )
        audit["selected_open"] += sum(
            str(item.metadata.get("selection", {}).get("selection_bucket")) == "open"
            for item in accepted
        )
        audit["capacity_backfill"] += sum(
            bool(item.metadata.get("selection", {}).get("capacity_backfill"))
            for item in accepted
        )
        reserve_counts = audit["reserve_counts"]
        for item in discovered:
            status = str(item.metadata.get("selection", {}).get("selection_status", ""))
            if status in RESERVE_STATUSES:
                reserve_counts[status] += 1
        audit["page_rejects"] += len(rejected)
    return accepted, rejected


# Replace the previously installed v0.5.5 snapshot-wrapped filter with the
# v0.5.6 wrapper above. The article upsert hook remains installed and consumes
# the CapturedDiscovery rows appended here.
_pipeline_v05.filter_discovered = filter_discovered


_SELECTION_MARKER = (
    f"prefilter_version={PREFILTER_VERSION}; "
    f"selection_version={SELECTION_VERSION}; "
    f"native_bucket_target={NATIVE_BUCKET_TARGET}; "
    f"open_bucket_target={OPEN_BUCKET_TARGET}; "
    f"native_source_cap={NATIVE_SOURCE_CAP}; "
    f"open_domain_cap={OPEN_DOMAIN_CAP}; absolute_host_cap={ABSOLUTE_HOST_CAP}; "
    "capacity_semantics=reserve_not_page_reject; "
    f"reserve_stage_slots={RESERVE_STAGE_SLOTS}; "
    "extraction_attempt_cap=32; post_extraction_retry=staged_within_cap; "
    "source_chase_version=deterministic-v0.5.5; "
    "classification_version=collector-v0.5.5"
)


class NativeCollectorPipeline(_BasePipeline):
    """Run PR-A routes with reserve-aware staged extraction capped at 32."""

    async def _extract_batch(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        return await super()._extract_all(discovered, fallback_budget)

    async def _extract_all(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        # Source-chase extraction is already separately bounded and must not
        # consume the primary selection reserve plan.
        if self._primary_selection_extracted:
            return await self._extract_batch(discovered, fallback_budget)
        self._primary_selection_extracted = True

        plan = current_selection_plan()
        max_attempts = min(
            int(self.settings.max_urls_per_run),
            int(plan.max_urls) if plan is not None else len(discovered),
        )
        if plan is None or max_attempts <= 0:
            return await self._extract_batch(discovered, fallback_budget)

        first_stage, deferred = split_first_stage(
            discovered,
            max_attempts=max_attempts,
            reserve_slots=RESERVE_STAGE_SLOTS,
        )
        discovered[:] = first_stage
        first_articles = await self._extract_batch(first_stage, fallback_budget)
        decision = build_second_stage(
            plan=plan,
            first_stage=first_stage,
            deferred=deferred,
            first_articles=first_articles,
            max_attempts=max_attempts,
        )

        for item in decision.promoted_reserves:
            _update_snapshot_status(
                item,
                status="accepted_for_extraction",
                reason="reserve_promoted",
            )
        for item in decision.deferred_not_extracted:
            _update_snapshot_status(
                item,
                status="not_selected_capacity",
                reason="deferred_not_extracted",
            )

        discovered.extend(decision.second_stage)
        second_articles = (
            await self._extract_batch(decision.second_stage, fallback_budget)
            if decision.second_stage
            else []
        )

        audit = _SELECTION_AUDIT.get()
        if audit is not None:
            audit["first_stage_attempts"] += len(first_stage)
            audit["second_stage_attempts"] += len(decision.second_stage)
            audit["failed_first_stage"] += len(decision.failed_first_stage)
            audit["reserve_promotions"] += len(decision.promoted_reserves)
            audit["deferred_not_extracted"] += len(
                decision.deferred_not_extracted
            )
        return first_articles + second_articles

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        clear_selection_plan()
        self._primary_selection_extracted = False
        audit_token = begin_selection_audit()
        previous_append = self.store.append_collector_run

        def append_with_selection_audit(values: dict[str, Any]) -> None:
            audit = current_selection_audit()
            notes = str(values.get("notes", "") or "")
            # Remove stale v0.5.5 selection markers if an inner layer emitted one.
            stale_start = notes.find("prefilter_version=deterministic-prefilter-v0.5.5")
            if stale_start >= 0:
                notes = notes[:stale_start].rstrip("; ")
            audit_marker = (
                f"selection_calls={audit.get('selection_calls', 0)}; "
                f"selected_native={audit.get('selected_native', 0)}; "
                f"selected_open={audit.get('selected_open', 0)}; "
                f"selection_backfill={audit.get('capacity_backfill', 0)}; "
                f"selection_reserves={audit.get('reserve_counts', {})}; "
                f"selection_page_rejects={audit.get('page_rejects', 0)}; "
                f"first_stage_attempts={audit.get('first_stage_attempts', 0)}; "
                f"second_stage_attempts={audit.get('second_stage_attempts', 0)}; "
                f"failed_first_stage={audit.get('failed_first_stage', 0)}; "
                f"reserve_promotions={audit.get('reserve_promotions', 0)}; "
                f"deferred_not_extracted={audit.get('deferred_not_extracted', 0)}"
            )
            values["notes"] = (
                f"{notes}; {_SELECTION_MARKER}; {audit_marker}"
                if notes
                else f"{_SELECTION_MARKER}; {audit_marker}"
            )
            # Bypass the class-level v0.5.5 marker hook; this wrapper supplies
            # the complete v0.5.6 marker and still uses the original sheet write.
            _pipeline_v055._ORIGINAL_APPEND_COLLECTOR_RUN(self.store, values)

        self.store.append_collector_run = append_with_selection_audit
        try:
            result = await super().collect(group_id=group_id, query_file=query_file)
            audit = current_selection_audit()
            result["prefilter_version"] = PREFILTER_VERSION
            result["selection_version"] = SELECTION_VERSION
            result["selection_audit"] = audit
            result["extraction_attempt_cap"] = self.settings.max_urls_per_run
            result["post_extraction_reserve_retry"] = True
            result["reserve_stage_slots"] = RESERVE_STAGE_SLOTS
            return result
        finally:
            self.store.append_collector_run = previous_append
            end_selection_audit(audit_token)
            clear_selection_plan()


__all__ = [
    "NativeCollectorPipeline",
    "begin_selection_audit",
    "current_selection_audit",
    "end_selection_audit",
    "filter_discovered",
]
