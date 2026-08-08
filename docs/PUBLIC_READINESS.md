# Public repository readiness

This repository is intended to be safe to expose publicly without granting pull-request code access to production credentials or production data.

## CI trust boundaries

### Pull requests

`.github/workflows/tests.yml` is the public-safe PR gate.

It may:
- check out the proposed code;
- install Python dependencies;
- run `pytest`.

It must not:
- reference repository production secrets;
- access the production Google Sheet;
- call paid/live validation APIs with repository credentials;
- write production state.

### Trusted live validation

The following workflows are not triggered by ordinary pull requests and may use repository secrets or production-backed validation:

- `editorial-hotfix-v055.yml`
- `native-discovery-v05.yml`
- `offline-validation-v056.yml`
- `source-registry-validation.yml`

They are reserved for trusted manual execution (plus the explicitly retained owner-only branch trigger in source-registry validation).

### Scheduled production operations

- `collector.yml` remains schedule/manual only.
- `final-recall-audit.yml` remains schedule/manual only.
- Both retain `contents: read` permissions and use repository secrets only inside trusted jobs.

## Public artifact policy

Action artifacts produced by collector/live-validation workflows should use a short retention window. Public-readiness hardening standardizes the touched workflows on 7 days.

## Local secret hygiene

The root `.gitignore` excludes common local environment files, credential/key files, runtime output, and local security-scan reports. `.env.example` remains tracked as a non-secret template.

`.gitignore` does not remove secrets that were committed in the past.

## Full-history secret scan

On a trusted local clone, install the two scanners and run the repository helper:

```bash
brew install gitleaks trufflehog
bash scripts/public_readiness_secret_scan.sh
```

The helper:
- fetches branches, tags, and GitHub pull-request head refs;
- records the reachable commit/ref counts;
- runs Gitleaks across all reachable refs with 100% redaction;
- detects the known failure mode where Gitleaks reports zero scanned commits;
- cross-checks with TruffleHog;
- writes only sanitized TruffleHog finding metadata;
- lists historical credential-like filenames for manual review.

Local output is written under `.public-readiness-scan/`, which is ignored by Git.

### TruffleHog Lob detector review note

TruffleHog v3.96.0's Lob detector matches `test_` followed by 35 alphanumeric/underscore characters and treats HTTP 422 from the Lob verification endpoint as evidence that a key is active. Python test function names can therefore be reported as verified Lob secrets even when they are ordinary identifiers.

The helper intentionally preserves the all-detector TruffleHog results for review, then performs a second cross-check excluding only the Lob detector so non-Lob findings remain independently visible. Lob findings must still be manually inspected and may not be dismissed solely because of detector type.

## Required gate before changing repository visibility

Before changing the repository from private to public:

1. Run the complete Git-history secret scan, including reachable branches, tags, and PR refs.
2. Confirm there are zero active/verified secrets in history after documented false-positive adjudication.
3. Investigate any historical credential-like filenames or scanner findings.
4. Revoke/rotate any real credential that was ever committed before making the repository public.
5. Re-review the final PR diff and confirm ordinary `pull_request` workflows do not reference production secrets or production resources.
6. After the repository becomes public, run the public-safe test workflow and trusted live validation separately before relying on subsequent scheduled collector evidence.

The visibility change itself is intentionally outside this PR.
