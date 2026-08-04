from pathlib import Path


WORKFLOW = Path(".github/workflows/final-recall-audit.yml")


def test_scheduled_recall_workflow_uses_v11_runner_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "python -m longread_collector.final_recall_audit_v11_runner" in text
    assert "python -m longread_collector.final_recall_audit \"${args[@]}\"" not in text
    assert "final_recall_audit_v11.py" in text
    assert "final_recall_audit_v11_runner.py" in text
    assert "registry_matching_v056.py" in text


def test_scheduled_recall_workflow_targets_v11_sheets_indirectly() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "final-recall-audit-v11-summary.json" in text
    assert "TZ=Asia/Shanghai date +%F" in text
    assert "--report-date \"$report_date\"" in text
    assert "--cutoff-time 07:35" in text
    assert "--lookback-hours 48" in text
