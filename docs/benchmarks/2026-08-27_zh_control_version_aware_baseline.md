# Chinese Control version-aware baseline — 2026-08-27

Status: **read-only historical anomaly baseline**  
Evidence source: live `collector_runs` ledger, natural Chinese runs only  
Window: 2026-08-19 through 2026-08-26 BJT  
Causal role: **NONE — same-run paired Control remains the only causal comparator for S1 Treatment**

## 1. Why this baseline exists

This baseline answers only one question:

> When a future S1 paired run appears unusual, is the Control side itself outside the recent operating range?

It must never be used as a substitute for same-run Control/Treatment comparison. A high Treatment incremental count on a day when Control itself is abnormally weak should be interpreted cautiously, but historical medians do not become the counterfactual Control.

## 2. Version boundary

The selected window starts on 2026-08-19 because it is the first late-Phase-2 Chinese window in which the relevant Control semantics are broadly stable enough for operational anomaly context:

- `source_run_coverage_version=run-source-coverage-v0.2`;
- durable snapshot persistence/readback markers are present;
- current 32-attempt staged-reserve semantics are present;
- extraction is on the late v0.5.6m-g1 path from 2026-08-19 onward.

A narrower boundary applies to publication-time observability:

- `section_publication_time_version=section-publication-time-observability-v0.2` appears from 2026-08-20 onward;
- therefore section-time observability statistics must not pool 2026-08-19 with 2026-08-20+ as if the evidence contract were identical.

The baseline is intentionally descriptive. It does not invent anomaly thresholds from this small sample.

## 3. Scheduler denominator

There are **15**, not 16, natural Chinese runs in the eight-day window.

2026-08-23 has a natural `zh_midday` run but no durable `zh_evening` Collector run. That missing scheduled opportunity is scheduler availability evidence, not a zero-output Control run.

This is the same denominator principle used by S1 L0:

> no durable run = `NOT_EVALUABLE`, not performance failure.

## 4. Run-level baseline

| Date | Group | URLs discovered | Native metadata items | Body attempts | Valid extractions | Eligible for editor | Start delay (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-08-19 | zh_midday | 221 | 197 | 32 | 31 | 14 | 1927 |
| 2026-08-19 | zh_evening | 188 | 160 | 31 | 29 | 17 | 1351 |
| 2026-08-20 | zh_midday | 186 | 158 | 29 | 23 | 10 | 1931 |
| 2026-08-20 | zh_evening | 369 | 345 | 32 | 31 | 18 | 1461 |
| 2026-08-21 | zh_midday | 210 | 182 | 32 | 29 | 16 | 2065 |
| 2026-08-21 | zh_evening | 241 | 216 | 32 | 32 | 19 | 1472 |
| 2026-08-22 | zh_midday | 207 | 173 | 32 | 30 | 17 | 1668 |
| 2026-08-22 | zh_evening | 169 | 144 | 26 | 26 | 16 | 752 |
| 2026-08-23 | zh_midday | 359 | 332 | 32 | 29 | 7 | 2032 |
| 2026-08-24 | zh_midday | 194 | 168 | 25 | 25 | 11 | 2428 |
| 2026-08-24 | zh_evening | 193 | 168 | 32 | 28 | 17 | 2029 |
| 2026-08-25 | zh_midday | 198 | 173 | 31 | 26 | 17 | 2093 |
| 2026-08-25 | zh_evening | 219 | 195 | 32 | 31 | 17 | 1560 |
| 2026-08-26 | zh_midday | 342 | 309 | 32 | 29 | 14 | 2127 |
| 2026-08-26 | zh_evening | 208 | 170 | 27 | 27 | 18 | 1805 |

`Body attempts = first_stage_attempts + second_stage_attempts` from the durable run audit markers.

## 5. Descriptive operating ranges

### All 15 natural Chinese runs

| Metric | Median | Range | Mean |
|---|---:|---:|---:|
| URLs discovered | 208 | 169–369 | 233.6 |
| Native metadata items | 173 | 144–345 | 206.0 |
| Body attempts | 32 | 25–32 | 30.5 |
| Valid extractions | 29 | 23–32 | 28.4 |
| Eligible for editor | 17 | 7–19 | 15.2 |
| Start delay seconds | 1927 | 752–2428 | 1780.1 |

### `zh_midday` only — n=8

| Metric | Median | Range |
|---|---:|---:|
| URLs discovered | 208.5 | 186–359 |
| Native metadata items | 177.5 | 158–332 |
| Body attempts | 32 | 25–32 |
| Valid extractions | 29 | 23–31 |
| Eligible for editor | 14 | 7–17 |
| Start delay seconds | 2048.5 | 1668–2428 |

### `zh_evening` only — n=7

| Metric | Median | Range |
|---|---:|---:|
| URLs discovered | 208 | 169–369 |
| Native metadata items | 170 | 144–345 |
| Body attempts | 32 | 26–32 |
| Valid extractions | 29 | 26–32 |
| Eligible for editor | 17 | 16–19 |
| Start delay seconds | 1472 | 752–2029 |

## 6. What may be compared prospectively

For a future post-S1 natural run, these metrics are useful as **contextual anomaly signals** when the underlying Control semantics remain compatible:

- selected-source count;
- URLs discovered;
- native metadata item count;
- body attempts under the fixed 32-attempt contract;
- valid extraction count;
- editor-eligible count;
- run start delay;
- source-level native/fallback status under the same coverage contract.

They should be read by group (`zh_midday` vs `zh_evening`) where practical because the recent distributions differ, especially in editor-eligible output and scheduler delay.

## 7. What must not be pooled blindly

Do not pool across a semantic boundary merely because the column name is unchanged.

Examples:

- pre- and post-`section-publication-time-observability-v0.2` timestamp observability;
- pre- and post-reliability-hardening failure rates (#132 / #135);
- any future Control route or selection semantic version change;
- S1 Treatment telemetry and historical Control discovery counts as if they were generated by the same mechanism.

If a future semantic change affects a metric, start a new baseline cohort rather than extending this table.

## 8. Interpretation examples

A future paired run with low Treatment incremental supply is not automatically a poor Treatment route if Control itself already observed unusually broad coverage that day.

Conversely, a high Treatment incremental count deserves caution if the same-run Control is abnormally weak relative to its recent group-specific context.

The correct sequence remains:

1. same-run S1 L0–L3 evidence qualification;
2. same-run Control/Treatment comparison;
3. historical baseline only as anomaly context;
4. repeated eligible exposures before any S2 decision.

No production parameter, route, cap, budget or editorial policy is implied by this baseline.
