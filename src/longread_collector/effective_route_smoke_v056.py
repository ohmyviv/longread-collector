from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import get_settings
from .effective_route_extensions_v056 import EffectiveRouteDiscovery
from .normalization import canonicalize_url
from .sheets import GoogleSheetStore

# Historical final-report targets are useful only while they remain inside the
# same seven-day window enforced by the live discovery route. Keeping their
# publication timestamps prevents an intentionally stale article from turning
# an otherwise healthy route red as wall-clock time advances.
TARGET_PUBLISHED_AT_BJ = {
    "propublica": {
        "https://www.propublica.org/article/federal-science-grants-russell-vought-omb": datetime(
            2026, 7, 27, 17, 0
        ),
    },
    "quanta": {
        "https://www.quantamagazine.org/a-new-way-that-a-cows-inner-world-shapes-earths-atmosphere-20260727/": datetime(
            2026, 7, 27, 0, 0
        ),
    },
    "jiemian-depth": {
        "https://www.jiemian.com/article/14841105.html": datetime(
            2026, 7, 29, 9, 37
        ),
        "https://www.jiemian.com/article/14839824.html": datetime(
            2026, 7, 29, 8, 36
        ),
    },
    "bjnews-depth": {
        "https://www.bjnews.com.cn/detail/1785144458129453.html": datetime(
            2026, 7, 28, 9, 16
        ),
        "https://www.bjnews.com.cn/detail/1785199934129721.html": datetime(
            2026, 7, 28, 8, 52
        ),
    },
    "thepaper": {
        "https://www.thepaper.cn/newsDetail_forward_33664738": datetime(
            2026, 7, 27, 7, 40
        ),
        "https://www.thepaper.cn/newsDetail_forward_33660139": datetime(
            2026, 7, 26, 22, 24
        ),
    },
}
TARGET_URLS = {
    source_id: set(targets)
    for source_id, targets in TARGET_PUBLISHED_AT_BJ.items()
}


def partition_target_urls(
    *,
    started: datetime,
    freshness_days: int,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Split fixed evidence URLs by the live route's current freshness window."""
    cutoff = started - timedelta(days=max(freshness_days, 7))
    active: dict[str, set[str]] = {}
    expired: dict[str, set[str]] = {}
    for source_id, targets in TARGET_PUBLISHED_AT_BJ.items():
        for url, published_at in targets.items():
            bucket = active if published_at >= cutoff else expired
            bucket.setdefault(source_id, set()).add(url)
    return active, expired


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live metadata-only smoke for v0.5.6 effective native routes"
    )
    parser.add_argument("--minimum-target-recall", type=float, default=0.75)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/effective-route-v056-smoke.json"),
    )
    args = parser.parse_args()

    settings = get_settings()
    store = GoogleSheetStore(settings)
    registry = store.load_source_registry("zh") + store.load_source_registry("en")
    wanted = set(TARGET_URLS)
    sources = [source for source in registry if str(source.get("source_id")) in wanted]
    missing_sources = sorted(wanted - {str(source.get("source_id")) for source in sources})
    if missing_sources:
        raise SystemExit(f"missing route sources in registry: {missing_sources}")

    started = datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    freshness_days = 7
    batch = asyncio.run(
        EffectiveRouteDiscovery(timeout=15, concurrency=10).discover(
            sources,
            limit_per_source=24,
            started=started,
            freshness_days=freshness_days,
        )
    )

    discovered_by_source: dict[str, set[str]] = {}
    for item in batch.items:
        source_id = str(item.metadata.get("source_id", ""))
        discovered_by_source.setdefault(source_id, set()).add(canonicalize_url(item.url))

    active_targets, expired_targets = partition_target_urls(
        started=started,
        freshness_days=freshness_days,
    )
    target_checks: dict[str, dict[str, bool]] = {}
    matched = 0
    total = 0
    for source_id, targets in active_targets.items():
        observed = discovered_by_source.get(source_id, set())
        checks: dict[str, bool] = {}
        for target in sorted(targets):
            hit = canonicalize_url(target) in observed
            checks[target] = hit
            total += 1
            matched += int(hit)
        target_checks[source_id] = checks

    logs = {str(log.get("source_id", "")): log for log in batch.logs}
    route_checks = {
        source_id: bool(logs.get(source_id, {}).get("success"))
        and int(logs.get(source_id, {}).get("metadata_limit") or 0) >= 24
        and logs.get(source_id, {}).get("configured_lookback_days") == freshness_days
        and bool(logs.get(source_id, {}).get("effective_route_version"))
        for source_id in sorted(wanted)
    }
    # Exact historical targets are a supplementary check. Once every fixture
    # has aged out, source route health remains enforced by route_checks rather
    # than manufacturing a zero-denominator failure.
    recall = matched / total if total else 1.0
    result = {
        "started_at": started.isoformat(sep=" "),
        "sources_attempted": len(batch.logs),
        "items_discovered": len(batch.items),
        "route_checks": route_checks,
        "target_checks": target_checks,
        "expired_targets": {
            source_id: sorted(targets)
            for source_id, targets in expired_targets.items()
        },
        "target_matches": matched,
        "target_total": total,
        "target_recall": recall,
        "target_gate_skipped": total == 0,
        "minimum_target_recall": args.minimum_target_recall,
        "logs": batch.logs,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not all(route_checks.values()):
        failed = [name for name, passed in route_checks.items() if not passed]
        raise SystemExit(f"effective route checks failed: {failed}")
    if recall < args.minimum_target_recall:
        raise SystemExit(
            f"target route recall {recall:.1%} below {args.minimum_target_recall:.1%}"
        )


if __name__ == "__main__":
    main()
