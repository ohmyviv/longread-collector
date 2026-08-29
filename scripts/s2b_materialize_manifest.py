from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import gspread

from longread_collector.zh_route_shadow_s2b_sample_plan_v1 import sample_summary, select_s2b_sample

AUDIT_SHEET_ID = "1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ"
COHORT_TAB = "s2a_cohort"
SEMANTIC_RUNTIME_BASELINE = "a380c68920c1de26f1e703b721d7eb2195900002"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_manifest(rows: list[dict[str, object]]) -> dict[str, object]:
    sample = select_s2b_sample(rows)
    by_url = {str(row["url_canonical"]).strip(): row for row in rows}
    items: list[dict[str, object]] = []
    for ordinal, selected in enumerate(sample, start=1):
        source = by_url[selected.url_canonical]
        items.append(
            {
                "manifest_ordinal": ordinal,
                **selected.as_dict(),
                "title": str(source.get("title") or "").strip(),
                "qualifying_surfaces": str(source.get("qualifying_surfaces") or "").strip(),
                "qualifying_row_count": str(source.get("qualifying_row_count") or "").strip(),
            }
        )
    manifest_sha256 = hashlib.sha256(canonical_json(items).encode("utf-8")).hexdigest()
    return {
        "schema_version": "zh-route-shadow-s2b-manifest-v1",
        "semantic_runtime_baseline": SEMANTIC_RUNTIME_BASELINE,
        "source_sheet_id": AUDIT_SHEET_ID,
        "source_tab": COHORT_TAB,
        "source_row_count": len(rows),
        "sample_summary": sample_summary(sample),
        "manifest_sha256": manifest_sha256,
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="s2b-manifest.json")
    args = parser.parse_args()
    credential_file = os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]
    client = gspread.service_account(filename=credential_file)
    ws = client.open_by_key(AUDIT_SHEET_ID).worksheet(COHORT_TAB)
    rows = ws.get_all_records(expected_headers=[
        "url_canonical", "source_id", "title", "first_surface",
        "qualifying_row_count", "qualifying_surfaces", "metadata_class", "class_reason",
    ])
    manifest = build_manifest(rows)
    Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(canonical_json({k: v for k, v in manifest.items() if k != "items"}))


if __name__ == "__main__":
    main()
