#!/usr/bin/env bash
set -euo pipefail
FILE="${1:-service-account.json}"
if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE" >&2
  exit 1
fi
base64 < "$FILE" | tr -d '\n'
echo
