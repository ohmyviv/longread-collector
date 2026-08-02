from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import get_settings
from .effective_route_extensions_v056 import EffectiveRouteDiscovery
from .normalization import canonicalize_url
from .sheets import GoogleSheetStore

TARGET_URLS = {
    "propublica": {
        "https://www.propublica.org/article/federal-science-grants-russell-vought-omb",
    },
    "quanta": {
        "https://www.quantamagazine.org/a-new-way-that-a-cows-inner-world-shapes-earths-atmosphere-20260727/",
    },
    "jiemian-depth": {
        "https://www.jiemian.com/article/14841105.html",
        "https://www.jiemian.com/article/14839824.html",
    },
    "bjnews-depth": {
        "https://www.bjnews.com.cn/detail/1785144458129453.html",
        "https://www.bjnews.com.cn/detail/1785199934129721.html",
    },
    "thepaper": {
        "https://www.thepaper.cn/newsDetail_forward_33664738",
        "https://www.thepaper.cn/newsDetail_forward_33660139",
    },
}


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
    batch = asyncio.run(
        EffectiveRouteDiscovery(timeout=15, concurrency=10).discover(
            sources,
            limit_per_source=24,
            started=started,
            freshness_days=7,
        )
    )

    discovered_by_source: dict[str, set[str]] = {}
    for item in batch.items:
        source_id = str(item.metadata.get("source_id", ""))
        discovered_by_source.setdefault(source_id, set()).add(canonicalize_url(item.url))

    target_checks: dict[str, dict[str, bool]] = {}
    matched = 0
    total = 0
    for source_id, targets in TARGET_URLS.items():
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
        and logs.get(source_id, {}).get("configured_lookback_days") == 7
        and bool(logs.get(source_id, {}).get("effective_route_version"))
        for source_id in sorted(wanted)
    }
    recall = matched / total if total else 0.0
    result = {
        "started_at": started.isoformat(sep=" "),
        "sources_attempted": len(batch.logs),
        "items_discovered": len(batch.items),
        "route_checks": route_checks,
        "target_checks": target_checks,
        "target_matches": matched,
        "target_total": total,
        "target_recall": recall,
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
