from __future__ import annotations

from longread_collector.zh_route_shadow_s2b_result_contract_v1 import (
    S2B_RESULT_CONTRACT_VERSION,
    validate_s2b_results,
)
from longread_collector.zh_route_shadow_s2b_sample_plan_v1 import S2BSampleItem


def _sample():
    return (
        S2BSampleItem(
            url_canonical="https://example.test/1.html",
            source_id="jiemian-depth",
            first_surface="jiemian_medicine",
            metadata_class="plausible_standard_longread",
            sampling_role="primary_plausible",
            deterministic_rank="a",
        ),
        S2BSampleItem(
            url_canonical="https://example.test/2.html",
            source_id="yicai",
            first_surface="yicai_kechuang",
            metadata_class="insufficient_evidence",
            sampling_role="uncertainty_explore",
            deterministic_rank="b",
        ),
    )


def _row(item: S2BSampleItem, **overrides):
    row = {
        "url_canonical": item.url_canonical,
        "source_id": item.source_id,
        "first_surface": item.first_surface,
        "metadata_class": item.metadata_class,
        "sampling_role": item.sampling_role,
        "acquisition_status": "usable_body",
        "body_product_class": "body_confirmed_standard_longread",
        "content_chars": 5000,
        "body_fingerprint": "sha256:abc",
        "extraction_path": "control_current",
        "network_request_count": 1,
        "firecrawl_calls": 0,
        "depth_signals": [
            "multi_source_or_substantive_interview",
            "causal_explanatory_strategic_or_mechanism_analysis",
        ],
        "non_target_reason": "",
    }
    row.update(overrides)
    return row


def test_valid_result_ledger_matches_manifest_exactly():
    sample = _sample()
    result = validate_s2b_results(sample, [_row(sample[0]), _row(sample[1])])
    assert result["version"] == S2B_RESULT_CONTRACT_VERSION
    assert result["valid"] is True
    assert result["sample_total"] == result["result_rows"] == 2
    assert result["network_requests_total"] == 2


def test_nonusable_body_must_remain_not_evaluable():
    sample = _sample()
    rows = [
        _row(
            sample[0],
            acquisition_status="acquisition_failed",
            body_product_class="body_confirmed_non_target",
            content_chars=0,
            body_fingerprint="",
            extraction_path="",
            depth_signals=[],
        ),
        _row(sample[1]),
    ]
    result = validate_s2b_results(sample, rows)
    assert result["valid"] is False
    assert any(error["error"] == "nonusable_body_must_be_not_evaluable" for error in result["errors"])


def test_confirmed_longread_requires_length_and_two_depth_signals():
    sample = _sample()
    rows = [
        _row(
            sample[0],
            content_chars=2400,
            depth_signals=["multi_source_or_substantive_interview"],
        ),
        _row(sample[1]),
    ]
    result = validate_s2b_results(sample, rows)
    assert result["valid"] is False
    errors = {error["error"] for error in result["errors"]}
    assert "confirmed_longread_too_short" in errors
    assert "confirmed_longread_needs_two_depth_signals" in errors


def test_non_target_requires_frozen_reason():
    sample = _sample()
    rows = [
        _row(
            sample[0],
            body_product_class="body_confirmed_non_target",
            non_target_reason="",
            depth_signals=[],
        ),
        _row(sample[1]),
    ]
    result = validate_s2b_results(sample, rows)
    assert result["valid"] is False
    assert any(error["error"] == "non_target_missing_or_invalid_reason" for error in result["errors"])


def test_manifest_identity_and_exact_url_coverage_are_fail_closed():
    sample = _sample()
    rows = [
        _row(sample[0], source_id="yicai"),
        _row(sample[1], url_canonical="https://example.test/unexpected.html"),
    ]
    result = validate_s2b_results(sample, rows)
    assert result["valid"] is False
    assert result["missing_urls"] == ["https://example.test/2.html"]
    assert result["unexpected_urls"] == ["https://example.test/unexpected.html"]
    assert any(error["error"] == "manifest_mismatch:source_id" for error in result["errors"])
