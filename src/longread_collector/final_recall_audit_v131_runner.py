"""Run Final Recall v1.3.1 with the existing v1.2 snapshot guards."""

from __future__ import annotations

from . import final_recall_audit_v11 as audit_v11
from . import final_recall_audit_v12 as audit_v12
from . import final_recall_audit_v131 as audit_v131
from .final_recall_audit_v12_runner import (
    phase0a_guarded_observation_coverage_status,
)
from .registry_matching_v056 import match_registry


def main() -> None:
    audit_v11._match_registry = match_registry
    audit_v12._observation_coverage_status = phase0a_guarded_observation_coverage_status
    audit_v131.main()


if __name__ == "__main__":
    main()
