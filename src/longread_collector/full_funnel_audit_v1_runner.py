"""CLI for the artifact-only full-funnel audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .full_funnel_audit_v1 import build_full_funnel_audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive a read-only Discovery→Selection funnel from collector-result.json"
    )
    parser.add_argument("--input", required=True, type=Path, help="collector-result.json")
    parser.add_argument("--output", type=Path, help="Optional JSON output path; stdout if omitted")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    audit = build_full_funnel_audit(payload)
    text = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
