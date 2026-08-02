"""v0.5.6 PR-C: publication evidence, freshness policy and general page gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import pipeline_v056b as _base
from .freshness_v056 import FRESHNESS_VERSION
from .page_gates_v056 import PAGE_GATE_VERSION
from .prefilter_v056 import PREFILTER_VERSION
from .ranked_selection_v056c import SELECTION_VERSION

_base.PREFILTER_VERSION = PREFILTER_VERSION
_base.SELECTION_VERSION = SELECTION_VERSION
_base._SELECTION_MARKER = (
    f"prefilter_version={PREFILTER_VERSION}; "
    f"page_gate_version={PAGE_GATE_VERSION}; "
    f"freshness_version={FRESHNESS_VERSION}; "
    f"selection_version={SELECTION_VERSION}; "
    f"native_bucket_target={_base.NATIVE_BUCKET_TARGET}; "
    f"open_bucket_target={_base.OPEN_BUCKET_TARGET}; "
    f"native_source_cap={_base.NATIVE_SOURCE_CAP}; "
    f"open_domain_cap={_base.OPEN_DOMAIN_CAP}; "
    f"absolute_host_cap={_base.ABSOLUTE_HOST_CAP}; "
    "capacity_semantics=reserve_not_page_reject; "
    f"reserve_stage_slots={_base.RESERVE_STAGE_SLOTS}; "
    "extraction_attempt_cap=32; post_extraction_retry=staged_within_cap; "
    "freshness_tracks=ordinary_7d|deep_read_8_14d|special_document|ordinary_unknown; "
    "classification_version=collector-v0.5.5"
)


class NativeCollectorPipeline(_base.NativeCollectorPipeline):
    """Run PR-B reserve extraction with PR-C page and freshness gates."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        result = await super().collect(group_id=group_id, query_file=query_file)
        result["prefilter_version"] = PREFILTER_VERSION
        result["page_gate_version"] = PAGE_GATE_VERSION
        result["freshness_version"] = FRESHNESS_VERSION
        result["selection_version"] = SELECTION_VERSION
        return result


__all__ = ["NativeCollectorPipeline"]
