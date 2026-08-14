"""Run recall audit v1.2 with registrable-domain source matching."""

from __future__ import annotations

from . import final_recall_audit_v11 as audit_v11
from . import final_recall_audit_v12 as audit_v12
from .registry_matching_v056 import match_registry


def main() -> None:
    # v1.2 reuses v1.1 source-coverage classification. Patch the owning module
    # global so registrable-domain aliases behave exactly like the production
    # v1.1 runner rather than silently narrowing source matching.
    audit_v11._match_registry = match_registry
    audit_v12.main()


if __name__ == "__main__":
    main()
