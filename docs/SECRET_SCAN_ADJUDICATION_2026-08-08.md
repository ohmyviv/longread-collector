# Secret scan adjudication — 2026-08-08

Initial local full-history scan before repository publication:

- reachable commits: 546
- reachable refs: 83
- GitHub PR refs fetched: yes
- Gitleaks 8.30.1: 0 findings; integrity PASS
- TruffleHog 3.96.0: 7 findings, all reported as verified, all DetectorName=Lob
- sensitive-looking historical filenames: 1

## Lob finding adjudication

All seven Lob findings were reviewed by commit, file, and line. Each finding is an ordinary Python test function identifier that is exactly `test_` followed by 35 alphanumeric/underscore characters. One identifier was surfaced in two commits, accounting for two of the seven records.

TruffleHog v3.96.0's Lob detector regex matches `(live|test)_` followed by 35 alphanumeric/underscore characters. Its verifier treats HTTP 422 from the Lob API as evidence that a key is active. That combination causes these Python test identifiers to be reported as verified Lob secrets.

No Lob integration, Lob API endpoint, or Lob credential configuration is present in the repository. These seven findings are therefore adjudicated as detector false positives, subject to a second TruffleHog cross-check excluding only the Lob detector.

## Historical filename adjudication

The sole sensitive-looking filename is `scripts/encode-service-account.sh`. The script accepts a local service-account JSON path and base64-encodes that local file to stdout. It does not contain an embedded service-account credential or private key.

## Remaining gate

Re-run the updated helper and confirm:

- Gitleaks remains 0 findings with integrity PASS;
- TruffleHog non-Lob cross-check reports 0 verified/unknown findings;
- scanner execution and sanitizer integrity pass.

Do not change repository visibility until that re-run and the final workflow review are complete.
