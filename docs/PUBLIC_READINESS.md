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

## Required gate before changing repository visibility

Before changing the repository from private to public:

1. Scan the complete Git history, including all reachable branches and tags, with at least one dedicated secret scanner (preferably Gitleaks plus TruffleHog cross-check).
2. Confirm there are zero active/verified secrets in history.
3. Investigate any historical credential-like filenames or scanner findings.
4. Revoke/rotate any real credential that was ever committed before making the repository public.
5. Re-review the final PR diff and confirm ordinary `pull_request` workflows do not reference production secrets or production resources.
6. After the repository becomes public, run the public-safe test workflow and trusted live validation separately before relying on subsequent scheduled collector evidence.

The visibility change itself is intentionally outside this PR.
