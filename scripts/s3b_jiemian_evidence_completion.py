from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

from longread_collector.zh_route_shadow_s3b_evidence_v1 import manifest_payload, run_s3b


def _measurement_settings():
    """Construct only the external-service settings this isolated runner uses.

    S3-B performs zero Google Sheets operations, so requiring production Sheet or
    service-account configuration would add an unrelated execution dependency.
    """
    return SimpleNamespace(
        jina_reader_base_url=os.environ.get("JINA_READER_BASE_URL", "https://r.jina.ai"),
        firecrawl_base_url=os.environ.get("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev"),
        firecrawl_api_key=os.environ.get("FIRECRAWL_API_KEY", ""),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="s3b-jiemian-evidence-results.json")
    parser.add_argument("--manifest-output", default="s3b-jiemian-evidence-manifest.json")
    args = parser.parse_args()

    Path(args.manifest_output).write_text(
        json.dumps(manifest_payload(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result = asyncio.run(run_s3b(_measurement_settings()))
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
