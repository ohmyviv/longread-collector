from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .config import get_settings
from .known_source_fixes import probe_known_sources
from .sheets import GoogleSheetStore


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
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    fallback = set(result["fallback_sources"])
    if result["sources_attempted"] != 4:
        raise SystemExit("expected exactly four known sources")
    if result["native_successes"] < 3:
        raise SystemExit("expected at least three repaired native sources")
    if fallback != {"inside-climate-news"}:
        raise SystemExit(
            f"unexpected fallback set: {sorted(fallback)}; expected inside-climate-news only"
        )


if __name__ == "__main__":
    main()
