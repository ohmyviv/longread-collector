#!/usr/bin/env bash
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "ERROR: run this script from inside a clone of the repository." >&2
  exit 2
fi
cd "$ROOT"

OUT_DIR="${1:-$ROOT/.public-readiness-scan}"
mkdir -p "$OUT_DIR"

missing=0
for cmd in git python3 gitleaks trufflehog; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "MISSING_TOOL=$cmd" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "Install the missing scanners before rerunning. On macOS with Homebrew: brew install gitleaks trufflehog" >&2
  exit 2
fi

echo "== Fetch reachable history =="
git fetch --all --tags --prune
# GitHub pull-request refs are not part of a normal clone. Include them because
# PR commits can become visible when a private repository is made public.
if ! git fetch origin '+refs/pull/*/head:refs/remotes/origin/pr/*'; then
  echo "WARNING: could not fetch GitHub pull-request refs; branch/tag history will still be scanned." >&2
  PR_REFS_FETCHED=false
else
  PR_REFS_FETCHED=true
fi

COMMIT_COUNT="$(git rev-list --all --count)"
REF_COUNT="$(git for-each-ref --format='%(refname)' | wc -l | tr -d ' ')"
echo "COMMITS_REACHABLE=$COMMIT_COUNT"
echo "REFS_REACHABLE=$REF_COUNT"
echo "PR_REFS_FETCHED=$PR_REFS_FETCHED"
echo "GITLEAKS_VERSION=$(gitleaks version 2>/dev/null || gitleaks --version 2>/dev/null || echo unknown)"
echo "TRUFFLEHOG_VERSION=$(trufflehog --version 2>/dev/null || echo unknown)"

rm -f \
  "$OUT_DIR/gitleaks-redacted.json" \
  "$OUT_DIR/gitleaks.stdout.log" \
  "$OUT_DIR/gitleaks.stderr.log" \
  "$OUT_DIR/trufflehog-redacted.jsonl" \
  "$OUT_DIR/trufflehog.stderr.log" \
  "$OUT_DIR/trufflehog-non-lob-redacted.jsonl" \
  "$OUT_DIR/trufflehog-non-lob.stderr.log" \
  "$OUT_DIR/sensitive-history-filenames.txt"

echo "== Gitleaks full reachable-history scan =="
gitleaks git "$ROOT" \
  --log-opts='--all' \
  --redact=100 \
  --report-format=json \
  --report-path="$OUT_DIR/gitleaks-redacted.json" \
  -v \
  >"$OUT_DIR/gitleaks.stdout.log" \
  2>"$OUT_DIR/gitleaks.stderr.log"
GITLEAKS_STATUS=$?

GITLEAKS_FINDINGS="$(python3 - "$OUT_DIR/gitleaks-redacted.json" <<'PY'
import json, os, sys
path = sys.argv[1]
if not os.path.exists(path) or os.path.getsize(path) == 0:
    print(0)
    raise SystemExit
try:
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    print(len(data) if isinstance(data, list) else 1)
except Exception:
    print(-1)
PY
)"

if grep -Eqi '0 commits scanned' "$OUT_DIR/gitleaks.stdout.log" "$OUT_DIR/gitleaks.stderr.log" 2>/dev/null && [[ "$COMMIT_COUNT" -gt 0 ]]; then
  GITLEAKS_INTEGRITY=FAIL_ZERO_COMMITS
else
  GITLEAKS_INTEGRITY=PASS
fi

echo "GITLEAKS_EXIT=$GITLEAKS_STATUS"
echo "GITLEAKS_FINDINGS=$GITLEAKS_FINDINGS"
echo "GITLEAKS_INTEGRITY=$GITLEAKS_INTEGRITY"

echo "== TruffleHog cross-check (sanitized output only) =="
SANITIZER="$OUT_DIR/.sanitize_trufflehog.py"
cat >"$SANITIZER" <<'PY'
import json
import sys

out_path = sys.argv[1]
with open(out_path, 'w', encoding='utf-8') as out:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        source = item.get('SourceMetadata') or {}
        data = source.get('Data') or {}
        git = data.get('Git') or {}
        safe = {
            'DetectorName': item.get('DetectorName'),
            'Verified': item.get('Verified'),
            'VerificationFromCache': item.get('VerificationFromCache'),
            'DecoderName': item.get('DecoderName'),
            'Commit': git.get('commit'),
            'File': git.get('file'),
            'Line': git.get('line'),
            'Email': git.get('email'),
            'Timestamp': git.get('timestamp'),
        }
        out.write(json.dumps(safe, ensure_ascii=False) + '\n')
PY

trufflehog git "file://$ROOT" \
  --results=verified,unknown \
  --json \
  2>"$OUT_DIR/trufflehog.stderr.log" \
  | python3 "$SANITIZER" "$OUT_DIR/trufflehog-redacted.jsonl"
PIPE_STATUS=("${PIPESTATUS[@]}")
TRUFFLEHOG_STATUS="${PIPE_STATUS[0]:-1}"
SANITIZER_STATUS="${PIPE_STATUS[1]:-1}"

read -r TRUFFLEHOG_FINDINGS TRUFFLEHOG_VERIFIED TRUFFLEHOG_UNKNOWN < <(
python3 - "$OUT_DIR/trufflehog-redacted.jsonl" <<'PY'
import json, os, sys
path = sys.argv[1]
total = verified = unknown = 0
if os.path.exists(path):
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except Exception:
                continue
            total += 1
            if item.get('Verified') is True:
                verified += 1
            else:
                unknown += 1
print(total, verified, unknown)
PY
)

echo "TRUFFLEHOG_EXIT=$TRUFFLEHOG_STATUS"
echo "TRUFFLEHOG_SANITIZER_EXIT=$SANITIZER_STATUS"
echo "TRUFFLEHOG_FINDINGS=$TRUFFLEHOG_FINDINGS"
echo "TRUFFLEHOG_VERIFIED=$TRUFFLEHOG_VERIFIED"
echo "TRUFFLEHOG_UNKNOWN=$TRUFFLEHOG_UNKNOWN"

# TruffleHog v3.96.0's Lob detector matches any test_ + 35 alnum/underscore
# string and treats HTTP 422 as verified. Python test function names in this
# repository can therefore become verified false positives. Keep the all-detector
# evidence above, then run a second pass excluding Lob so other detectors remain
# independently visible. Lob findings must still be manually reviewed.
echo "== TruffleHog non-Lob cross-check (sanitized output only) =="
trufflehog git "file://$ROOT" \
  --results=verified,unknown \
  --exclude-detectors=Lob \
  --json \
  2>"$OUT_DIR/trufflehog-non-lob.stderr.log" \
  | python3 "$SANITIZER" "$OUT_DIR/trufflehog-non-lob-redacted.jsonl"
NON_LOB_PIPE_STATUS=("${PIPESTATUS[@]}")
TRUFFLEHOG_NON_LOB_STATUS="${NON_LOB_PIPE_STATUS[0]:-1}"
NON_LOB_SANITIZER_STATUS="${NON_LOB_PIPE_STATUS[1]:-1}"
rm -f "$SANITIZER"

read -r TRUFFLEHOG_NON_LOB_FINDINGS TRUFFLEHOG_NON_LOB_VERIFIED TRUFFLEHOG_NON_LOB_UNKNOWN < <(
python3 - "$OUT_DIR/trufflehog-non-lob-redacted.jsonl" <<'PY'
import json, os, sys
path = sys.argv[1]
total = verified = unknown = 0
if os.path.exists(path):
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except Exception:
                continue
            total += 1
            if item.get('Verified') is True:
                verified += 1
            else:
                unknown += 1
print(total, verified, unknown)
PY
)

echo "TRUFFLEHOG_NON_LOB_EXIT=$TRUFFLEHOG_NON_LOB_STATUS"
echo "TRUFFLEHOG_NON_LOB_SANITIZER_EXIT=$NON_LOB_SANITIZER_STATUS"
echo "TRUFFLEHOG_NON_LOB_FINDINGS=$TRUFFLEHOG_NON_LOB_FINDINGS"
echo "TRUFFLEHOG_NON_LOB_VERIFIED=$TRUFFLEHOG_NON_LOB_VERIFIED"
echo "TRUFFLEHOG_NON_LOB_UNKNOWN=$TRUFFLEHOG_NON_LOB_UNKNOWN"

echo "== Historical sensitive-looking filenames =="
git log --all --name-only --pretty=format: \
  | sort -u \
  | grep -Ei '(^|/)\.env($|\.)|credential|service.?account|private.?key|\.pem$|\.key$|token' \
  | grep -Ev '(^|/)\.env\.example$|scripts/public_readiness_secret_scan\.sh$' \
  >"$OUT_DIR/sensitive-history-filenames.txt" || true
SENSITIVE_FILENAME_COUNT="$(grep -c . "$OUT_DIR/sensitive-history-filenames.txt" 2>/dev/null || true)"
echo "SENSITIVE_HISTORY_FILENAMES=$SENSITIVE_FILENAME_COUNT"

if [[ "$GITLEAKS_INTEGRITY" != PASS || "$TRUFFLEHOG_STATUS" -ne 0 || "$SANITIZER_STATUS" -ne 0 || "$TRUFFLEHOG_NON_LOB_STATUS" -ne 0 || "$NON_LOB_SANITIZER_STATUS" -ne 0 ]]; then
  FINAL_STATUS=SCANNER_INTEGRITY_FAILED
elif [[ "$GITLEAKS_FINDINGS" -gt 0 || "$TRUFFLEHOG_FINDINGS" -gt 0 || "$SENSITIVE_FILENAME_COUNT" -gt 0 ]]; then
  FINAL_STATUS=REVIEW_REQUIRED
else
  FINAL_STATUS=CLEAN_CANDIDATE
fi

echo "== Summary =="
echo "PUBLIC_READINESS_SECRET_SCAN_STATUS=$FINAL_STATUS"
echo "REPORT_DIR=$OUT_DIR"
echo "Share the summary plus the *redacted* reports only. Do not share raw credentials or tokens."
