# Phase 3 Source-Cap / Pre-Extraction Counterfactual — 2026-08-27

Status: **offline diagnostic only**. No production cap, ranking or budget change is authorized by this analysis.

## Question

Would mechanically increasing `NATIVE_SOURCE_CAP` from 4 to 6 or 8 recover the three Chinese Final items that Collector discovered but did not extract?

Frozen cases:

| Run | Source | Known-good Final | source/domain rank | pre-extraction editorial priority |
|---|---|---|---:|---:|
| COL-20260819-122210-BJT-zh_midday | EEO | 东航率先松绑“退改签” 其他航司会跟进吗 | 17 | 73 |
| COL-20260821-122427-BJT-zh_midday | Yicai | 地平线借道博世，智驾芯片落地欧洲16国 | 17 | 45 |
| COL-20260823-122354-BJT-zh_midday | EEO | 海外收入减少11%，泡泡玛特王宁：2026是调 | 13 | 73 |

Each run exhausted the fixed 32 body-attempt budget.

## Critical interaction: source cap is not the only cap

Current ranked-selection constants are:

```text
NATIVE_SOURCE_CAP = 4
ABSOLUTE_HOST_CAP = 4
OPEN_DOMAIN_CAP = 2
```

The same host cap is enforced in both initial selection and staged reserve scheduling. EEO and Yicai candidates in these cases are single-host source groups. Therefore:

```text
effective same-host native capacity = min(NATIVE_SOURCE_CAP, ABSOLUTE_HOST_CAP)

source cap 4, host cap 4 -> effective 4
source cap 6, host cap 4 -> effective 4
source cap 8, host cap 4 -> effective 4
```

A replay reconstructed from persisted `selection.score_components`, group ranks and the production ranking order reproduced the observed cap-4 initial selected counts exactly:

```text
2026-08-19 zh_midday: 22
2026-08-21 zh_midday: 19
2026-08-23 zh_midday: 23
```

Replaying source cap 6 and 8 while holding the independent host cap at 4 produced the **same initial selected set item-for-item** in all three runs. All three known-good Finals remained outside the initial selected set.

## Result

**Source-cap-only 4 -> 6 -> 8 is a no-op for these three cases.**

Known-good recovery:

```text
cap 4: 0/3
cap 6: 0/3
cap 8: 0/3
```

This invalidates a simple recommendation to raise only `NATIVE_SOURCE_CAP`.

## Why the problem still looks like “capacity” in the logs

The stored rejection reason `source_initial_cap_reserve` is locally true at the first ranking step, but it is not a complete causal description of end-to-end recoverability. The independent host cap and the fixed 32-attempt budget remain binding later.

In addition, EEO's shallow homepage mix creates severe pre-extraction ranking ties. For example, on 2026-08-19 many stock/ETF micro-flow snippets had editorial priority 73, identical to the known-good 东航 article. Several such snippets consumed extraction attempts and were rejected only after body extraction as `insufficient_editorial_evidence`.

This means the actionable problem is better stated as:

> **route/listing quality + weak pre-extraction discrimination + dual caps + fixed attempt budget**

rather than “source cap too small”.

## Next counterfactual to test

The next useful replay is **quality-aware reserve rescue under the same 32-attempt budget**, not a mechanical cap expansion. It must use only information available before body extraction (title, description, route identity, publication-time evidence and safe structural metadata).

A defensible first diagnostic is to demote obvious micro-market flow formats (e.g. repeated `主力资金`, `近5日`, ETF申赎/溢价, point-in-time valuation-flow snippets) and measure:

1. known-good Final recovery;
2. extra unknown/body attempts;
3. false demotion of genuinely substantive reporting;
4. displaced candidates elsewhere in the 32-attempt portfolio.

No such heuristic should be promoted from three cases alone. The purpose is to establish whether **pre-extraction discrimination** is the next bottleneck worth natural Shadow validation.
