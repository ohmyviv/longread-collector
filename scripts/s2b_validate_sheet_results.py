from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import gspread

from longread_collector.zh_route_shadow_s2b_result_contract_v1 import validate_s2b_results
from longread_collector.zh_route_shadow_s2b_sample_plan_v1 import S2BSampleItem

AUDIT_SHEET_ID = "1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ"
EXPECTED_MANIFEST_SHA256 = "7946ce964f82abd14a95e925769dbcde484dd581d0713d4996f149cb216a247b"
EXPECTED_TOTAL = 40


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="s2b-validation-summary.json")
    args = parser.parse_args()

    client = gspread.service_account(filename=os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
    book = client.open_by_key(AUDIT_SHEET_ID)
    manifest_rows = book.worksheet("s2b_manifest").get_all_records()
    result_rows = book.worksheet("s2b_results").get_all_records()

    if len(manifest_rows) != EXPECTED_TOTAL:
        raise ValueError(f"expected {EXPECTED_TOTAL} manifest rows, found {len(manifest_rows)}")
    if len(result_rows) != EXPECTED_TOTAL:
        raise ValueError(f"expected {EXPECTED_TOTAL} result rows, found {len(result_rows)}")
    hashes = {str(row.get("manifest_sha256") or "").strip() for row in manifest_rows}
    if hashes != {EXPECTED_MANIFEST_SHA256}:
        raise ValueError(f"manifest hash drift: {sorted(hashes)}")

    sample = tuple(
        S2BSampleItem(
            url_canonical=str(row["url_canonical"]).strip(),
            source_id=str(row["source_id"]).strip(),
            first_surface=str(row["first_surface"]).strip(),
            metadata_class=str(row["metadata_class"]).strip(),
            sampling_role=str(row["sampling_role"]).strip(),
            deterministic_rank=str(row["deterministic_rank"]).strip(),
        )
        for row in manifest_rows
    )
    summary = validate_s2b_results(sample, result_rows)
    summary["manifest_sha256"] = EXPECTED_MANIFEST_SHA256
    summary["audit_sheet_id"] = AUDIT_SHEET_ID
    Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if not summary["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
