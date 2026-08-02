"""Run the persisted Stage 3 replay with the active v0.5.6f policy."""

from __future__ import annotations

from . import freshness_policy_v056f as policy
from . import offline_replay_sheet_adapter_v056 as adapter


def main() -> None:
    adapter.replay.evaluate_freshness_policy = policy.evaluate_freshness_policy
    adapter.main()


if __name__ == "__main__":
    main()
