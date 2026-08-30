from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import gspread

from longread_collector.zh_route_shadow_s3_fixed32_v12 import (
    FROZEN_RUN_IDS,
    replay_s3_cohort,
)

LIVE_SHEET_ID = "1Ohi2amTCPnIZZont7rwOLO487DFk64-pemLT8O76xq4"
AUDIT_SHEET_ID = "1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ"
SNAPSHOT_TAB = "collector_discovery_snapshot"
ROUTE_TAB = "collector_route_shadow_items"
COHORT_TAB = "s2a_cohort"
REVIEW_TAB = "s2b_v21_results"

S3B_PROVENANCE = {
    "experiment": "zh-route-shadow-s3b-jiemian-evidence-completion-v1",
    "continuation_workflow_run_id": 33302774739,
    "artifact_id": 9729478058,
    "artifact_sha256": "ff3dfbad9a86d729794f1292bb721a33d021b7f31b8bb2b99c051f780006570a",
    "manifest_sha256": "ff4fe7d54b1c38b3105329ec5653bed14799e7ae493bd36dc4d93fd88bfbc865",
    "denominator": 4,
    "replacement": 0,
}

S3B_REVIEW_OVERLAY = [
    {
        "url": "https://jiemian.com/article/14977759.html",
        "source": "jiemian-depth",
        "role": "primary_plausible",
        "review_class": "not_evaluable_instrumentation_failure_after_network_attempt",
        "evidence_state": "instrumentation_censored",
        "final_reason": "result_lost_after_real_network_exposure; compensating_rerun_forbidden",
    },
    {
        "url": "https://jiemian.com/article/14997276.html",
        "source": "jiemian-depth",
        "role": "primary_plausible",
        "review_class": "body_confirmed_non_target",
        "evidence_state": "body_observed",
        "final_reason": "press_release_or_corporate_promotion",
    },
    {
        "url": "https://jiemian.com/article/14998723.html",
        "source": "jiemian-depth",
        "role": "primary_plausible",
        "review_class": "body_confirmed_standard_longread",
        "evidence_state": "body_observed",
        "final_reason": "standard_longread",
    },
    {
        "url": "https://jiemian.com/article/15018993.html",
        "source": "jiemian-depth",
        "role": "primary_plausible",
        "review_class": "body_confirmed_non_target",
        "evidence_state": "body_observed",
        "final_reason": "press_release_or_corporate_promotion",
    },
]


def _records(ws) -> list[dict[str, Any]]:
    values = ws.get_all_values()
    if not values:
        return []
    headers = [str(value).strip() for value in values[0]]
    rows: list[dict[str, Any]] = []
    for values_row in values[1:]:
        if not any(str(value).strip() for value in values_row):
            continue
        padded = list(values_row) + [""] * max(0, len(headers) - len(values_row))
        rows.append(dict(zip(headers, padded[: len(headers)], strict=True)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="s3-jiemian-fixed32-replay-v12.json")
    args = parser.parse_args()

    credential_file = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
    client = gspread.service_account(filename=credential_file)
    live = client.open_by_key(LIVE_SHEET_ID)
    audit = client.open_by_key(AUDIT_SHEET_ID)

    frozen = set(FROZEN_RUN_IDS)
    snapshot_rows = [
        row
        for row in _records(live.worksheet(SNAPSHOT_TAB))
        if str(row.get("collector_run_id") or "").strip() in frozen
    ]
    route_rows = [
        row
        for row in _records(live.worksheet(ROUTE_TAB))
        if str(row.get("collector_run_id") or "").strip() in frozen
        and str(row.get("source_id") or "").strip() == "jiemian-depth"
    ]
    cohort_rows = _records(audit.worksheet(COHORT_TAB))
    reviewed_rows = _records(audit.worksheet(REVIEW_TAB)) + list(S3B_REVIEW_OVERLAY)

    result = replay_s3_cohort(
        snapshot_rows=snapshot_rows,
        route_rows=route_rows,
        cohort_rows=cohort_rows,
        reviewed_rows=reviewed_rows,
    )
    result["input_counts"] = {
        "snapshot_rows": len(snapshot_rows),
        "route_rows": len(route_rows),
        "cohort_rows": len(cohort_rows),
        "reviewed_rows_base": len(reviewed_rows) - len(S3B_REVIEW_OVERLAY),
        "reviewed_rows_s3b_overlay": len(S3B_REVIEW_OVERLAY),
    }
    result["s3b_provenance"] = dict(S3B_PROVENANCE)
    result["s3b_review_overlay"] = list(S3B_REVIEW_OVERLAY)
    result["read_only"] = True
    result["network_body_requests"] = 0
    result["sheet_writes"] = 0
    result["production_mutations"] = 0

    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "version": result.get("version"),
                "status": result.get("status"),
                "utility_status": result.get("utility_status"),
                "input_counts": result.get("input_counts"),
                "control_passes": [
                    bool(value.get("pass")) for value in result.get("control_replays", [])
                ],
                "evidence_completion_manifest": result.get("evidence_completion_manifest"),
                "utility_evidence_manifest": result.get("utility_evidence_manifest"),
                "utility_irrecoverable_censoring": result.get("utility_irrecoverable_censoring"),
                "treatment_entry_intended_dates": result.get("treatment_entry_intended_dates"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
