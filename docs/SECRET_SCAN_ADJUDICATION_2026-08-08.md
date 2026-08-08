# Secret scan adjudication — 2026-08-08

Two local full-history scans were completed before repository publication. The final re-run covered:

- reachable commits: 549
- reachable refs: 83
- GitHub PR refs fetched: yes
- Gitleaks 8.30.1: 0 findings; integrity PASS
- TruffleHog 3.96.0 all-detector scan: 7 findings, all reported as verified, all DetectorName=Lob
- TruffleHog 3.96.0 non-Lob cross-check: 0 findings; 0 verified; 0 unknown; scanner/sanitizer PASS
- sensitive-looking historical filenames: 1

## Lob finding adjudication

All seven Lob findings were reviewed by commit, file, and line. Each finding is an ordinary Python test function identifier that is exactly `test_` followed by 35 alphanumeric/underscore characters. One identifier was surfaced in two commits, accounting for two of the seven records.

TruffleHog v3.96.0's Lob detector regex matches `(live|test)_` followed by 35 alphanumeric/underscore characters. Its verifier treats HTTP 422 from the Lob API as evidence that a key is active. That combination causes these Python test identifiers to be reported as verified Lob secrets.

No Lob integration, Lob API endpoint, or Lob credential configuration is present in the repository. The second full-history TruffleHog pass excluded only the Lob detector and returned zero verified or unknown findings. These seven records are therefore adjudicated as detector false positives, not repository credentials.

## Historical filename adjudication

The sole sensitive-looking filename is `scripts/encode-service-account.sh`. The script accepts a local service-account JSON path and base64-encodes that local file to stdout. It does not contain an embedded service-account credential or private key.

## Gate result

**SECRET HISTORY GATE: PASS**

Evidence supporting the pass:

- all 549 reachable commits and 83 refs were included, including fetched GitHub pull-request head refs;
- Gitleaks found zero secrets and its scan-integrity guard passed;
- TruffleHog found zero non-Lob verified or unknown credentials;
- the seven Lob results were individually adjudicated as deterministic test-identifier false positives;
- the one credential-like historical filename contains no embedded credential.

No credential revocation, rotation, or Git history rewrite is required on the evidence reviewed here.

Repository visibility must still remain private until the final workflow/public-readiness review and Public-readiness PR merge are complete.
