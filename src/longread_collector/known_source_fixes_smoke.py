from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .config import get_settings
from .known_source_fixes import probe_known_sources
from .sheets import GoogleSheetStore

_TRANSIENT_NETWORK_ERRORS = {
    "ReadTimeout",
    "ConnectTimeout",
    "ConnectError",
    "ReadError",
    "RemoteProtocolError",
}


def _log_by_source(result: dict[str, object]) -> dict[str, dict[str, object]]:
    logs = result.get("logs", [])
    return {
        str(log.get("source_id", "")): log
        for log in logs
        if isinstance(log, dict) and log.get("source_id")
    }


def _attempts(log: dict[str, object]) -> list[dict[str, object]]:
    raw = log.get("attempts", [])
    return [attempt for attempt in raw if isinstance(attempt, dict)]


def _has_attempt(
    log: dict[str, object],
    *,
    method: str,
    endpoint_contains: str,
    acceptable_statuses: set[int] | None = None,
) -> bool:
    for attempt in _attempts(log):
        if str(attempt.get("method", "")) != method:
            continue
        if endpoint_contains not in str(attempt.get("endpoint", "")):
            continue
        status = attempt.get("http_status")
        if acceptable_statuses is None or status in acceptable_statuses:
            return True
    return False


def validate_known_source_probe(result: dict[str, object]) -> dict[str, object]:
    """Validate repaired routes without requiring fresh articles every run.

    A smoke check should fail for a broken endpoint or missing fallback policy,
    not because a healthy RSS feed has no items inside the current freshness
    window or because an upstream reader has one transient timeout.
    """

    logs = _log_by_source(result)
    jiemian = logs.get("jiemian-depth", {})
    deeptech = logs.get("deeptech", {})
    knowable = logs.get("knowable", {})
    inside = logs.get("inside-climate-news", {})

    checks = {
        "jiemian_endpoint": bool(jiemian.get("success"))
        and str(jiemian.get("selected_endpoint", "")).endswith("/lists/423.html"),
        "knowable_rss_reachable": _has_attempt(
            knowable,
            method="rss",
            endpoint_contains="knowablemagazine.org/rss",
            acceptable_statuses={200},
        ),
        "deeptech_reader_route": _has_attempt(
            deeptech,
            method="reader_section",
            endpoint_contains="r.jina.ai/http://www.mittrchina.com/news",
        )
        and (
            bool(deeptech.get("success"))
            or str(deeptech.get("error_type", "")) in _TRANSIENT_NETWORK_ERRORS
        ),
        "inside_climate_bounded_fallback": (
            str(inside.get("error_type", "")) == "NativeAccessBlocked"
            and bool(inside.get("fallback_needed"))
            and _has_attempt(
                inside,
                method="firecrawl_search",
                endpoint_contains="insideclimatenews.org",
            )
        ),
    }
    return {
        "checks": checks,
        "operationally_healthy": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate the four v0.5.1 known-source repairs without extraction"
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/known-source-fixes-smoke.json"),
    )
    args = parser.parse_args()

    store = GoogleSheetStore(get_settings())
    sources = store.load_source_registry("zh") + store.load_source_registry("en")
    result = asyncio.run(probe_known_sources(sources))
    validation = validate_known_source_probe(result)
    result.update(validation)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["sources_attempted"] != 4:
        raise SystemExit("expected exactly four known sources")
    if not result["operationally_healthy"]:
        failed = [
            name for name, passed in result["checks"].items() if not passed
        ]
        raise SystemExit(f"known-source route checks failed: {failed}")


if __name__ == "__main__":
    main()
