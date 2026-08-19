"""v0.5.6m release entrypoint for the zh-midday natural-holdout fixes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import classification as _classification
from . import pipeline_v051 as _pipeline_v051
from . import pipeline_v056b as _pipeline_v056b
from . import pipeline_v056d as _pipeline_v056d
from . import quality as _quality
from .classification_v056m import (
    CLASSIFICATION_VERSION,
    classify_candidate_v056m,
    sanitize_author_v056l,
)
from .direct_html_v056m import DIRECT_HTML_VERSION
from .extraction_v056m import EXTRACTION_VERSION, extract_article_v056m
from .page_gate_policy_v056m import PAGE_GATE_POLICY_VERSION
from .pipeline_v056e import NativeCollectorPipeline as _BasePipeline
from .post_extraction_gates_v056m import (
    POST_EXTRACTION_GATE_VERSION,
    apply_post_extraction_gates_v056m,
)
from .prefilter_v056m import PREFILTER_VERSION, filter_discovered_v056m
from .publication_date_v056m import (
    BODY_DATE_VERSION,
    extract_body_publication_date_v056m,
)
from .section_publication_time_v056 import (
    SECTION_PUBLICATION_TIME_VERSION,
    install_section_publication_time_observability,
)
from .staged_reserve_v056m import (
    STAGED_RESERVE_VERSION,
    build_second_stage_v056m,
    split_first_stage,
)

FINAL_CALIBRATION_VERSION = "shadow-quality-final-v0.5.6m"

# The wrapper chain established by v0.5.3-v0.5.6e remains intact. Replace only
# its innermost extraction implementation so source resolution, precise budget
# errors and operational request counters continue to run unchanged.
_pipeline_v051._ORIGINAL_EXTRACT_ARTICLE = extract_article_v056m

# v0.5.6b resolves these module globals at runtime.
_pipeline_v056b._core_filter = filter_discovered_v056m
_pipeline_v056b.split_first_stage = split_first_stage
_pipeline_v056b.build_second_stage = build_second_stage_v056m

# Observe list-page publication clocks only in dedicated telemetry metadata.
# The observer deliberately does not populate DiscoveredURL.published_at, so
# freshness selection and ranking semantics remain unchanged.
install_section_publication_time_observability()

# v0.5.6d's inherited methods also resolve module globals at runtime. Point the
# final classification/date/terminal projection to the v0.5.6m implementations.
_pipeline_v056d.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_pipeline_v056d.FINAL_CALIBRATION_VERSION = FINAL_CALIBRATION_VERSION
_pipeline_v056d.POST_EXTRACTION_GATE_VERSION = POST_EXTRACTION_GATE_VERSION
_pipeline_v056d.classify_candidate_v056l = classify_candidate_v056m
_pipeline_v056d.sanitize_author_v056l = sanitize_author_v056l
_pipeline_v056d.apply_post_extraction_gates_v056l = (
    apply_post_extraction_gates_v056m
)
_pipeline_v056d.extract_body_publication_date_v056l = (
    extract_body_publication_date_v056m
)

_classification.CLASSIFICATION_VERSION = CLASSIFICATION_VERSION
_classification.classify_candidate = classify_candidate_v056m
_quality.classify_candidate = classify_candidate_v056m

_RELEASE_MARKER = (
    f"classification_version={CLASSIFICATION_VERSION}; "
    f"final_calibration_version={FINAL_CALIBRATION_VERSION}; "
    f"body_date_version={BODY_DATE_VERSION}; "
    f"post_extraction_gate_version={POST_EXTRACTION_GATE_VERSION}; "
    f"prefilter_version={PREFILTER_VERSION}; "
    f"page_gate_policy_version={PAGE_GATE_POLICY_VERSION}; "
    f"staged_reserve_version={STAGED_RESERVE_VERSION}; "
    f"extraction_version={EXTRACTION_VERSION}; "
    f"direct_html_version={DIRECT_HTML_VERSION}; "
    f"section_publication_time_version={SECTION_PUBLICATION_TIME_VERSION}"
)
if _RELEASE_MARKER not in _pipeline_v056b._SELECTION_MARKER:
    _pipeline_v056b._SELECTION_MARKER = (
        f"{_pipeline_v056b._SELECTION_MARKER}; {_RELEASE_MARKER}"
    )


class NativeCollectorPipeline(_BasePipeline):
    """Run the existing operational chain with v0.5.6m terminal semantics."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        result = await super().collect(group_id=group_id, query_file=query_file)
        result.update(
            {
                "classification_version": CLASSIFICATION_VERSION,
                "final_calibration_version": FINAL_CALIBRATION_VERSION,
                "body_date_version": BODY_DATE_VERSION,
                "post_extraction_gate_version": POST_EXTRACTION_GATE_VERSION,
                "prefilter_version": PREFILTER_VERSION,
                "page_gate_policy_version": PAGE_GATE_POLICY_VERSION,
                "staged_reserve_version": STAGED_RESERVE_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "direct_html_version": DIRECT_HTML_VERSION,
                "section_publication_time_version": SECTION_PUBLICATION_TIME_VERSION,
            }
        )
        return result


__all__ = ["FINAL_CALIBRATION_VERSION", "NativeCollectorPipeline"]
