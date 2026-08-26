from __future__ import annotations

import base64
import gzip
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from longread_collector.final_recall_audit_v131 import (
    durable_run_status,
    evaluate_product_scope,
    evaluate_publication_surface,
    evaluate_strict_measurement_item,
    resolve_publication_evidence,
    strict_coverage_ledger_start,
    strict_summary,
)

# CI synchronize marker only; no test or production logic change.
TZ = ZoneInfo("Asia/Shanghai")
FIXTURE = Path(__file__).parent / "fixtures" / "final_recall_v131_phase2_replay.json.gz.b64"


def _fixture() -> dict:
    payload = base64.b64decode(FIXTURE.read_text(encoding="ascii").strip())
    return json.loads(gzip.decompress(payload).decode("utf-8"))


def _durable_notes(*, expected: int = 10, persisted: int = 10, readback: str = "TRUE") -> str:
    return ";".join(
        [
            "source_run_coverage_version=run-source-coverage-v0.2",
            "source_run_coverage_persisted=TRUE",
            "snapshot_persistence_status=success",
            f"snapshot_expected_rows={expected}",
            f"snapshot_persisted_rows={persisted}",
            f"snapshot_readback_performed={readback}",
        ]
    )


def test_product_scope_distinguishes_nature_news_from_scholarly_assets() -> None:
    news = {"final_url": "https://www.nature.com/articles/d41586-026-02528-y"}
    paper = {"final_url": "https://www.nature.com/articles/s41591-026-04562-9"}

    assert evaluate_product_scope(news).status == "in_scope"
    paper_result = evaluate_product_scope(paper)
    assert paper_result.status == "excluded"
    assert paper_result.reason == "nature_scholarly_asset"


def test_publication_surface_is_stricter_than_registrable_domain() -> None:
    reuters = {"source_id": "reuters-special"}
    assert evaluate_publication_surface(
        {"final_url": "https://www.reuters.com/investigates/example"}, reuters
    ).status == "matched"
    assert evaluate_publication_surface(
        {"final_url": "https://www.reuters.com/commentary/example"}, reuters
    ).status == "mismatch"

    guardian = {"source_id": "guardian-longread"}
    assert evaluate_publication_surface(
        {
            "final_url": "https://www.theguardian.com/news/2026/aug/20/example",
            "matched_source": "The Guardian · The Long Read",
        },
        guardian,
    ).status == "matched"
    assert evaluate_publication_surface(
        {"final_url": "https://www.theguardian.com/environment/2026/aug/21/example"},
        guardian,
    ).status == "mismatch"


def test_durable_run_requires_terminal_success_and_complete_snapshot_readback() -> None:
    base = {
        "collector_run_id": "COL-ok",
        "completed_at_bj": "2026-08-25 04:15:02",
        "final_status": "success",
        "notes": _durable_notes(),
    }
    assert durable_run_status(base, TZ) == (True, "durable_success")

    failed = dict(base, final_status="failed")
    assert durable_run_status(failed, TZ)[0] is False

    mismatch = dict(base, notes=_durable_notes(expected=10, persisted=9))
    assert durable_run_status(mismatch, TZ)[1] == "snapshot_row_count_mismatch"

    unread = dict(base, notes=_durable_notes(readback="FALSE"))
    assert durable_run_status(unread, TZ)[1] == "snapshot_readback_not_confirmed"


def test_exact_persisted_timestamp_resolves_date_only_boundary() -> None:
    item = {
        "final_url": "https://www.ft.com/content/4a26bc38-1634-4804-81f7-11124c1e3008",
        "final_url_canonical": "https://ft.com/content/4a26bc38-1634-4804-81f7-11124c1e3008",
        "final_title": "How climate is driving new geostrategy",
        "final_source": "Financial Times",
        "published_date": "2026-08-24",
    }
    candidates = [
        {
            "url_canonical": item["final_url_canonical"],
            "published_at": "2026-08-24 04:00 UTC",
        }
    ]
    result = resolve_publication_evidence(item=item, candidate_rows=candidates, tz=TZ)
    assert result.status == "exact_persisted"
    assert result.precision == "datetime"
    assert result.resolved_at == datetime(2026, 8, 24, 12, 0, tzinfo=TZ)


def test_conflicting_trusted_exact_publication_times_fail_closed() -> None:
    item = {
        "final_url": "https://example.com/story",
        "final_url_canonical": "https://example.com/story",
        "final_title": "Story",
        "final_source": "Example",
        "published_date": "2026-08-24",
    }
    candidates = [
        {"url_canonical": "https://example.com/story", "published_at": "2026-08-24 10:00 BJT"},
        {"url_canonical": "https://example.com/story", "published_at": "2026-08-24 11:00 BJT"},
    ]
    result = resolve_publication_evidence(item=item, candidate_rows=candidates, tz=TZ)
    assert result.status == "publication_date_conflict"
    assert result.resolved_at is None


def test_orphan_coverage_row_cannot_establish_recall_measurement() -> None:
    item = {
        "language": "en",
        "final_url": "https://www.ft.com/content/example",
        "final_url_canonical": "https://ft.com/content/example",
        "final_title": "Example",
        "final_source": "Financial Times",
        "published_date": "2026-08-24 12:00:00",
        "item_observation_started_at_bj": "2026-08-24 00:00:00",
        "cutoff_at_bj": "2026-08-25 07:35:00",
        "observation_coverage_status": "full",
        "measurement_age_bucket": "0_3d",
        "match_status": "not_discovered",
    }
    source = {"source_id": "ft", "language": "en"}
    coverage = [
        {
            "collector_run_id": "COL-orphan",
            "query_group": "intl_early",
            "run_started_at_bj": "2026-08-24 23:00:00",
            "source_id": "ft",
            "selected": "TRUE",
            "route_status": "native_covered",
            "oldest_observed_published_at": "2026-08-24 00:00:00",
            "newest_observed_published_at": "2026-08-24 22:00:00",
            "coverage_version": "run-source-coverage-v0.2",
        }
    ]
    failed_run = {
        "collector_run_id": "COL-orphan",
        "started_at_bj": "2026-08-24 23:00:00",
        "completed_at_bj": "2026-08-24 23:05:00",
        "query_group": "intl_early",
        "final_status": "failed",
        "notes": _durable_notes(),
    }
    bootstrap = {
        "collector_run_id": "COL-bootstrap",
        "started_at_bj": "2026-08-23 23:00:00",
        "completed_at_bj": "2026-08-23 23:05:00",
        "query_group": "intl_early",
        "final_status": "success",
        "notes": _durable_notes(),
    }
    runs = [bootstrap, failed_run]
    result = evaluate_strict_measurement_item(
        item=item,
        source_row=source,
        candidate_rows=[],
        coverage_rows=coverage,
        collector_runs=runs,
        ledger_started_at=strict_coverage_ledger_start(runs, TZ),
        tz=TZ,
    )
    assert result["strict_measurement_universe_status"] == "included"
    assert result["realized_coverage_status"] == "nondurable_coverage_only"
    assert result["conditional_surface_denominator_status"] == "excluded"


def test_fixed_phase2_replay_reproduces_forensic_baseline() -> None:
    fixture = _fixture()
    sources = {row["source_id"]: row for row in fixture["source_rows"]}
    runs = fixture["collector_runs"]
    ledger_start = strict_coverage_ledger_start(runs, TZ)
    assert ledger_start == datetime(2026, 8, 18, 18, 12, 36, tzinfo=TZ)

    replayed = []
    for frozen in fixture["items"]:
        item = dict(frozen)
        source = sources.get(item.pop("fixture_source_id"))
        item.update(
            evaluate_strict_measurement_item(
                item=item,
                source_row=source,
                candidate_rows=fixture["candidate_rows"],
                coverage_rows=fixture["coverage_rows"],
                collector_runs=runs,
                ledger_started_at=ledger_start,
                tz=TZ,
            )
        )
        replayed.append(item)

    expected = fixture["expected"]
    summary = strict_summary(replayed, ledger_start)
    assert len(replayed) == expected["final_items"] == 58
    assert summary["strict_measurement_universe"] == expected["strict_measurement_universe"] == 36
    assert summary["strict_measurement_covered"] == expected["strict_measurement_covered"] == 15
    assert summary["strict_measurement_coverage_rate"] == pytest.approx(15 / 36)
    assert summary["conditional_surface_recall_denominator"] == 15
    assert summary["conditional_surface_recall_discovered"] == 13
    assert summary["conditional_surface_recall"] == pytest.approx(13 / 15)
    assert summary["conditional_surface_editable"] == 9
    assert summary["conditional_surface_editable_recall"] == pytest.approx(9 / 15)
    assert summary["strict_measurement_zh_covered"] == 1
    assert summary["strict_measurement_en_covered"] == 14

    # Independent denominator guards: 7 scholarly Nature assets, 5 publication-
    # surface mismatches and 10 pre-ledger items are what reduce 58 -> 36.
    assert summary["product_scope_excluded_items"] == 7
    assert summary["publication_surface_mismatch_items"] == 5
    assert summary["preledger_items"] == 10

    clean_misses = sorted(
        row["final_title"]
        for row in replayed
        if row.get("conditional_surface_denominator_status") == "conditional_surface_denominator"
        and row.get("match_status") == "not_discovered"
    )
    assert clean_misses == sorted(expected["clean_miss_titles"])


def test_scheduled_final_recall_workflow_remains_on_v12() -> None:
    workflow = Path(".github/workflows/final-recall-audit.yml").read_text(encoding="utf-8")
    assert "python -m longread_collector.final_recall_audit_v12_runner" in workflow
    assert "final_recall_audit_v131_runner" not in workflow
