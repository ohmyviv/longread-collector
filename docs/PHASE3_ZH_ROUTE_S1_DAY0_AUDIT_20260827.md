# Phase 3 — Chinese Route Shadow S1 Day-0 Audit

Audit target: `COL-20260827-224813-BJT-zh_midday`  
Audit date: 2026-08-28  
Audit contract: `zh-route-shadow-s1-audit-v1`  
Decision: **DAY-0 PASS / ELIGIBLE EXPOSURE**  
S1 overall: **EVIDENCE ACCUMULATION / NOT S2-READY**  
Production effect: **NONE**

## Executive decision

This natural run is the first valid post-activation prospective S1 exposure. The frozen Day-0 question is only whether the paired experiment executed correctly and left reconstructable evidence. On that question, L0–L3 all pass.

This does **not** mean S1 is complete, the routes are useful, or S2 is authorized. It means the experiment is technically valid and the naturally selected target sources receive their first eligible exposure:

- Yicai: eligible exposure #1 / technical observed;
- Jiemian-depth: eligible exposure #1 / technical observed;
- Caixin: eligible exposure #1 / technical observed;
- EEO: 0 eligible prospective exposures / not yet prospectively observed.

The 11:50 BJT scheduled slot started at 22:48:13 BJT. The 39,490-second scheduler delay is recorded as reliability telemetry; it does not invalidate the S1 paired experiment because the eventual run is natural, durable, post-activation and internally complete.

## L0 — Scheduler / cohort availability: PASS

- exact durable run count for `collector_run_id`: 1;
- query group: `zh_midday`;
- run started after S1 activation boundary `2026-08-27 16:24:01 BJT`;
- run was naturally scheduled, not a manual rerun;
- at least one S1 target source was naturally selected.

Naturally selected S1 target sources: `yicai`, `jiemian-depth`, `caixin`.

## L1 — Control validity: PASS

Durable Control evidence:

- `final_status=success`;
- `source_run_coverage_persisted=TRUE`;
- coverage version `run-source-coverage-v0.2`;
- run ledger declares 8 coverage rows and exactly 8 rows exist;
- `snapshot_persistence_status=success`;
- snapshot expected=177;
- snapshot persisted=177;
- snapshot readback=TRUE.

The matching `collector_v06_shadow_runs` row independently records:

- status=success;
- discovery snapshot=177;
- Control discovery snapshot=177;
- persisted snapshot=177;
- readback=TRUE;
- capture gap=0;
- full snapshot invariant=TRUE;
- Control acquired=24;
- shared body=24;
- body fingerprint mismatch=0;
- duplicate Shadow network invariant=TRUE;
- Shadow network requests=0;
- Shadow Firecrawl requests=0;
- Shadow incremental cost=0;
- Control result preserved=TRUE.

## L2 — Experimental isolation: PASS

Runtime-observable checks:

- Treatment rows occur only for naturally selected S1 target sources;
- all Treatment rows are `metadata_only`;
- Control extraction cap remains 32;
- observed Control body attempts=24 (`first_stage_attempts=16` + `second_stage_attempts=8`), therefore <=32;
- `native_source_cap=4` unchanged;
- `absolute_host_cap=4` unchanged;
- frozen static 21-surface Route Contract remains valid.

The following remain deliberately **not independently observable from the per-run route sidecar** and are therefore not claimed as Sheet-derived facts:

- Treatment `body_requests=0`;
- Treatment never enters candidate selection;
- Treatment never enters production `article_cache`.

They remain code/workflow regression invariants. The independent v0.6 Shadow summary nevertheless shows zero Shadow network / Firecrawl requests and preserved Control result.

## L3 — Telemetry integrity: PASS

Expected Treatment surfaces for the naturally selected targets:

- Yicai: 6;
- Jiemian-depth: 4;
- Caixin: 5;
- total: 15.

Persisted evidence:

- observation rows=15;
- route item rows=275;
- exactly one observation per expected surface;
- all observation/item rows foreign-key to the exact Control run;
- Route Contract version mismatches=0;
- Route Discovery version mismatches=0;
- body-mode mismatches=0;
- telemetry-version mismatches=0.

A separate deterministic spreadsheet recomputation from the 275 item rows reproduced, for all 15 surfaces, every persisted observation aggregate:

- raw / unique item count;
- recent count;
- dated count;
- exact-high timestamp count;
- Control overlap;
- Treatment unique;
- noise count and reason composition.

No aggregate mismatch and no item→parent surface mismatch were found.

## L4 — Route technical health: OBSERVE, not acceptance

Persisted surface states:

- `observed`: 5;
- `date_unknown`: 7;
- `stale_surface`: 3;
- `empty`: 0;
- `request_failed`: 0.

All 15 surface requests returned HTTP 200 and parsed successfully.

### Jieman-depth

All four surfaces are technically observable. `jiemian_medicine` shows 21/21 recent, dated and exact-high listing timestamps. Consumer and health surfaces also expose dates, although the S1 listing-time contract remains distinct from Final Recall publication-time evidence.

### Yicai

Finance / kechuang / auto and the two controls are largely `date_unknown`; breadth produced only one persisted recent timestamp. Listing anchor text itself contains forms such as `48分钟前`, `1小时前`, `3小时前`, while the current generic parser does not natively parse this relative-age form and may bind a later neighboring context instead.

### Caixin

Companies / finance / China were persisted as `stale_surface`; latest and promotion control were `date_unknown`. This classification is measurement-contaminated: many persisted article URLs encode `/2026-08-27/...` or `/2026-08-26/...`, while the generic listing context parser assigned `2026-08-02` or `2026-08-01`. The stale result must therefore not be interpreted as evidence that the Caixin route itself is stale.

## L5 — Route utility evidence: OBSERVE / TIMESTAMP-CONTAMINATED

Raw persisted item-ledger recomputation, before timestamp-confidence correction:

- route item rows: 275;
- unique canonical observed URLs: 248;
- canonical Control overlap: 8;
- canonical `within_freshness` under the persisted S1 timestamps: 40;
- canonical proven-recent Treatment incrementals under the persisted S1 timestamps: 40;
- explicit-noise canonical URLs among those persisted recent incrementals: 1.

These numbers are **not utility-grade evidence** for this exposure because current section timestamp binding is demonstrably contaminated on Caixin and shows an association risk on Yicai. They must not be used to claim route quality, S2 readiness, eligible/editable supply, or fixed-32 displacement value.

The known Jiemian gene-therapy miss appears on `jiemian_medicine` in this exposure with a listing timestamp, which is a useful regression observation only. It is not a tuning label and does not by itself justify route promotion.

## Timestamp measurement finding

The Day-0 run exposed a measurement-layer defect family:

1. **Caixin URL-date/context-date conflict** — first-party article URLs carry a current date path, but generic post-anchor context binding can attach an unrelated older date and false-classify the surface as stale.
2. **Yicai relative-age unmodeled / context borrowing risk** — anchor text includes `N分钟前/N小时前`, while the current parser does not model that form and can either leave the item unknown or attach neighboring clock text.

Because L4/L5 are descriptive layers, these defects do not invalidate L0–L3 Day-0 acceptance. They do block timestamp-derived utility interpretation until measured separately.

A read-only timestamp forensic module is being added separately. It is intentionally not wired into Treatment discovery: it detects persisted URL-date conflicts and relative-age binding conflicts/available-but-unbound evidence without changing Control or Treatment behavior.

## Next evidence rules

1. Every later eligible natural run remains independently audited; no future success can mask this run and no future failure can retroactively invalidate this Day-0 PASS.
2. Source maturity advances by eligible exposure, not raw run count.
3. Timestamp-derived L4/L5 utility metrics remain guarded until the conflict family is understood or a separately reviewed measurement-contract change is introduced.
4. EEO still needs its first natural eligible exposure.
5. No Route expansion, source/cap/budget change, S2 body acquisition, Editor connection, production wiring or auto-promotion follows from Day-0.

## Final status

**S1 Day-0:** PASS for `COL-20260827-224813-BJT-zh_midday`.  
**Eligible exposures:** Yicai=1, Jiemian-depth=1, Caixin=1, EEO=0.  
**S1 overall:** active evidence accumulation; technical repeatability not yet established.  
**S2 readiness:** NOT ESTABLISHED / NOT AUTHORIZED.  
**Production posture:** SHADOW / NOT_READY, unchanged.
