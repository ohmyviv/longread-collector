# Phase 3 Chinese Route S1 Natural Audit — intended 2026-08-29 zh_midday

## Status

**Eligible prospective S1 exposure / L0-L3 PASS**

This is a read-only evidence record for the natural scheduled Collector run. It does not rerun Discovery, change Route Treatment, change source/cap/body budgets, alter Scheduler semantics, start S2/S3, wire Editor, or change production.

## Run identity and scheduler evidence

Durable Collector run:

`COL-20260829-182701-BJT-zh_midday`

- intended schedule: 2026-08-29 11:50:00 BJT
- GitHub Actions scheduled run: `33247829472`
- Actions run created: 2026-08-29 18:26:32 BJT
- Collector started: 2026-08-29 18:27:01 BJT
- Collector completed: 2026-08-29 18:29:11 BJT
- `start_delay_seconds=23819` (~6.62h)
- final status: success

Collector startup occurred ~29 seconds after GitHub created the scheduled run, so almost the entire multi-hour delay again occurred upstream of repository execution. This evidence was added to Issue #142; no scheduler change is made here.

## L0 — Scheduler availability / cohort identity

**PASS**

- natural scheduled `zh_midday` run exists;
- intended date = 2026-08-29, after S1 prospective activation;
- durable run id is unique;
- run completed successfully.

The severe scheduling delay affects operational timeliness but does not by itself invalidate same-run paired S1 evidence.

## L1 — Control validity

**PASS**

Collector facts:

- URLs discovered: 198
- URLs new: 17
- body acquisition budget consumed: 32
- final status: success

`collector_source_run_coverage` contains exactly 8 selected source rows, all persisted with `run-source-coverage-v0.2`.

`collector_v06_shadow_runs` independently corroborates:

- status = success
- Discovery snapshot = 198
- Control Discovery snapshot = 198
- persisted snapshot = 198
- snapshot readback = TRUE
- capture gap = 0
- full snapshot invariant = TRUE
- Control acquired/shared body = 32/32
- body fingerprint mismatches = 0
- zero duplicate network invariant = TRUE
- Shadow requests = 0
- Shadow Firecrawl requests = 0
- Shadow incremental cost = 0
- Control result preserved = TRUE

Therefore the paired Control is valid and durable.

## L2 — Experimental isolation

**PASS**

Naturally selected sources were:

- yicai
- jiemian-depth
- latepost
- zaobao-depth
- caijing
- caixin
- bbc-zh
- chinadevelopmentbrief

Naturally selected S1 target sources were therefore:

- **Yicai**
- **Jiemian-depth**
- **Caixin**

EEO was not selected and correctly generated no Treatment exposure.

All Route Treatment observations for the three selected target sources remained:

- `body_mode=metadata_only`
- route contract `zh-route-shadow-contract-v1`
- route discovery `zh-route-shadow-discovery-v1`
- telemetry `zh-route-shadow-telemetry-v1`

The v0.6 summary confirms zero Shadow body/network/Firecrawl requests and zero incremental cost. Natural Control body attempts remained at the frozen 32 cap.

## L3 — Telemetry integrity

**PASS**

Expected Route surfaces from the frozen portfolio:

- Yicai = 6
- Jiemian-depth = 4
- Caixin = 5
- total expected = **15**

Persisted `collector_route_shadow_observations` rows = **15**, exactly matching expectation.

All 15 observations:

- request success = TRUE
- HTTP status = 200
- parse success = TRUE
- correct run FK
- correct source/surface identity
- correct contract/discovery/body-mode/telemetry versions

Observation unique-item totals reconcile exactly to the item ledger:

- Yicai = 108
- Jiemian-depth = 73
- Caixin = 95
- total = **276**

Persisted `collector_route_shadow_items` for this run = **276**.

A temporary apparent 275/276 version mismatch was investigated and closed. A scoped Sheet search over `A873:Z1148` initially treated row 873 as an implicit header because the range did not contain the real worksheet header, thereby excluding one valid item from the match count. Repeating the four checks with `header_row=null` produced **276/276** matches for:

- `zh-route-shadow-contract-v1`
- `zh-route-shadow-discovery-v1`
- `metadata_only`
- `zh-route-shadow-telemetry-v1`

This was a query-boundary artifact, not a telemetry defect.

## L4 — Descriptive Route health

**OBSERVE; technically healthy**

### Yicai

Six surfaces all requested and parsed successfully:

- finance: 20 unique, Control overlap 2
- kechuang: 20 unique, overlap 0
- auto: 16 unique, overlap 2
- news breadth: 24 unique, overlap 8
- info control: 16 unique, overlap 0
- commercial control: 12 unique, overlap 0, all 12 correctly tagged commercial noise

Treatment-unique total by observation = 96.

The persisted v1 timestamp fields still leave most Yicai section rows date-unknown even though titles expose relative/listing clock evidence. This is a timestamp-measurement issue, not a route-request failure.

### Jiemian-depth

Four surfaces all requested and parsed successfully:

- medicine: 21/21 recent and exact under persisted listing evidence
- consumer: 16 recent of 20, all 20 dated/exact
- health_face: 3 recent of 16, all 16 dated/exact
- health: 3 recent of 16, all 16 dated/exact

Total = 73 unique items, zero same-run Control overlap.

Jiemian remains the cleanest timestamp-observable source in the portfolio.

### Caixin

Five surfaces all requested and parsed successfully, 95 unique items total. However, the known timestamp-binding defect persists on core section surfaces: first-party URLs visibly encode dates such as `/2026-08-29/` and `/2026-08-28/`, while persisted `published_at` is repeatedly `2026-08-02`. The resulting `stale_surface` labels are therefore measurement-contaminated and must not be interpreted as true source staleness.

Caixin promotion control continues to be isolated as commercial noise.

## L5 — Utility interpretation

**DESCRIPTIVE ONLY / no new promotion decision**

This run strengthens technical evidence but does not independently solve body utility or acquisition observability.

- Jiemian and Yicai were already source-specifically `S2_READY_FOR_REVIEW` before this run; this natural exposure strengthens repeatability but does not reopen or overwrite S2-B v1.
- S2-B v1 remains formally `CLOSED / NOT_EVALUABLE_FOR_SOURCE_UTILITY / ACQUISITION-CENSORED`.
- Caixin gains a second eligible S1 exposure but remains **NOT S2-ready**, because timestamp conflict/utility evidence is not yet sufficient.
- EEO receives no new exposure because it was not naturally selected.

No L5 rate should be computed from contaminated v1 timestamp labels for Caixin, and no body-value inference should be made from S1 metadata-only Treatment.

## Exposure ledger update

After this valid intended-2026-08-29 run:

- Yicai: **5 eligible exposures**
- Jiemian-depth: **5 eligible exposures**
- Caixin: **2 eligible exposures**
- EEO: **1 eligible exposure**

Yicai and Jiemian now have valid technical evidence across at least **three distinct intended schedule dates** (2026-08-27, 2026-08-28, 2026-08-29). This strengthens the conclusion that their S1 technical behavior is repeatable across intended dates, while operational wall-clock timeliness remains unproven because the scheduler continues to dispatch hours late.

Caixin now has two eligible exposures across distinct intended dates, but exposure count alone does not establish utility readiness.

## Decision boundary

No system modification follows from this run.

- S1 remains an evidence-accumulation / measurement program.
- Jiemian/Yicai source-specific review status remains unchanged.
- Caixin and EEO remain below S2-readiness.
- S2-B v2 body-observability execution remains **NOT AUTHORIZED**.
- Track F production-acquisition feasibility remains a separate future decision.
- S3 remains **NOT_AUTHORIZED / NOT_STARTED**.
- Production remains **SHADOW / NOT_READY**.
- Scheduler reliability remains a separate operational blocker under Issue #142.
