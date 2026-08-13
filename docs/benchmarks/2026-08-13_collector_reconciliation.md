# 2026-08-13 Collector benchmark-window reconciliation

> Phase 0 audit artifact. This document reconciles the independent High-reasoning editorial rerun against Collector run/snapshot evidence available before the scheduled daily editor started. It changes no runtime behavior, schema, L4/L5/L6 semantics, network budget, or promotion state.

## 1. Benchmark contract

Scheduled editorial run:

```text
run_id: LR-20260813-0735-BJT-LRv35
started_at_bj / cutoff: 2026-08-13 07:35:00
```

Use the existing final-recall convention for the immutable snapshot window:

```text
lookback_start: 2026-08-11 07:35:00 BJT
cutoff:         2026-08-13 07:35:00 BJT
window:         48 hours
```

The audit has two denominators:

1. **editorial-anchor coverage** — manual selected/strong items that existed by cutoff, regardless of whether the source is already in Collector registry;
2. **effective-route promotion denominator** — pre-cutoff anchor items whose source is registered and has an effective Collector route. Outside-registry items remain explicit source-coverage gaps but should not be silently counted as route failures.

The manual rerun produced 8 selected + 5 strong-rejected anchor items. One strong item (the Tencent/第一财经 article) was published at 2026-08-13 07:47:06, after the 07:35 cutoff, so all 13 are reconciled but only 12 are pre-cutoff editorial anchors.

## 2. Authoritative Collector run window

Eight Collector runs completed in the 48-hour benchmark window:

| # | collector_run_id | completed_at_bj | query_group | urls_discovered | eligible_for_editor | persisted snapshot rows |
|---|---|---:|---|---:|---:|---:|
| 1 | `COL-20260811-125504-BJT-zh_midday` | 2026-08-11 13:01:52 | zh_midday | 289 | 16 | 289 |
| 2 | `COL-20260811-183734-BJT-zh_evening` | 2026-08-11 18:42:16 | zh_evening | 111 | 18 | 111 |
| 3 | `COL-20260811-232745-BJT-intl_early` | 2026-08-11 23:34:25 | intl_early | 207 | 25 | 207 |
| 4 | `COL-20260812-042957-BJT-pre_report` | 2026-08-12 04:37:30 | pre_report | 186 | 28 | **0 — missing snapshot** |
| 5 | `COL-20260812-131915-BJT-zh_midday` | 2026-08-12 13:23:18 | zh_midday | 172 | 10 | 172 |
| 6 | `COL-20260812-184527-BJT-zh_evening` | 2026-08-12 18:52:55 | zh_evening | 69 | 10 | 69 |
| 7 | `COL-20260812-232742-BJT-intl_early` | 2026-08-12 23:30:32 | intl_early | 123 | 19 | 123 |
| 8 | `COL-20260813-042803-BJT-pre_report` | 2026-08-13 04:36:01 | pre_report | 143 | 14 | 143 |

Run-reported raw discovery observations:

```text
1300
```

Persisted immutable snapshot observations:

```text
1114 / 1300 = 85.7%
```

The entire 186-row discovery snapshot for `COL-20260812-042957-BJT-pre_report` is absent. Its `article_cache` writes do exist: 32 cache rows are attributable to that run. Therefore the authoritative benchmark evidence is:

```text
collector_runs
  + persisted discovery snapshots for 7/8 runs
  + article_cache recovery evidence for the missing-snapshot run
```

This is an observability gap, not permission to reconstruct or fabricate the missing 186 snapshot rows.

## 3. Source/route facts

| Source | Registry | Native/effective evidence | Last confirmed source scan before cutoff |
|---|---|---|---|
| ProPublica | registered/enabled | RSS works | 2026-08-12 04:37 BJT |
| The Atlantic | registered/enabled | RSS works | 2026-08-12 04:37 BJT |
| Quanta Magazine | registered/enabled | RSS works | 2026-08-12 04:37 BJT |
| 每日经济新闻 (NBD) | **outside registry** | no Collector-native route; no `article_cache` rows found | none |
| 第一财经 | registered/enabled | effective runtime evidence includes `section_scan` | 2026-08-11 18:42 BJT |
| 界面新闻·界面深度 | registered/enabled | `section_scan` works | 2026-08-12 13:23 BJT |

Persisted snapshot search across the 7 available snapshot blocks found no target-domain rows at all for ProPublica, The Atlantic, Quanta, or NBD. 第一财经 and 界面新闻 had many snapshot rows in the window, but none of the target URLs below appeared. Exact target URLs were also absent from `article_cache`.

## 4. Per-item funnel reconciliation

Legend:

```text
POST_CUTOFF
OUTSIDE_REGISTRY_NO_ROUTE
NOT_SCHEDULED_AFTER_PUBLICATION
OBSERVABILITY_AMBIGUOUS
```

The funnel stop is deliberately placed at the earliest stage supported by evidence. No target is blamed on Acquisition/L4/L5 when it never entered the target URL universe.

| # | Manual bucket | Source / article | Cutoff status | Registry/route | Snapshot/cache target match | Earliest supported stop | Reconciliation |
|---|---|---|---|---|---|---|---|
| 1 | selected | ProPublica — artillery factory | pre-cutoff | registered; RSS | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Last scan 8/12 04:37 BJT; article published 8/12 06:00 US Eastern (~18:00 BJT); later intl/pre-report runs did not rescan ProPublica before cutoff. |
| 2 | selected | Quanta — fractal uncertainty principle | pre-cutoff at current date-granularity | registered; RSS | none | discovery/snapshot observability | **OBSERVABILITY_AMBIGUOUS**. Page exposes 8/12 date but not exact publication time. Quanta was scanned at 8/12 04:37, but that run's full snapshot is missing. Cannot prove whether the URL was never in the feed at scan time or was captured then lost before cache. |
| 3 | selected | The Atlantic — testosterone decline | pre-cutoff | registered; RSS | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Last scan 8/12 04:37 BJT; article published 8/12 07:07 ET (~19:07 BJT); no later Atlantic source scan before cutoff. |
| 4 | selected | NBD — Tsimerman/OpenAI interview | pre-cutoff | **outside registry** | none | source coverage | **OUTSIDE_REGISTRY_NO_ROUTE**. Published 8/11 11:08 BJT; no registered NBD route and no NBD cache evidence. |
| 5 | selected | NBD — Shanghai river/flood resilience | pre-cutoff | **outside registry** | none | source coverage | **OUTSIDE_REGISTRY_NO_ROUTE**. No registered NBD route and no NBD cache evidence. |
| 6 | selected | 第一财经 — only-child parents/eldercare | pre-cutoff | registered | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Last confirmed Yicai scan was 8/11 18:42; article dated 8/12; no later Yicai scan before cutoff. |
| 7 | selected | 第一财经 — Rhine low water | pre-cutoff | registered | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Same route-cadence gap as item 6. |
| 8 | selected | 界面新闻 — low-cost compute network | pre-cutoff | registered; section_scan | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Jiemian scan at 8/12 13:23; article published 8/12 15:09; later zh_evening/pre-report runs did not rescan this source before cutoff. |
| 9 | strong_rejected | ProPublica — Tennessee juvenile prisons | pre-cutoff | registered; RSS | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Last scan 8/12 04:37 BJT; article published 8/12 05:00 US Eastern (~17:00 BJT); no later ProPublica source scan before cutoff. |
| 10 | strong_rejected | The Atlantic — AI panic | pre-cutoff | registered; RSS | none | source scheduling / freshness | **NOT_SCHEDULED_AFTER_PUBLICATION**. Published 8/12 16:05 ET = 8/13 04:05 BJT; the 8/13 04:28 pre-report run occurred after publication but Atlantic was not selected/rescanned. |
| 11 | strong_rejected | NBD — Wenfeng equity dispute | pre-cutoff | **outside registry** | none | source coverage | **OUTSIDE_REGISTRY_NO_ROUTE**. No registered NBD route and no NBD cache evidence. |
| 12 | strong_rejected | NBD — Insta360/DJI interview | pre-cutoff | **outside registry** | none | source coverage | **OUTSIDE_REGISTRY_NO_ROUTE**. No registered NBD route and no NBD cache evidence. |
| 13 | strong_rejected | 第一财经 — Tencent Q2 AI capex | **post-cutoff** | registered | none required | benchmark availability | **POST_CUTOFF**. First财经 timestamp is 2026-08-13 07:47:06, 12 minutes after the 07:35 editor cutoff. Reconcile it, but exclude it from pre-report recall denominators. |

## 5. Aggregate diagnosis

All 13 manual anchors are reconciled. At the 07:35 cutoff:

```text
13 total manual selected/strong anchors
- 1 post-cutoff article
= 12 pre-cutoff editorial anchors

12 pre-cutoff anchors:
  4 outside-registry / no-route (all NBD)
  7 registered but not rescanned after publication
  1 Quanta timing/snapshot-observability ambiguous
  0 proven acquisition failures
  0 proven L4 failures
  0 proven L5/editorial failures after target capture
```

Under the existing promotion-denominator concept:

```text
pre-cutoff registered/effective-route anchors: 8
known target URLs captured into snapshot/cache: 0
anchor effective-route recall: 0/8 for this case
```

This 0/8 is a single-day anchor diagnostic, not a promotion metric by itself.

The more important causal result is that the observed loss is overwhelmingly **before target acquisition**:

```text
source coverage
  -> source scheduling / rotation freshness
  -> discovery capture
```

There is no evidence in this anchor case that parser/body acquisition, L4 canonicalization, or frozen L5 is the primary bottleneck.

## 6. Phase-0 conclusions and first repair targets

Priority order should change accordingly:

1. **Snapshot completeness invariant** — a Collector run reporting discoveries must not silently lack its immutable discovery snapshot. Repair/alert this control-plane failure first because it prevents trustworthy attribution.
2. **Source registry coverage** — decide whether NBD is an approved core source; if yes, add it through a dedicated Discovery/config PR with first-party routes and tests. Do not hide the gap by counting it as an extractor failure.
3. **Scheduling/rotation freshness** — registered high-value sources can go >24h without a post-publication scan. Add measurable source-age/SLA logic before adding another generic crawler.
4. **Route quality** — for Yicai/Jiemian and other first-party surfaces, measure whether the existing section/sitemap/feed route exposes current article URLs soon enough. Enhance route coverage only after cadence is corrected/measured.
5. **Do not touch L4/L5 for this RCA** — this benchmark provides no evidence that PR-7.3 L4 semantics or frozen PR-7.2 L5 caused these 12 misses.

Suggested next implementation slice:

```text
Phase 0A: snapshot-persistence invariant + audit test
Phase 0B: source freshness / last-successful-scan observability and scheduler diagnosis
Phase 0C: NBD registry decision + source-specific route fixture
```

Keep Collector `SHADOW`; no promotion decision should be made from this one benchmark day.
