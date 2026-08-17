# 2026-08-17 Controlled High Rerun Diagnostic

> Docs-only evidence snapshot for the daily longread recommendation project.
>
> Mutable canonical handoff remains the Google Doc `每日长文推荐 — Canonical Handoff`, id `1bhedf-8OWiWAWCYxwgboRfc5Et4yxDcZCi3de4sOisE`.
>
> Authority for mutable facts remains: `merged code/contracts → open PR → GitHub Actions → scheduled natural evidence → live Sheet/config → docs → handoff → chat`.

## Scope and boundaries

This document records the blind controlled comparison between the 2026-08-17 scheduled 07:35 run and an independent GPT-5.6 Thinking + High manual rerun.

No runtime/config/workflow/source-cap/network/Firecrawl/body/L4/frozen-L5/L6/article_cache-production/promotion/auto-promotion change is authorized by this document.

Collector remains `shadow`; Promotion remains `NOT_READY / SHADOW`.

## Scheduled reference

```text
run_id:                     LR-20260817-0735-BJT-LRv35
run_type:                   scheduled_auto
editor semantics:           LR-v3.5
runtime reliability:        LR-v3.5.2
final_status:               success
raw:                        25
strong:                     2
selected:                   2
completion_validation:      pass
```

The run durably completed four Discovery lanes, two delta-only candidate checkpoints/readbacks, final freeze, final_items/history/archive, centralized readback and completion validation. Collector was not consumed before freeze.

Therefore the two-item result on 2026-08-17 cannot be attributed to an incomplete run/finalization failure. This is materially different from the 2026-08-16 finalization inconsistency.

Scheduled final:

1. WIRED — `This Coin-Sized Device Can Hack a Boeing 737`
2. The Verge — `Rogue AI aren’t science fiction anymore`

## Blind manual High rerun

```text
run_id:                     LR-20260817-0828-BJT-LRv35
run_type:                   manual_rerun
model_requested:            GPT-5.6 Thinking
reasoning_effort_requested: High
model_observed:             unavailable
reasoning_effort_observed:  unavailable
editor semantics:           LR-v3.5
runtime reliability:        LR-v3.5.2
final_status:               success
```

Blindness before final freeze:

- no read of same-day scheduled candidate_log/final_items;
- no use of scheduled article-level chat evidence;
- no read of article_cache;
- Collector Shadow did not participate in Discovery, verification, scoring, ranking or selection;
- history baseline was restricted to `recommended_date <= 2026-08-16`.

Coverage:

```text
international_attempted >= 14
zh_attempted            >= 16
special_sections        >= 5
lanes_completed            4
checkpoint1 delta          21
checkpoint1 readback       21 unique
checkpoint2 delta           8
cumulative readback        29 unique
raw soft floor             24
low-yield escalation       false
```

## Manual funnel

```text
29 raw
→19 canonical-date-valid
→19 body/date independently verified
→16 history-clean
→11 strong / final-caliber
→3 selected
```

Main losses:

- false-recency / stale canonical date: 10;
- exact-URL history duplicate: 3;
- 8 strong articles remained `strong_rejected`, mainly due to portfolio/language structure rather than failure to reach final-caliber.

Frozen manual final:

1. The Guardian — `A bungled bomb plot in Poland exposed a spy – but whose spy was he?` — score 94
2. WIRED — `This Coin-Sized Device Can Hack a Boeing 737` — score 93
3. The Atlantic — `The 108-Degree Eviction` — score 92

Eight additional strong candidates:

- WIRED — `Rogue AI Agents Aren’t Evil. They’re Just Eager to Please`
- FT — `How the UAE won over Washington`
- FT — `Putin’s war machine scours the home front for recruits`
- The Atlantic — `The Human-Origin Story Is Being Radically Revised`
- Quanta — `Neutrinos From Deep Inside Earth Provide a New Picture of the Mantle`
- Reuters — `Lenders scrutinize US data center financing as community opposition builds`
- Reuters — `Millions of burnt books show how 'war of endurance' is hurting Ukraine`
- The New Yorker — `G.P.S. and the Lost Art of Getting Lost`

Thus `manual final=3` must not be interpreted as only three final-caliber articles existing that day.

## Chinese effective-supply / freshness finding

Manual Chinese funnel:

```text
raw=10
date-valid=0
```

Observed patterns included publisher surfaces showing current-looking month/day or relative freshness while the recovered standalone canonical article was actually from 2023 or July 2026.

```text
manual explicit false-recency:    10/29 raw
scheduled explicit comparable:   >=9/25 raw
```

Because both independent runs exhibited the same pattern, current evidence supports a systemic surface-freshness / canonical-date precision problem rather than one-off search noise.

## Scheduled vs manual comparison

```text
                         scheduled    manual
raw                         25          29
strong                       2          11
final                        2           3
```

Overlap:

```text
raw article-identity overlap     4
exact canonical URL overlap      2
strong overlap                   1
final overlap                    1
```

All 10 manual-only strong articles were absent from scheduled raw. The closest evidence-backed miss category is therefore `discovery_miss` rather than editorial scoring.

The scheduled-only strong The Verge article was absent from manual raw, also a `discovery_miss` in the opposite direction.

The one shared strong/final article, WIRED Boeing 737, was selected by both. There is no same-article evidence here supporting scheduled editorial conservatism as the primary cause.

Scheduled model/reasoning remains unspecified/unavailable; manual High is part of a larger treatment bundle and its isolated causal effect is not identified.

## Acquisition / dedup / Collector audit

Manual access telemetry:

```text
DIRECT_OK          21
PARTIAL_PREVIEW     3
PAYWALL             5
```

No manual item was proven to be final-caliber and excluded solely because of body-access failure.

Scheduled had five verification rejections, including some high-potential items, so Acquisition/canonical-body verification remains a contributing factor, especially for Chinese publishers.

14-day dedup:

```text
manual exact URL duplicates     3
scheduled exact URL duplicates  2
```

This is a real contraction but too small to explain the low final count by itself.

Post-freeze article_cache audit:

```text
Guardian exact overlap  1
WIRED exact overlap     0
Atlantic exact overlap  0
```

This audit occurred only after manual freeze and did not change `candidate_origin=native_search` or the frozen payload.

## Root-cause decision

### Primary

Effective recent Chinese supply is scarce under current product rules, and publisher false-recency / canonical freshness precision contamination causes the Chinese candidate pool to collapse at the date-valid stage.

### Secondary

Scheduled Discovery recall / execution realization variance. The scheduled run missed 10 strong articles that the manual run found.

### Contributing

- Acquisition / canonical-body verification;
- 14-day history dedup.

### Substantially ruled out for this run

- scheduled runtime incompleteness;
- editorial conservatism as the main explanation;
- scarcity of high-quality international longreads.

## Next validation boundary

Do not modify LR-v3.5.2, the 07:35 automation, Collector Shadow, L4, frozen L5, L6, source cap, network/Firecrawl/body budget or promotion state from this single comparison.

On the next naturally low-yield day, repeat the same blind controlled-rerun boundary and test two falsifiable signals:

1. whether manual-only strong remains material (`>=5`, or scheduled recall of manual strong remains below roughly 50%);
2. whether Chinese publisher `surface lead → canonical recovered → date-valid → body verified` conversion remains low, with special attention to 南方周末、界面、虎嗅、财新.

Only repeated evidence should decide whether the next repair target is Discovery, canonical recovery/date precision, or Acquisition.

## Current checkpoint after this evidence

```text
2026-08-17 scheduled runtime completion: PASS
2026-08-17 controlled manual rerun:       SUCCESS
Discovery/freshness diagnosis:            OPEN
Collector:                                SHADOW
Promotion:                                NOT_READY
Production change authorized:             NONE
```
