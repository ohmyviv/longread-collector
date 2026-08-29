from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from longread_collector.config import Settings
from longread_collector.zh_route_shadow_s2b_track_v2 import run_track_v


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="s2b-v2-track-v-results.json")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    settings = Settings()
    result = asyncio.run(run_track_v(manifest, settings))
    result["execution_commit"] = os.environ.get("GITHUB_SHA", "")
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
