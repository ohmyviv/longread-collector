import json
from dataclasses import replace
from pathlib import Path

from longread_collector.v06.contracts import (
    AcquisitionBundle,
    AssetClass,
    CanonicalArticle,
    ContentMedium,
    EditorialGenre,
    EditorialVerdict,
    PageSurface,
    PolicyAction,
    RunContext,
    SelectionTrack,
    SourceAction,
    SourceRelationship,
    StageName,
    TechnicalStatus,
)
from longread_collector.v06.editorial import EditorialJudge
from longread_collector.v06.manifest import DEFAULT_V06_MANIFEST
from longread_collector.v06.selection import (
    AcquisitionForecast,
    PolicyPortfolioSelector,
    SelectionCandidate,
    ShadowAcquisitionPlanner,
    legacy_static_plan,
)

EDITORIAL_FIXTURE = Path(__file__).parent / "fixtures" / "v06_editorial_human_labels.json"
POLICY_FIXTURE = Path(__file__).parent / "fixtures" / "v06_policy_portfolio_replay.json"


def _context() -> RunContext:
    return RunContext(
        schema_version="v06-contracts-v1",
        run_id="COL-20260806-195235-BJT-zh_evening",
        group_id="zh_evening",
        scheduled_at_bj="2026-08-06 17:50:00",
        started_at_bj="2026-08-06 19:52:35",
        collector_version="collector-v0.5.6m",
    )


def _load_cases():
    editorial = {
        item["id"]: item
        for item in json.loads(EDITORIAL_FIXTURE.read_text(encoding="utf-8"))
    }
    policy = json.loads(POLICY_FIXTURE.read_text(encoding="utf-8"))
    return editorial, policy


def _objects(case):
    source_action = SourceAction.NONE
    relationship = SourceRelationship.ORIGINAL
    if case["id"] == "pbc_primary":
        source_action = SourceAction.FIND_PRIMARY_DOCUMENT
        relationship = SourceRelationship.SECONDARY_REPUBLISH
    elif case["id"] == "external_people_shell":
        source_action = SourceAction.REPLACE_WITH_ORIGINAL
        relationship = SourceRelationship.SECONDARY_REPUBLISH

    source_name = {
        "hello_world_ceuta": "报导者",
        "turnintl_analysis": "转角国际",
        "turnintl_interview": "转角国际",
        "book_review": "端传媒",
        "legal_commentary": "法治日报",
        "pbc_primary": "中国人民银行",
        "academic_paper": "学术期刊",
        "ideological_commentary": "理论网",
        "cctv_transcript": "央视网",
        "shanghai_bookfair_event": "解放日报",
        "training_event": "无锡日报",
        "promotional_article": "文化宣传",
        "straight_news_brief": "新华社",
        "market_data_card": "市场数据",
        "external_people_shell": "人民日报",
    }.get(case["id"], case["id"])

    article = CanonicalArticle(
        schema_version="v06-contracts-v1",
        stage_version="canonical-article-resolver-v0.6-pr2",
        run_id=_context().run_id,
        item_id=case["id"],
        content_id=f"content-{case['id']}",
        display_url=f"https://fixture.invalid/{case['id']}",
        canonical_content_url=f"https://fixture.invalid/{case['id']}",
        resolved_title=case["title"],
        published_at=case["published_at"],
        published_at_confidence=0.96,
        publisher=source_name,
        hosting_source=source_name,
        canonical_source=source_name,
        source_relationship=relationship,
        source_action=source_action,
        page_surface=PageSurface(case["page_surface"]),
        main_content_medium=ContentMedium(case["medium"]),
        editorial_genre=EditorialGenre(case["genre"]),
        asset_class=AssetClass(case["asset_class"]),
        freshness_facts={"policy_applied": False},
        confidence_by_field={
            "title": 0.95,
            "publication": 0.96,
            "source": 0.92,
            "page_surface": 0.94,
            "main_content_medium": 0.94,
            "editorial_genre": 0.88,
        },
    )
    sufficient = case.get("sufficient_for_editorial_judgment", True)
    bundle = AcquisitionBundle(
        schema_version="v06-contracts-v1",
        stage_version="legacy-adapter-v0.6-pr1",
        run_id=_context().run_id,
        item_id=case["id"],
        status=TechnicalStatus.SUCCESS,
        body_text=case["body"],
        body_markdown=case["body"],
        raw_title=case["title"],
        raw_dates=(case["published_at"],),
        content_length=case["content_chars"],
        prose_length=case["prose_chars"],
        template_length=case["template_chars"],
        video_count=case["video_count"],
        sufficient_for_canonicalization=True,
        sufficient_for_editorial_judgment=sufficient,
        sufficient_for_source_chase=not sufficient or source_action is not SourceAction.NONE,
    )
    assessment = EditorialJudge().assess(_context(), article, bundle)
    return article, bundle, assessment


def _replay_result(max_selected=10):
    editorial, policy = _load_cases()
    candidates = []
    for row in policy:
        article, _, assessment = _objects(editorial[row["id"]])
        candidates.append(SelectionCandidate(article=article, assessment=assessment))
    return (
        PolicyPortfolioSelector().select(
            _context(),
            candidates,
            max_selected=max_selected,
        ),
        policy,
    )


def test_fixed_human_replay_policy_actions_match_expected():
    result, policy = _replay_result()
    decisions = {decision.item_id: decision for decision in result.decisions}
    for row in policy:
        decision = decisions[row["id"]]
        assert decision.policy_action is PolicyAction(row["expected_action"]), row["id"]
        assert decision.selection_track is SelectionTrack(row["expected_track"]), row["id"]

    assert set(result.source_chase_item_ids) == {"pbc_primary", "external_people_shell"}


def test_pr4_development_replay_reduces_legacy_action_regret_by_at_least_80_percent():
    result, policy = _replay_result()
    decisions = {decision.item_id: decision for decision in result.decisions}
    legacy_regret = sum(
        float(row["human_weight"])
        for row in policy
        if row["legacy_action"] != row["expected_action"]
    )
    pr4_regret = sum(
        float(row["human_weight"])
        for row in policy
        if decisions[row["id"]].policy_action.value != row["expected_action"]
    )
    assert legacy_regret > 0
    reduction = 1.0 - (pr4_regret / legacy_regret)
    assert reduction >= 0.80


def test_serious_false_accepts_are_policy_rejected_not_selected():
    result, policy = _replay_result()
    decisions = {decision.item_id: decision for decision in result.decisions}
    serious = [row for row in policy if row.get("serious_false_accept")]
    assert serious
    for row in serious:
        decision = decisions[row["id"]]
        assert decision.policy_action is PolicyAction.REJECT
        assert decision.selected is False


def test_low_editorial_value_becomes_final_reject_only_in_policy_layer():
    editorial, _ = _load_cases()
    case = editorial["ideological_commentary"]
    article, _, assessment = _objects(case)
    assert assessment.verdict is EditorialVerdict.LOW_VALUE
    result = PolicyPortfolioSelector().select(
        _context(),
        [SelectionCandidate(article=article, assessment=assessment)],
        max_selected=1,
    )
    decision = result.decisions[0]
    assert decision.policy_action is PolicyAction.REJECT
    assert decision.reason_code == "low_editorial_value_policy_reject"


def test_intrinsic_transcript_reject_takes_precedence_over_source_chase():
    editorial, _ = _load_cases()
    case = editorial["cctv_transcript"]
    article, _, assessment = _objects(case)
    article = replace(article, source_action=SourceAction.REPLACE_WITH_ORIGINAL)
    result = PolicyPortfolioSelector().select(
        _context(),
        [SelectionCandidate(article=article, assessment=assessment)],
        max_selected=1,
    )
    assert result.decisions[0].policy_action is PolicyAction.REJECT
    assert result.source_chase_item_ids == ()


def test_original_primary_document_uses_special_document_track():
    editorial, _ = _load_cases()
    case = editorial["pbc_primary"]
    article, _, assessment = _objects(case)
    article = replace(
        article,
        source_action=SourceAction.NONE,
        source_relationship=SourceRelationship.ORIGINAL,
    )
    result = PolicyPortfolioSelector().select(
        _context(),
        [SelectionCandidate(article=article, assessment=assessment)],
        max_selected=1,
    )
    decision = result.decisions[0]
    assert decision.policy_action is PolicyAction.SELECT_SPECIAL
    assert decision.selection_track is SelectionTrack.SPECIAL_DOCUMENT
    assert decision.selected is True


def test_academic_material_uses_academic_track_despite_lower_timeliness():
    editorial, _ = _load_cases()
    article, _, assessment = _objects(editorial["academic_paper"])
    assert assessment.timeliness_relevance_score < 0.50
    result = PolicyPortfolioSelector().select(
        _context(),
        [SelectionCandidate(article=article, assessment=assessment)],
        max_selected=1,
    )
    decision = result.decisions[0]
    assert decision.policy_action is PolicyAction.SELECT_SPECIAL
    assert decision.selection_track is SelectionTrack.ACADEMIC
    assert decision.selected is True


def test_capacity_loss_is_defer_not_content_reject():
    editorial, _ = _load_cases()
    ids = ["hello_world_ceuta", "turnintl_analysis", "turnintl_interview"]
    candidates = []
    for item_id in ids:
        article, _, assessment = _objects(editorial[item_id])
        candidates.append(SelectionCandidate(article=article, assessment=assessment))
    result = PolicyPortfolioSelector().select(
        _context(),
        candidates,
        max_selected=1,
    )
    deferred = [decision for decision in result.decisions if not decision.selected]
    assert len(deferred) == 2
    assert all(decision.policy_action is PolicyAction.DEFER for decision in deferred)
    assert all(decision.reason_code == "portfolio_capacity" for decision in deferred)


def test_duplicate_cluster_is_not_selected_twice():
    editorial, _ = _load_cases()
    article_a, _, assessment_a = _objects(editorial["hello_world_ceuta"])
    article_b, _, assessment_b = _objects(editorial["turnintl_analysis"])
    article_a = replace(article_a, duplicate_cluster_id="dup-1")
    article_b = replace(article_b, duplicate_cluster_id="dup-1")
    result = PolicyPortfolioSelector().select(
        _context(),
        [
            SelectionCandidate(article=article_a, assessment=assessment_a),
            SelectionCandidate(article=article_b, assessment=assessment_b),
        ],
        max_selected=2,
    )
    assert len(result.selected_item_ids) == 1
    deferred = next(decision for decision in result.decisions if not decision.selected)
    assert deferred.policy_action is PolicyAction.DEFER
    assert deferred.reason_code == "duplicate_cluster_already_selected"


def test_selection_evidence_is_owned_by_selection_stage():
    editorial, _ = _load_cases()
    article, _, assessment = _objects(editorial["hello_world_ceuta"])
    result = PolicyPortfolioSelector().select(
        _context(),
        [SelectionCandidate(article=article, assessment=assessment)],
        max_selected=1,
    )
    decision = result.decisions[0]
    fields = {evidence.field for evidence in decision.evidence}
    assert {
        "policy_action",
        "selection_track",
        "marginal_utility",
        "risk_penalty",
        "diversity_penalty",
        "freshness_penalty",
        "cost_penalty",
    } <= fields
    assert all(evidence.source_stage is StageName.SELECTION for evidence in decision.evidence)


def test_shadow_planner_respects_24_plus_4_plus_4_and_excludes_hard_rejects():
    forecasts = []
    for index in range(30):
        forecasts.append(
            AcquisitionForecast(
                item_id=f"core-{index:02d}",
                expected_editorial_utility=0.90 - index * 0.005,
                confidence=0.90,
                source_group=f"source-{index % 6}",
                stratum="core",
                legacy_priority=100 - index,
            )
        )
    for index in range(10):
        forecasts.append(
            AcquisitionForecast(
                item_id=f"longtail-{index:02d}",
                expected_editorial_utility=0.58,
                confidence=0.30,
                source_group=f"longtail-source-{index}",
                stratum="longtail",
                legacy_priority=5 - index * 0.1,
            )
        )
    forecasts.append(
        AcquisitionForecast(
            item_id="hard-reject",
            expected_editorial_utility=1.0,
            confidence=1.0,
            legacy_priority=1000,
            deterministic_reject=True,
        )
    )

    plan = ShadowAcquisitionPlanner().plan(forecasts)
    assert len(plan.exploit_ids) == 24
    assert len(plan.replacement_ids) == 4
    assert len(plan.exploration_ids) == 4
    assert plan.attempt_count == 32
    assert len(set(plan.ordered_ids)) == 32
    assert "hard-reject" not in plan.ordered_ids
    assert any(item_id.startswith("longtail-") for item_id in plan.exploration_ids)


def test_legacy_comparator_is_static_24_plus_8():
    forecasts = [
        AcquisitionForecast(
            item_id=f"item-{index:02d}",
            expected_editorial_utility=0.5,
            confidence=0.5,
            legacy_priority=100 - index,
        )
        for index in range(40)
    ]
    plan = legacy_static_plan(forecasts)
    assert len(plan.exploit_ids) == 24
    assert len(plan.replacement_ids) == 8
    assert plan.exploration_ids == ()
    assert plan.attempt_count == 32


def test_shadow_24_plus_4_plus_4_reduces_counterfactual_regret_vs_legacy():
    forecasts = []
    human_value = {}

    for index in range(28):
        item_id = f"strong-{index:02d}"
        forecasts.append(
            AcquisitionForecast(
                item_id=item_id,
                expected_editorial_utility=0.90,
                confidence=0.90,
                source_group=f"source-{index % 7}",
                stratum="core",
                legacy_priority=0.95,
            )
        )
        human_value[item_id] = 1.0

    for index in range(4):
        item_id = f"hidden-strong-{index:02d}"
        forecasts.append(
            AcquisitionForecast(
                item_id=item_id,
                expected_editorial_utility=0.65,
                confidence=0.25,
                source_group=f"hidden-source-{index}",
                stratum="underexplored",
                legacy_priority=0.10,
            )
        )
        human_value[item_id] = 1.0

    for index in range(8):
        item_id = f"legacy-trap-{index:02d}"
        forecasts.append(
            AcquisitionForecast(
                item_id=item_id,
                expected_editorial_utility=0.12,
                confidence=0.95,
                source_group="template-source",
                stratum="template",
                legacy_priority=0.80,
            )
        )
        human_value[item_id] = 0.0

    new_plan = ShadowAcquisitionPlanner().plan(forecasts)
    legacy_plan = legacy_static_plan(forecasts)

    optimal_value = 32.0
    new_value = sum(human_value[item_id] for item_id in new_plan.ordered_ids)
    legacy_value = sum(human_value[item_id] for item_id in legacy_plan.ordered_ids)
    new_regret = optimal_value - new_value
    legacy_regret = optimal_value - legacy_value

    assert legacy_regret > 0
    reduction = 1.0 - (new_regret / legacy_regret)
    assert reduction >= 0.80


def test_manifest_advances_only_architecture_phase():
    assert DEFAULT_V06_MANIFEST.architecture_version == "collector-v0.6-pr4"
    assert DEFAULT_V06_MANIFEST.migration_phase == "pr4_policy_portfolio"
    assert DEFAULT_V06_MANIFEST.production_behavior_changed is False
    assert DEFAULT_V06_MANIFEST.active_entrypoint_changed is False
    assert DEFAULT_V06_MANIFEST.runtime_config_integrated is False
    assert DEFAULT_V06_MANIFEST.network_requests_added is False
    assert DEFAULT_V06_MANIFEST.primary_cache_enabled is False
    assert DEFAULT_V06_MANIFEST.editor_0735_connected is False
    assert DEFAULT_V06_MANIFEST.auto_promote_when_ready is False
