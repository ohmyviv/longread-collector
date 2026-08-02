"""Run recall audit v1.1 with registrable-domain source matching."""

from __future__ import annotations

from . import final_recall_audit_v11 as audit
from .registry_matching_v056 import match_registry


def main() -> None:
    audit._match_registry = match_registry
    audit.main()


if __name__ == "__main__":
    main()
