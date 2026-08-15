# Standard Longread Eligibility E0

Status: **offline contract only / no production wiring**

Version: `standard-longread-eligibility-v0.6-e0`

## Why this exists

The 2026-08-15 retrospective human review completed 80/80 delivered recommendations. Raw Human Recommendation Hit Rate was 42/80 (52.5%), but attribution separated the 38 non-Hits into different responsibility layers:

- `upstream_eligibility`: 17
- `editorial_mismatch`: 12
- `preference_or_novelty`: 8
- `borderline_other`: 1

The cleanest upstream signal was `wrong_medium_or_asset=6`: one video page, two daily briefings, and three academic papers. All six were human Rejects. These should not be repaired by changing L5 editorial quality scores.

The same review produced 11 human `too_short` notes, but a later join to historical `final_items.body_chars_read` disproved a simple character-count hard gate. Human-short rows ranged from 2,600 to 9,000 read characters (median 6,000), while known Hits existed at 3,000, 3,100, 4,200, 4,500, 5,000, and 5,200. A `<9,500` threshold would capture all 11 short labels but would also remove 22/42 known Hits. E0 therefore records length evidence but **never rejects on length alone**.

## Architectural responsibility

The intended sequence is:

`Discovery/Acquisition evidence → L4 Canonical facts → Standard Longread Eligibility → L5 Editorial Judge → L6 Portfolio`

The eligibility layer answers a product-class question: *is this object eligible to compete for a Standard Longread slot?* It does not answer whether an eligible article is insightful, deep, newsy, repetitive, or personally relevant.

## E0 dispositions

- `eligible_standard`: factual class is a normal written media article on an article page.
- `route_special`: factual class belongs to an existing non-standard route, currently academic papers and primary documents.
- `ineligible_standard`: high-confidence non-longread product class, such as video page, roundup identity, non-article navigation surface, data card, or event listing.
- `unknown`: factual identity is unresolved or the page surface prevents a safe product decision.

## Explicit non-goals

E0 does **not**:

- change Collector workflow/runtime/config;
- modify L4 resolvers;
- modify frozen `editorial-judge-v0.6-pr7.2`;
- modify L6 portfolio selection;
- connect the 07:35 Editor to `article_cache`;
- increase network, body, Firecrawl, or source budgets;
- start Phase0C/NBD or PR-8;
- define a production length threshold;
- infer `roundup_identity` from a publisher name or title inside the eligibility evaluator.

## Evidence interface

`EligibilityEvidence` keeps product-specific facts separate from editorial scoring. `roundup_identity` is expected to be resolved upstream. `substantive_length_chars` and `substantive_length_source` are audit measurements only in E0.

The historical field `body_chars_read` has no active configuration contract proving that it equals cleaned, untruncated substantive article length. Future E2 work must first define a trustworthy length measurement and provenance before evaluating a hard floor.

## Offline replay acceptance

`eligibility_replay.py` intentionally has no Sheets/network dependency. A caller supplies human review rows plus candidate dispositions. The replay reports separately:

- known-Hit loss from Standard Longread;
- wrong-medium/asset rows correctly resolved away from Standard Longread;
- wrong-medium/asset rows that remain `unknown` rather than being falsely counted as capture;
- subtype-correct disposition, so academic papers must route special while videos/briefings become standard-ineligible;
- special routing count;
- hard ineligible count;
- total unknown count.

For the high-confidence wrong-medium/asset family, the intended acceptance gate is:

1. all reviewed video/briefing/paper failures are factually resolved away from `eligible_standard`; `unknown` does not count as successful capture;
2. academic papers are `route_special`, while resolved video pages and recurring briefings are `ineligible_standard`;
3. known Standard Longread Hits are not lost because of those rules;
4. papers are routed, not treated as low-quality media articles;
5. written articles with embedded videos remain written articles if L4 resolved them as such;
6. no source-wide blacklist is introduced.

Length is a separate measurement-first track. Any future threshold proposal must publish human-short capture versus known-Hit loss and require near-zero known-Hit loss for a hard reject.

## Next steps after E0

- **E1:** complete high-confidence factual recognition/routing for academic assets, video medium, and recurring briefing identity. `arxiv.org/abs/...` should be recognized as an academic-document hint, but journalism *about* a paper must remain media article.
- **E2:** define substantive-length semantics and structural adequacy; distinguish literal shortness from perceived thinness/depth inadequacy.
- **L5.1:** only after the eligibility boundary is accepted, offline-evaluate narrow `depth floor` and `newsiness penalty` changes on the 55 editorial-evaluable human items.

## Current natural-gate state

Phase0B reached formal `NATURAL ACCEPTED / DONE` on 2026-08-15. The authoritative closure run is:

```text
collector_run_id: COL-20260815-041810-BJT-pre_report
GitHub Actions:   31837235761
snapshot:         208/208
readback:         true
full invariant:   true
sources:          6 freshness + 2 coverage = 8
```

A previous document tuple `COL-20260815-042614-BJT-pre_report / 156` was stale and has been corrected from higher-authority GitHub artifact plus live run-ledger evidence.

PR #93 full-funnel observability was subsequently merged as `f408ccd801caff8cd51f228a4228b6fe0cd69c58`. PR #94 E0 itself is merged as `4b581db494668a9da8897b88ced251e80dce6912`. These facts permit further offline eligibility work but do not create production wiring or promotion readiness.

The 07:35 scheduled LR path is a separate gate. LR-v3.5.1 received its first natural acceptance test on 2026-08-15 and **failed** despite Coverage Gate PASS: raw=8 / verified=2 / strong=2 / selected=2, followed by `FINAL_PERSISTENCE_SHEETID_MISMATCH`. Independent manual GPT-5.6 Thinking + High produced raw=26 / verified=23 / strong=13 / selected=8, so two-item supply scarcity was rejected while High itself remains only one confounder.

LR-v3.5.2 is now implemented as a runtime-only scheduled completeness/persistence repair, with first natural acceptance target `2026-08-16 07:35 BJT`. E0 remains offline and independent of that runtime gate. Do not production-wire E0 or modify frozen L5 merely to improve the LR-v3.5.2 acceptance result or Collector promotion metrics.

Collector itself remains `mode=shadow`, Editorial Gate `NOT_READY`, Promotion Gate `SHADOW`, and `article_cache` production consumption prohibited.
