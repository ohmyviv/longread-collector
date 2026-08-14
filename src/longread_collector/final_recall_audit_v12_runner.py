"""Run recall audit v1.2 with production matching and snapshot-integrity guards."""

from __future__ import annotations

from datetime import datetime

from . import final_recall_audit_v11 as audit_v11
from . import final_recall_audit_v12 as audit_v12
from .registry_matching_v056 import match_registry

# Freeze the unpatched helper before main() installs the production guard. This
# avoids recursive self-calls if main() is invoked after module import.
_BASE_OBSERVATION_COVERAGE_STATUS = audit_v12._observation_coverage_status

# Phase 0A's first naturally accepted run is the earliest point at which the
# project has positive evidence for durable full-snapshot persistence/readback.
# Older immutable snapshot rows remain useful diagnostic history, but they must
# not be promoted into the strict headline recall denominator merely because
# they exist in the Sheet.
PHASE0A_STRICT_SNAPSHOT_START_BJ = datetime(2026, 8, 13, 18, 47, 10)


def phase0a_guarded_observation_coverage_status(
    observation_start: datetime,
    snapshot_coverage_start: datetime | None,
    cutoff: datetime,
    validity: str,
) -> str:
    base_status = _BASE_OBSERVATION_COVERAGE_STATUS(
        observation_start,
        snapshot_coverage_start,
        cutoff,
        validity,
    )
    if base_status != "full":
        return base_status
    accepted_start = PHASE0A_STRICT_SNAPSHOT_START_BJ.replace(
        tzinfo=observation_start.tzinfo
    )
    if observation_start < accepted_start:
        return "partial"
    return "full"


def main() -> None:
    # v1.2 reuses v1.1 source-coverage classification. Patch the owning module
    # global so registrable-domain aliases behave exactly like the production
    # v1.1 runner rather than silently narrowing source matching.
    audit_v11._match_registry = match_registry

    # Keep raw pre-Phase0A snapshots available for diagnostic matching, while
    # requiring the naturally accepted snapshot-integrity epoch for the strict
    # KPI. v1.2 calls this module-global helper at evaluation time.
    audit_v12._observation_coverage_status = (
        phase0a_guarded_observation_coverage_status
    )
    audit_v12.main()


if __name__ == "__main__":
    main()
