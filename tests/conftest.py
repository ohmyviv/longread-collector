from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from longread_collector.freshness_policy_v056 import (
    begin_freshness_clock,
    end_freshness_clock,
)

BJ = ZoneInfo("Asia/Shanghai")
LEGACY_FRESHNESS_REFERENCE = datetime(2026, 8, 2, 12, 0, tzinfo=BJ)

# These modules use synthetic 2026-08-01/02 fixtures to test page gates,
# reserve allocation, ranking, and offline replay semantics. Their assertions
# are about those policies at the fixture's historical reference point, not
# about wall-clock time at the day pytest happens to run.
LEGACY_FRESHNESS_ANCHORED_MODULES = {
    "test_offline_replay_v056.py",
    "test_offline_replay_v056g.py",
    "test_page_gate_policy_v056.py",
    "test_page_gates_v056.py",
    "test_ranking_policy_v056g.py",
    "test_reserve_only_v056f.py",
    "test_selection_reserve_v056.py",
    "test_staged_reserve_v056.py",
}


@pytest.fixture(autouse=True)
def freeze_legacy_freshness_clock(request):
    """Keep historical synthetic freshness fixtures deterministic over time."""
    if request.node.path.name not in LEGACY_FRESHNESS_ANCHORED_MODULES:
        yield
        return

    token = begin_freshness_clock(LEGACY_FRESHNESS_REFERENCE)
    try:
        yield
    finally:
        end_freshness_clock(token)
