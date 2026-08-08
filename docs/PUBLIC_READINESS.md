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

Action artifacts produced by collector/live-validation workflows use a 7-day retention window in the workflows touched by the Public-readiness change.

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
- performs a second TruffleHog pass excluding only the Lob detector so known Lob false positives can be independently bounded;
- writes only sanitized TruffleHog finding metadata;
- lists historical credential-like filenames for manual review.

Local output is written under `.public-readiness-scan/`, which is ignored by Git.

The 2026-08-08 adjudication is recorded in `docs/SECRET_SCAN_ADJUDICATION_2026-08-08.md`.

## Pre-public gate result — 2026-08-08

**SECRET HISTORY GATE: PASS**

Final local full-history evidence:
- 549 reachable commits;
- 83 reachable refs, including fetched GitHub PR heads;
- Gitleaks 8.30.1: 0 findings; integrity PASS;
- TruffleHog 3.96.0 non-Lob pass: 0 verified/unknown findings;
- seven all-detector Lob results individually adjudicated as deterministic Python test-identifier false positives;
- one sensitive-looking historical filename reviewed and found to contain no embedded credential.

**WORKFLOW TRUST-BOUNDARY GATE: PASS**

Final workflow review confirms:
- only `tests.yml` is triggered by ordinary `pull_request`;
- the PR workflow has `contents: read` and does not reference repository secrets, Google Sheet access, or paid/live validation credentials;
- workflows that reference Google/Jina/Firecrawl secrets are restricted to trusted manual, scheduled, or main-repository branch events;
- no `pull_request_target` workflow is present;
- collector schedules and v0.6 shadow safety flags remain unchanged.

**GITHUB-HOSTED CI: DEFERRED UNTIL PUBLIC**

The private repository remains blocked before runner allocation by the existing GitHub Billing/Spending Limit condition. No pytest step starts. This is infrastructure failure, not a test assertion failure. After visibility changes to public, immediately rerun the public-safe test workflow and then run trusted live validation separately.

## Remaining steps

1. Merge the Public-readiness hardening PR.
2. Change repository visibility from private to public.
3. Confirm the public-safe `Collector tests` workflow actually starts and passes.
4. Run trusted live validation separately.
5. Rely only on subsequent naturally scheduled collector runs for Natural Acceptance evidence; do not count manual validation runs.

The visibility change itself is intentionally outside the Public-readiness PR.
