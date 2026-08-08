from pathlib import Path


WORKFLOW = Path(".github/workflows/final-recall-audit.yml")


def test_scheduled_recall_workflow_uses_v11_runner_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "python -m longread_collector.final_recall_audit_v11_runner" in text
    assert "python -m longread_collector.final_recall_audit \"${args[@]}\"" not in text
    assert "pull_request:" not in text


def test_scheduled_recall_workflow_targets_v11_sheets_indirectly() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "final-recall-audit-v11-summary.json" in text
    assert "TZ=Asia/Shanghai date +%F" in text
    assert "--report-date \"$report_date\"" in text
    assert "--cutoff-time 07:35" in text
    assert "--lookback-hours 48" in text


def test_manual_mode_is_explicit_and_defaults_to_writing() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "execution_mode:" in text
    assert "default: write_to_sheets" in text
    assert "- write_to_sheets" in text
    assert "- dry_run" in text
    assert 'mode="${EXECUTION_MODE:-write_to_sheets}"' in text
    assert 'if [ "$mode" = "dry_run" ]; then' in text


def test_write_mode_verifies_both_v11_sheets() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "Verify v1.1 Sheet write" in text
    assert 'store.book.worksheet("final_recall_daily_v11")' in text
    assert 'store.book.worksheet("final_recall_audit_v11")' in text
    assert "Write verification failed" in text
    assert "RESOLVED_REPORT_DATE" in text
    assert "EFFECTIVE_MODE" in text
    assert text.count("FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}") == 2
