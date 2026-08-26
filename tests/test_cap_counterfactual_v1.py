from longread_collector.cap_counterfactual_v1 import (
    FROZEN_CASES,
    cap_only_recovery_ceiling,
    effective_single_host_cap,
)
from longread_collector.ranked_selection_v055 import ABSOLUTE_HOST_CAP, NATIVE_SOURCE_CAP


def test_current_caps_are_both_four() -> None:
    assert NATIVE_SOURCE_CAP == 4
    assert ABSOLUTE_HOST_CAP == 4


def test_source_cap_4_6_8_is_inert_while_single_host_cap_stays_four() -> None:
    assert [effective_single_host_cap(native_source_cap=c, absolute_host_cap=4) for c in (4, 6, 8)] == [4, 4, 4]
    assert cap_only_recovery_ceiling() == {4: 0, 6: 0, 8: 0}


def test_frozen_capacity_cases_are_the_three_known_chinese_finals() -> None:
    assert len(FROZEN_CASES) == 3
    assert [case.source_rank for case in FROZEN_CASES] == [17, 17, 13]
    assert [case.editorial_priority for case in FROZEN_CASES] == [73, 45, 73]
