from longread_collector.full_funnel_audit_v1 import build_full_funnel_audit


def ev(item, kind, stage, attrs=None, status="success", reason="ok"):
    return {
        "event_id": f"{item}-{kind}",
        "item_id": item,
        "stage": stage,
        "event_type": kind,
        "stage_version": "fixture",
        "technical_status": status,
        "flow_status": "pass",
        "reason_code": reason,
        "parent_event_id": "",
        "cost": 0.0,
        "attributes": attrs or {},
    }


def fixture():
    events = [
        ev("a", "discovery_result", "discovery", {"url": "https://example.com/a", "canonical_url_hint": "https://example.com/a", "source_id": "wired", "discovery_method": "rss"}),
        ev("a", "gate_result", "acquisition_gate", {"gate_action": "acquire"}),
        ev("a", "acquisition_result", "acquisition"),
        ev("a", "canonical_result", "canonical", {"canonical_source": "example.com"}),
        ev("a", "editorial_result", "editorial", {"verdict": "consider"}),
        ev("a", "selection_result", "selection", {"policy_action": "select_standard", "selected": True, "selection_rank": 1}),
        ev("b", "discovery_result", "discovery", {"url": "https://example.com/b", "canonical_url_hint": "https://example.com/b", "source_id": "open_query_1", "discovery_method": "firecrawl_search"}),
        ev("b", "gate_result", "acquisition_gate", {"gate_action": "acquire"}),
        ev("b", "selection_result", "selection", {"policy_action": "defer", "selected": False}, status="partial", reason="body_not_observed_in_control"),
        ev("c", "discovery_result", "discovery", {"url": "https://example.com/c", "canonical_url_hint": "https://example.com/c", "source_id": "newyorker", "discovery_method": "rss"}),
        ev("c", "gate_result", "acquisition_gate", {"gate_action": "hard_reject"}, reason="non_article_surface"),
        ev("c", "selection_result", "selection", {"policy_action": "reject", "selected": False}, reason="gate:non_article_surface"),
    ]
    return {
        "collector_run_id": "COL-FIXTURE",
        "query_group": "pre_report",
        "queries_count": 2,
        "sources_scanned": 2,
        "discovery_snapshot_rows": 3,
        "source_selection_audit": {"selected": [{"source_id": "wired"}, {"source_id": "newyorker"}]},
        "v06_shadow": {
            "status": "success",
            "run_id": "COL-FIXTURE",
            "group_id": "pre_report",
            "pipeline_version": "collector-v0.6-pr7.3.9",
            "control_version": "collector-v0.5.6m",
            "discovery_snapshot_count": 3,
            "events": events,
            "items": [
                {"item_id": "a", "url": "https://example.com/a", "prefilter_status": "accepted_for_extraction"},
                {"item_id": "b", "url": "https://example.com/b", "prefilter_status": "not_selected_capacity"},
                {"item_id": "c", "url": "https://example.com/c", "prefilter_status": "prefilter_rejected"},
            ],
        },
    }


def test_observation_boundary_and_actionable_funnel():
    audit = build_full_funnel_audit(fixture())
    assert audit["audit_status"] == "complete"
    assert audit["coverage"]["observation_closed_item_count"] == 3
    assert audit["coverage"]["gate_pass_body_not_observed_item_count"] == 1
    assert audit["coverage"]["gate_terminal_without_body_item_count"] == 1
    funnel = audit["funnel"]
    assert funnel["attempted_discovery_surfaces"] == 4
    assert funnel["raw_discovery_observations"] == 3
    assert funnel["acquisition_success"] == 1
    assert funnel["editorial_eligible_for_decision"] == 1
    assert funnel["high_editorial_value"] == 0
    assert funnel["strong_editorial_actionable"] == 1
    assert funnel["selected"] == 1
    item_b = next(item for item in audit["items"] if item["item_id"] == "b")
    assert item_b["failure_family"] == "body_not_observed"


def test_zero_result_query_identity_gap_is_explicit():
    surfaces = build_full_funnel_audit(fixture())["surface_summary"]
    assert surfaces["open_query_attempt_count"] == 2
    assert surfaces["unattributed_open_query_attempt_count"] == 1
    assert surfaces["surface_identity_coverage_ratio"] == 0.75
    assert surfaces["surface_observability_status"] == "aggregate_only_for_zero_result_surfaces"


def test_missing_observed_body_stage_is_partial():
    payload = fixture()
    payload["v06_shadow"]["events"] = [
        event for event in payload["v06_shadow"]["events"]
        if not (event["item_id"] == "a" and event["event_type"] == "canonical_result")
    ]
    audit = build_full_funnel_audit(payload)
    assert audit["audit_status"] == "partial"
    assert audit["coverage"]["observation_incomplete_item_count"] == 1
    assert any("missing=canonical_result_after_acquisition" in error for error in audit["integrity_errors"])
