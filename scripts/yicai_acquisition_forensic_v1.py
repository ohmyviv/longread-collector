from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import gspread

from longread_collector.yicai_acquisition_forensic_v1 import execute_manifest, manifest_sha256, select_manifest

AUDIT_SHEET_ID = "1dE_0alXOO254hrycAMNISmjpL8brLUji9ZNMK0NBDnQ"
MANIFEST_TAB = "s2b_manifest"


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


async def run(output: str) -> None:
    client = gspread.service_account(filename=os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"])
    workbook = client.open_by_key(AUDIT_SHEET_ID)
    rows = _records(workbook.worksheet(MANIFEST_TAB))
    manifest = select_manifest(rows)
    result = await execute_manifest(manifest, firecrawl_api_key=os.environ["FIRECRAWL_API_KEY"])
    result["manifest"] = [
        {
            "ordinal": item.ordinal,
            "first_surface": item.first_surface,
            "canonical_url": item.canonical_url,
            "title": item.title,
            "deterministic_rank": item.deterministic_rank,
        }
        for item in manifest
    ]
    result["manifest_sha256_recomputed"] = manifest_sha256(manifest)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "version": result["version"],
        "status": result["status"],
        "manifest_sha256": result["manifest_sha256"],
        "actual_http_requests": result["actual_http_requests"],
        "signals": result["signals"],
        "manifest": result["manifest"],
    }, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="yicai-acquisition-forensic-v1.json")
    args = parser.parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()
