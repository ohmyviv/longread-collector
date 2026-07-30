from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_settings
from .native_discovery import NativeSourceDiscovery, select_sources_for_run
from .sheets import GoogleSheetStore

SMOKE_HEADERS = [
    "run_at_bj",
    "source_id",
    "source_name",
    "language",
    "priority_tier",
    "success",
    "selected_method",
    "selected_endpoint",
    "results_count",
    "fallback_needed",
    "error_type",
    "error_message",
]


def summarize(logs: list[dict[str, Any]], items_count: int) -> dict[str, Any]:
    successes = sum(bool(log.get("success")) for log in logs)
    fallback = sum(bool(log.get("fallback_needed")) for log in logs)
    return {
        "sources_attempted": len(logs),
        "sources_succeeded": successes,
        "source_success_rate": successes / len(logs) if logs else 0.0,
        "native_items_discovered": items_count,
        "fallback_sources": fallback,
        "estimated_firecrawl_queries_avoided": successes,
        "estimated_firecrawl_queries_required": fallback,
        "methods": dict(
            Counter(
                str(log.get("selected_method", ""))
                for log in logs
                if log.get("success")
            )
        ),
        "languages": dict(Counter(str(log.get("language", "")) for log in logs)),
    }


def write_sheet(store: GoogleSheetStore, logs: list[dict[str, Any]], now: str) -> None:
    try:
        worksheet = store.book.worksheet("native_discovery_shadow")
    except Exception:
        worksheet = store.book.add_worksheet(
            title="native_discovery_shadow",
            rows=1000,
            cols=len(SMOKE_HEADERS),
        )
        worksheet.append_row(SMOKE_HEADERS, value_input_option="USER_ENTERED")
    rows = []
    for log in logs:
        rows.append(
            [
                now,
                log.get("source_id", ""),
                log.get("source_name", ""),
                log.get("language", ""),
                log.get("priority_tier", ""),
                str(bool(log.get("success"))).upper(),
                log.get("selected_method", ""),
                log.get("selected_endpoint", ""),
                log.get("results_count", 0),
                str(bool(log.get("fallback_needed"))).upper(),
                log.get("error_type", ""),
                log.get("error_message", ""),
            ]
        )
    if rows:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")


async def run_smoke(
    store: GoogleSheetStore,
    *,
    max_sources_per_language: int,
    timeout: float,
    concurrency: int,
    limit_per_source: int,
    freshness_days: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = datetime.now(store.tz)
    selected: list[dict[str, Any]] = []
    for language in ("zh", "en"):
        selected.extend(
            select_sources_for_run(
                store.load_source_registry(language),
                started=started,
                max_sources=max_sources_per_language,
            )
        )
    discovery = NativeSourceDiscovery(timeout=timeout, concurrency=concurrency)
    batch = await discovery.discover(
        selected,
        limit_per_source=limit_per_source,
        started=started,
        freshness_days=freshness_days,
    )
    source_by_id = {str(source.get("source_id", "")): source for source in selected}
    logs: list[dict[str, Any]] = []
    for log in batch.logs:
        source = source_by_id.get(str(log.get("source_id", "")), {})
        logs.append(
            {
                **log,
                "language": str(source.get("language", "")),
                "priority_tier": str(source.get("priority_tier", "")),
            }
        )
    summary = summarize(logs, len(batch.items))
    summary["run_at_bj"] = started.strftime("%Y-%m-%d %H:%M:%S")
    summary["selected_source_ids"] = [
        str(source.get("source_id", "")) for source in selected
    ]
    return summary, logs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run native discovery without extraction")
    parser.add_argument("--max-sources-per-language", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--limit-per-source", type=int, default=6)
    parser.add_argument("--freshness-days", type=int, default=3)
    parser.add_argument("--minimum-success-rate", type=float, default=0.40)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/native-discovery-smoke.json"),
    )
    parser.add_argument("--skip-sheet-write", action="store_true")
    args = parser.parse_args()

    store = GoogleSheetStore(get_settings())
    summary, logs = asyncio.run(
        run_smoke(
            store,
            max_sources_per_language=args.max_sources_per_language,
            timeout=args.timeout,
            concurrency=args.concurrency,
            limit_per_source=args.limit_per_source,
            freshness_days=args.freshness_days,
        )
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps({"summary": summary, "logs": logs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not args.skip_sheet_write:
        write_sheet(store, logs, str(summary["run_at_bj"]))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["source_success_rate"] < args.minimum_success_rate:
        raise SystemExit(
            "native discovery success rate below threshold: "
            f"{summary['source_success_rate']:.3f} < {args.minimum_success_rate:.3f}"
        )


if __name__ == "__main__":
    main()
