# Phase 3 Quality-Aware Reserve Replay — 2026-08-27

Status: **offline diagnostic only**. This document does not authorize a production ranking, source-cap, host-cap or body-budget change.

## Question

Can a conservative pre-extraction demotion of obvious micro-market snapshots recover the three Chinese Final items that Collector discovered but did not extract, while keeping the hard 32 body-attempt budget unchanged?

Frozen known-good cases:

1. 2026-08-19 EEO — `东航率先松绑“退改签” 其他航司会跟进吗`
2. 2026-08-21 Yicai — `地平线借道博世，智驾芯片落地欧洲16国`
3. 2026-08-23 EEO — `海外收入减少11%，泡泡玛特王宁：2026是调…`

The replay uses the immutable snapshot blocks for those runs. It does **not** use post-extraction outcomes to calculate the demotion score; outcomes are used only to evaluate whether the proposed title patterns were historically safe.

## Tier 1: high-precision micro-market detector

The first experiment intentionally uses only narrow title patterns:

- `主力资金` or `主力净流入/主力净流出`;
- `近5日` combined with stock-snapshot context such as `大盘/估值/主力/震荡/市盈`;
- `ETF` combined with transaction/snapshot language such as `净申购/净赎回/申赎/溢价/溢折率/规模缩水`.

This is a **demotion**, not a hard rejection rule.

A generic `ETF` keyword is explicitly unsafe. The same evidence window contains substantive reporting such as `东方红、中欧新入局，ETF赛道迎来“最后的头部玩家”`; therefore broad ETF suppression is prohibited by this experiment.

## Independent safety evidence

A broad snapshot query for `主力资金` across the relevant interval returned repeated EEO single-stock templates. Every matched item that had actually been body-extracted was `eligible_for_editor=FALSE` and ended as `candidate_disposition=reject`; no extracted `主力资金` match in that observed sample was a formal candidate.

Transactional ETF examples such as:

- `创业板50ETF鹏华净申购减少1600万份…高溢价…`
- `责任ETF建信…净申购…溢价走势`
- `建材ETF富国规模缩水…溢折率…`
- `创新药ETF华泰柏瑞…净申购…溢价率`

were likewise extracted and rejected. This supports the narrow conjunctive detector, not a domain/topic blacklist.

## Source-local rank replay

Persisted `selection.source_or_domain_rank` is treated as the factual baseline. All non-flagged candidates preserve their relative order; Tier-1 matches ahead of the known-good item are moved below ordinary editorial candidates.

| Run / known-good Final | Original source rank | Tier-1 items ahead | Adjusted source rank | Result |
|---|---:|---:|---:|---|
| 8/19 EEO — 东航退改签 | 17 | 9 | **8** | still outside top 4 |
| 8/21 Yicai — 地平线×博世 | 17 | 0 | **17** | unchanged; still outside top 4 |
| 8/23 EEO — 泡泡玛特 | 13 | 8 | **5** | first same-source reserve candidate |

### 8/19 EEO

The homepage contained a large block of high-scoring micro-market snapshots, many at editorial priority 73. Several were extracted and later rejected as `insufficient_editorial_evidence`.

However, removing only the high-precision micro-market patterns does **not** solve the case. The known-good 东航 article moves only from rank 17 to rank 8 because several ordinary news items still tie or outrank it. This is evidence that richer route/listing metadata is still required.

### 8/21 Yicai

The high-precision micro-market detector has essentially no leverage. The known-good 地平线 article remains rank 17.

The dominant issue is a large 45-point tie created by weak listing metadata and unknown publication time (`freshness_unknown=true`, deferred publication evidence). This strongly reinforces the separate Chinese route experiment: better first-party Yicai listing surfaces and timestamp evidence are more causally relevant than a micro-market penalty here.

### 8/23 EEO

This is the strongest positive case. The original top four EEO source slots were dominated by transactional ETF / single-stock flow snapshots that were later rejected. Tier-1 demotion moves 泡泡玛特 from source rank 13 to **rank 5**.

Rank 5 is important because current staged reserve logic first replaces an unusable first-stage item with a same-group reserve. Therefore 泡泡玛特 becomes a plausible first same-source reserve candidate.

It is **not** counted as a deterministic recovery: after the counterfactual reorder, several candidates newly entering the first four were not body-extracted in the historical run, so their usability is unknown. Using unknown post-extraction outcomes as if they were failures would overstate the result.

## Why no broader Tier-2 rule is promoted from this replay

Two obvious low-value-looking titles ahead of 泡泡玛特 after Tier-1 demotion include a sports medal recap and a promotional/lifestyle-style headline. Demoting both would move 泡泡玛特 into the top four.

That is not sufficient evidence for a generic sports/event/promotion penalty. The false-positive denominator has not been established, and broad title rules could suppress substantive reporting. Tier 2 is therefore left as a future hypothesis, not encoded as a recommended policy.

## Result

The conservative answer is:

> **Tier-1 quality-aware demotion improves EEO extraction opportunity materially, but it does not independently recover all three known-good Finals.**

Frozen outcome:

- deterministic top-4 recoveries: **0/3**;
- materially improved to first same-source reserve: **1/3** (8/23 泡泡玛特);
- improved but still outside top four: **1/3** (8/19 东航);
- no effect: **1/3** (8/21 地平线).

This is not a failed experiment. It isolates two different bottlenecks:

1. **EEO:** noisy listing mix + weak pre-extraction discrimination genuinely wastes body attempts; a narrow micro-market demotion is promising for Shadow validation.
2. **Yicai and residual EEO cases:** route/listing quality and publication metadata remain necessary. Ranking cannot manufacture information that the listing surface does not expose.

## Decision boundary

Recommended next step is **Shadow scoring observability**, not a production penalty:

- calculate the Tier-1 flag/reason on future natural candidates;
- record whether flagged items would have consumed body attempts under baseline ranking;
- compare against post-extraction eligibility when bodies are naturally available;
- collect a larger false-positive denominator before any ranking semantic change.

Do not change `NATIVE_SOURCE_CAP`, `ABSOLUTE_HOST_CAP`, the 32-attempt budget, source registry, L4/L5/L6, `v06_primary`, 07:35 Editor wiring, production `article_cache` consumption or auto-promotion based on this replay.
