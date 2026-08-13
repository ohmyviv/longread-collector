# 2026-08-13 Phase 0B source freshness measurement

## Purpose and boundary

Phase 0B measures why registered first-party sources can publish strong articles after a successful Collector scan yet remain unseen by the next daily-report cutoff.

This is a Discovery scheduling / source-revisit analysis only. It does **not** authorize changes to L4, frozen L5, L6, Acquisition/network budgets, Collector promotion, or a second generic crawler.

Phase 0A is already naturally accepted. Durable Discovery snapshots are therefore treated as trustworthy run evidence for this measurement.

---

## 1. Two different freshness clocks

Phase 0B must keep two clocks separate:

```text
A. workflow execution freshness
   configured scheduled_at
        -> GitHub Actions / Collector actual start

B. source revisit freshness
   source scan
        -> article publication
        -> next source scan
        -> report cutoff
```

A delayed GitHub workflow can amplify a freshness problem, but it is not the same failure as a source not being selected for a later run.

### Recent workflow start delay

From `collector_runs` for the natural scheduled runs spanning 2026-08-11 through the first post-Phase-0A run on 2026-08-13:

```text
run/query_group                         scheduled   actual start   delay
2026-08-11 pre_report                   03:57       04:27:38       1836 s
2026-08-11 zh_midday                    11:50       12:55:04       3902 s
2026-08-11 zh_evening                   17:50       18:37:34       2853 s
2026-08-11 intl_early                   22:30       23:27:45       3463 s
2026-08-12 pre_report                   03:57       04:29:57       1975 s
2026-08-12 zh_midday                    11:50       13:19:15       5353 s
2026-08-12 zh_evening                   17:50       18:45:27       3325 s
2026-08-12 intl_early                   22:30       23:27:42       3460 s
2026-08-13 pre_report                   03:57       04:28:03       1861 s
2026-08-13 zh_midday                    11:50       13:23:32       5610 s
2026-08-13 zh_evening                   17:50       18:47:10       3428 s
```

Observed delay summary:

```text
median: 3428 s  ~= 57m08s
mean:   3370 s  ~= 56m10s
p90:    5353 s  ~= 89m13s
max:    5610 s  =  93m30s
```

This is operationally material and should remain observable, but it does not explain the benchmark misses by itself. Several benchmark articles were already published before a later Collector run actually started, yet their source was not selected in that run.

---

## 2. Current source-selection contract

The active workflow provides two English-oriented and two Chinese-oriented natural Collector opportunities per day:

```text
22:30  intl_early
03:57  pre_report
11:50  zh_midday
17:50  zh_evening
```

The active Sheet config is:

```text
native_source_scans_per_run = 8
```

The config note itself describes the intended behavior as approximately two days to cover the formal source pool.

`select_sources_for_run()` is explicitly a least-recently-scanned selector with tier quotas and same-day avoidance. In summary:

```text
1. exclude disabled / monitor sources
2. prefer sources not scanned on the current calendar day
3. sort by oldest last_scanned_at_bj
4. with max_sources=8 and rotate_share=0.75:
     rotate quota ~= 6
     explore quota ~= 2
5. fill any remaining slots by oldest eligible source
```

The same-day rule is especially important: when at least eight not-yet-scanned-today sources exist, a source scanned earlier that day is excluded from the pool even if it publishes a new article minutes later.

---

## 3. Capacity math: the current policy is coverage-oriented, not report-freshness-oriented

Current enabled registry size at measurement time:

```text
English enabled sources: 29
Chinese enabled sources: 34
```

With two runs per language per day and eight native source scans per run:

```text
English native source slots/day = 16
29 / 16 ~= 1.81 days for one complete pass

Chinese native source slots/day = 16
34 / 16 ~= 2.13 days for one complete pass
```

The tier quota makes a universal sub-24-hour guarantee even less feasible. With roughly six `rotate` slots per run, only about twelve rotate-source scans are available per language per day. The active rotate pools are materially larger than twelve.

Therefore:

> Under the current fixed eight-source budget, a <24h revisit SLA for every enabled or every `rotate` source is mathematically impossible.

This means the observed 1-2 day revisit interval is not merely an accidental scheduler anomaly. It is a structural consequence of the current coverage-oriented policy.

---

## 4. 2026-08-13 anchor: article-level source-revisit evidence

The benchmark reconciliation identified seven pre-cutoff strong/selected anchors classified as `NOT_SCHEDULED_AFTER_PUBLICATION`. Phase 0B now explains that class more precisely.

### ProPublica — artillery factory

```text
last source scan before publication: 2026-08-12 04:37 BJT
article published:                   ~2026-08-12 18:00 BJT
later runs before report cutoff:
  2026-08-12 23:27 intl_early        ProPublica not selected
  2026-08-13 04:28 pre_report        ProPublica not selected
report cutoff:                       2026-08-13 07:35 BJT
```

The first-party ProPublica RSS route was healthy; the source simply did not receive another scan after publication and before cutoff.

### ProPublica — juvenile prisons investigation

```text
last source scan before publication: 2026-08-12 04:37 BJT
article published:                   ~2026-08-12 17:00 BJT
later intl_early / pre_report runs:  ProPublica not selected
report cutoff:                       2026-08-13 07:35 BJT
```

Same failure mode as above.

### The Atlantic — testosterone

```text
last source scan before publication: 2026-08-12 04:37 BJT
article published:                   ~2026-08-12 19:07 BJT
later intl_early / pre_report runs:  Atlantic not selected
report cutoff:                       2026-08-13 07:35 BJT
```

The Atlantic RSS route was healthy; no post-publication source scan occurred before cutoff.

### The Atlantic — AI panic

This is the cleanest demonstration that workflow timing is not the primary cause:

```text
article published:                   2026-08-13 04:05 BJT
pre_report actual start:             2026-08-13 04:28 BJT
```

The Collector began about 23 minutes after publication, but Atlantic was still not selected because older sources were ahead of it in the source-rotation queue.

### 界面新闻 / Jiemian — low-cost compute network

```text
Jiemian scan:                        2026-08-12 13:23 BJT
article published:                   2026-08-12 15:09 BJT
zh_evening actual start:             2026-08-12 18:45 BJT
Jiemian in that run:                 not selected
next confirmed Jiemian scan:         2026-08-13 18:50:41 BJT
```

Actual article-publication -> next-source-scan lag:

```text
~27h41m
```

The same-day avoidance rule is directly relevant here: Jiemian had already been scanned earlier on 2026-08-12, so later same-day sources were preferred even though a benchmark-quality article appeared after that scan.

### 第一财经 / Yicai

```text
last confirmed scan before targets:  2026-08-11 18:42 BJT
benchmark target date:               2026-08-12
next confirmed source scan:          2026-08-13 18:50:41 BJT
```

Confirmed source revisit interval:

```text
~48h08m
```

Exact publication times for the two selected Yicai targets are not available in the current benchmark evidence, so no exact publication-to-next-scan lag is asserted.

### Quanta

Quanta remains `OBSERVABILITY_AMBIGUOUS` for the original anchor window because exact publication time is unavailable and the relevant historical snapshot block was missing. Do not use it as proof for a precise lag number.

---

## 5. Direct evidence from the English rotation

The source groups around the benchmark make the LRU behavior visible.

The 2026-08-12 23:27 `intl_early` run selected sources including:

```text
STAT
Undark
WIRED
C&EN
Financial Times
Works in Progress
Aeon
Reuters Special Reports
```

The 2026-08-13 04:28 `pre_report` run then advanced to another older block, including:

```text
Knowable Magazine
The New Yorker
Noema
The Guardian · The Long Read
IEEE Spectrum
Yale Environment 360
Foreign Policy
Inside Climate News (native access blocked / no native rows)
```

ProPublica, Atlantic and Quanta had last been scanned at 2026-08-12 04:37 and were still behind these older sources in the least-recently-scanned queue. Their omission was therefore consistent with the selector's intended coverage rotation, not evidence that their first-party routes were broken.

---

## 6. Causal conclusion

For the registered-source benchmark misses, the primary causal chain is now:

```text
coverage-oriented LRU rotation
        +
same-day avoidance
        +
8 native source scans/run
        +
large enabled source pools
        ↓
1-2+ day source revisit interval
        ↓
strong article published after prior scan
        ↓
no post-publication source scan before report cutoff
        ↓
target URL never enters the Collector observable universe
```

Workflow start delay is a separate operational amplifier. Route quality remains a later diagnostic dimension, but it is not the first demonstrated failure for ProPublica, Atlantic, Yicai or Jiemian in this anchor.

The active policy is therefore internally consistent with a **coverage objective**, but misaligned with the **daily-report freshness objective** required for promotion.

---

## 7. What Phase 0B should change — and what it should not

A blind increase from 8 to 16+ source scans per run is **not** the first fix because it silently expands live network work and would mix scheduler policy with a budget decision.

Likewise, merely removing same-day avoidance is insufficient: with 29 English and 34 Chinese enabled sources, pure LRU still produces approximately two-day full-pool cycles.

The next design should preserve the existing total source-scan budget and split the eight slots conceptually into:

```text
freshness/SLA reserve
        +
coverage rotation
```

However, the current `rotate` tier is too large to give every rotate source a sub-24-hour SLA under the existing budget. A smaller explicit freshness-critical subset is required if the budget is held constant.

Candidate design direction for the implementation PR:

1. Add a narrowly scoped **freshness-critical source policy** rather than hard-coding benchmark URLs.
2. Reserve a bounded number of the existing eight slots for freshness-critical sources whose source scan age exceeds a configured SLA.
3. Use the remaining slots for the existing least-recently-scanned rotate/explore coverage policy.
4. Allow an overdue freshness-critical source to bypass same-day avoidance; retain same-day avoidance for ordinary coverage rotation.
5. Keep total `native_source_scans_per_run=8` unless a separate evidence-based budget change is explicitly approved.
6. Make the policy observable: record why a source was selected (`freshness_reserve` vs `coverage_rotation`) and its scan age at selection.

The freshness-critical set must be justified as a source-policy concept, not chosen merely to make the 2026-08-13 benchmark pass.

---

## 8. Acceptance criteria for a scheduler/freshness PR

Before any live behavior change is accepted, test/simulation should demonstrate:

```text
- total native source selections/run do not exceed the existing configured cap
- ordinary coverage rotation still progresses; no starvation of explore sources
- freshness-critical overdue sources are selected deterministically
- same-day bypass applies only to overdue freshness-critical sources
- source selection remains deterministic under equal timestamps
- source-selection reason and scan age are observable
- 2026-08-13 anchor loss modes improve in replay/simulation without touching L4/L5/L6
```

Post-merge natural evidence should then report at least:

```text
workflow start delay p50/p90
source scan-age p50/p90/p95 by policy class
freshness-critical SLA breach count
coverage age / starvation indicators
registered benchmark target post-publication scan coverage
```

No Editorial or Promotion gate changes follow automatically from this Phase 0B repair.

---

## Decision

```text
Phase 0B measurement slice: COMPLETE
Primary demonstrated issue: SOURCE REVISIT POLICY / CAPACITY
First repair target: source-selection freshness policy
Route-quality repair: defer until post-selection evidence requires it
NBD registry gap: remains Phase 0C
```
