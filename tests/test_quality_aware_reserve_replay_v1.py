from longread_collector.quality_aware_reserve_replay_v1 import (
    FROZEN_CASES,
    adjusted_source_rank,
    frozen_replay_summary,
    opportunity_status,
    tier1_micro_market_reason,
)


def test_main_flow_and_short_horizon_stock_snapshots_are_flagged() -> None:
    assert tier1_micro_market_reason(
        "8月21日三晖电气主力资金净流入远超均值 近5日震荡持平大盘强于行业"
    )
    assert tier1_micro_market_reason(
        "8月21日万丰奥威主力净流出股价弱于大盘 估值处历史低位"
    )
    assert tier1_micro_market_reason(
        "某公司近5日震荡弱于大盘 当前估值处历史低位"
    )


def test_transactional_etf_is_flagged_but_substantive_etf_reporting_is_not() -> None:
    assert tier1_micro_market_reason(
        "创新药ETF华泰柏瑞8月21日净申购-600万份，近一年涨1.29%建议关注溢价率"
    ) == "etf_transaction_snapshot"
    assert tier1_micro_market_reason(
        "建材ETF富国规模缩水跌幅超21% 溢折率偏高处于高风险区存回落风险"
    ) == "etf_transaction_snapshot"
    assert tier1_micro_market_reason(
        "东方红、中欧新入局，ETF赛道迎来“最后的头部玩家”"
    ) == ""


def test_known_good_capacity_cases_are_never_flagged_by_tier1_detector() -> None:
    assert all(tier1_micro_market_reason(case.title) == "" for case in FROZEN_CASES)


def test_frozen_rank_replay_is_8_17_5() -> None:
    adjusted = [
        adjusted_source_rank(case.original_source_rank, case.tier1_flagged_ranks_before)
        for case in FROZEN_CASES
    ]
    assert adjusted == [8, 17, 5]
    assert adjusted == [case.expected_adjusted_rank for case in FROZEN_CASES]


def test_replay_does_not_overclaim_recovery() -> None:
    rows = frozen_replay_summary()
    assert [row["opportunity_status"] for row in rows] == [
        "still_outside_top4",
        "still_outside_top4",
        "first_same_source_reserve_candidate",
    ]
    assert opportunity_status(4) == "deterministic_top4_membership"
    assert opportunity_status(5) == "first_same_source_reserve_candidate"
    assert opportunity_status(6) == "still_outside_top4"


def test_flagged_ranks_are_unique_and_strictly_ahead_of_known_good() -> None:
    for case in FROZEN_CASES:
        assert len(set(case.tier1_flagged_ranks_before)) == len(case.tier1_flagged_ranks_before)
        assert all(0 < rank < case.original_source_rank for rank in case.tier1_flagged_ranks_before)
