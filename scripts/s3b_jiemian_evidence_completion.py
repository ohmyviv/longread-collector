from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from longread_collector.config import Settings
from longread_collector.zh_route_shadow_s3b_evidence_v1 import manifest_payload, run_s3b


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="s3b-jiemian-evidence-results.json")
    parser.add_argument("--manifest-output", default="s3b-jiemian-evidence-manifest.json")
    args = parser.parse_args()

    Path(args.manifest_output).write_text(
        json.dumps(manifest_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = asyncio.run(run_s3b(Settings()))
    result["execution_commit"] = os.environ.get("GITHUB_SHA", "")
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "results"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
