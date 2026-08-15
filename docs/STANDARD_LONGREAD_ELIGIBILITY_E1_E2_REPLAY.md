# Standard Longread Eligibility E1 / E2 Offline Replay

Status: **offline replay + isolated implementation only / no production wiring**

Date: 2026-08-15

Versions:

```text
E0 evaluator: standard-longread-eligibility-v0.6-e0
E1 identity resolver: standard-longread-eligibility-v0.6-e1
E2 measurement: standard-longread-eligibility-v0.6-e2-measurement
```

## 1. Scope

This work follows E0 and replays the two upstream eligibility questions exposed by the 80/80 human recommendation review:

1. **E1 — factual medium/asset identity:** can high-confidence non-Standard objects be identified before L5 without source-wide blacklists or editorial heuristics?
2. **E2 — substantive length / structural adequacy:** is historical length evidence trustworthy and discriminative enough to justify a Standard Longread hard floor?

This PR is isolated offline code + tests + documentation. It does not wire any evaluator into Collector, the 07:35 Editor, source selection, L4, frozen L5, L6, or Promotion.

## 2. Human calibration set

The live `recommendation_review_analysis_v1` contains 80 reviewed delivered recommendations:

```text
total reviewed = 80
Hit = 42
non-Hit = 38

upstream_eligibility = 17
editorial_mismatch = 12
preference_or_novelty = 8
borderline_other = 1
```

The 17 upstream rows split cleanly into two families:

```text
wrong medium / asset = 6
  video page = 1
  recurring daily briefing = 2
  academic paper = 3

human perceived shortness = 11
```

All six wrong-medium/asset rows are human `不应推荐`. None are Hits.

## 3. E1 design rule

E1 must optimize precision, not apparent retrospective capture.

Allowed high-confidence identities in this replay:

### 3.1 Academic paper

Exact arXiv document identity:

```text
host = arxiv.org
path begins /abs/ or /pdf/ or /html/
```

Disposition:

```text
route_special / academic_asset
```

A media article whose title merely mentions arXiv remains a normal article.

### 3.2 Recurring Guardian day briefing

Requires both:

```text
Guardian host/source identity
AND
title begins Monday|Tuesday|...|Sunday briefing:
```

Disposition:

```text
ineligible_standard / roundup_identity
```

This is deliberately narrower than matching the word `briefing` or blacklisting The Guardian.

### 3.3 Video page

Requires explicit upstream page/medium evidence:

```text
explicit_video_page = TRUE
```

Disposition:

```text
ineligible_standard / video_medium
```

E1 never infers video-page identity from publisher, title, or the mere existence of an embedded video.

## 4. E1 retrospective replay result

### 4.1 Three academic papers — 3/3 resolved

Reviewed rows:

```text
https://arxiv.org/abs/2608.07077
https://arxiv.org/abs/2608.07069
https://arxiv.org/abs/2608.05466
```

All three are exact arXiv academic-document URLs and are deterministically routed `route_special`.

### 4.2 Two Guardian briefings — 2/2 resolved

Reviewed rows:

```text
Tuesday briefing: Inside the right's heated climate-denial debate
Wednesday briefing: How misinformation and a hardened immigration policy turned Ceuta into Europe's latest flashpoint
```

Both are Guardian URLs and day-specific `... briefing:` titles. They are deterministically `ineligible_standard`.

### 4.3 Historical video row — correctly abstained without missing evidence

Reviewed row:

```text
新京报
起底“隐形杀手”防晒衣：实测4件全翻车，厂家嘲讽记者“傻瓜”
https://m.bjnews.com.cn/detail/1785199934129721.html
human note: 非文章是视频
```

The historical `final_items` row looks like an ordinary media article and does not durably preserve the page-level video evidence needed by current L4 medium resolution. Therefore metadata-only E1 returns `UNRESOLVED` rather than inventing a video heuristic.

When explicit video-page evidence is supplied, E1/E0 correctly returns `ineligible_standard`.

This distinction is intentional:

```text
historical metadata-only newly resolvable wrong-medium rows = 5/6
applicable E1 high-confidence cues resolved = 5/5
video retrospective evidence completeness = insufficient
```

Do **not** report this as an E1 false negative. The missing fact belongs to historical page/medium observability. Equally, do not claim a historical 6/6 replay by using the human label as machine input.

## 5. E1 false-positive guards

Regression tests explicitly preserve:

- journalism about an arXiv paper as Standard media article;
- ordinary Guardian longform as Standard media article;
- a non-Guardian article whose title contains `Tuesday briefing:` as Standard media article;
- a written page with no explicit video-page evidence as Standard unless L4 says otherwise.

No source-wide blacklist is introduced.

## 6. E2 historical evidence audit

The 11 human-short rows have historical `final_items.body_chars_read` values:

```text
2600
4200
4300
5000
5500
6000
6200
6500
7000
8200
9000
```

Therefore:

```text
range = 2600–9000
median = 6000
```

But known Hits also occur at low historical lengths, including:

```text
3000
3100
4200
4500
5000
5200
```

The previously documented full 80-item replay shows:

```text
hypothetical <9500 chars rule:
  captures human-short = 11/11
  loses known Hits = 22/42
```

A very low `<3000` rule would capture only the single 2600-character human-short row and has no observed known-Hit below that point, but this is not sufficient evidence for a production floor: it addresses only 1/11 perceived-short cases and the historical field itself lacks trustworthy substantive-body provenance.

## 7. Why historical `body_chars_read` cannot define the floor

The historical field does not prove all of the following:

- complete article body was acquired;
- extraction was not truncated;
- navigation/captions/related links/boilerplate were removed;
- the count refers specifically to substantive prose;
- the same extraction semantics were used across versions/sources.

E2 therefore labels historical `body_chars_read` as:

```text
legacy_approximate
hard_gate_eligible = FALSE
```

This is stronger than merely saying “do not use 9500”. It prevents any future threshold from silently treating the old field as clean ground truth.

## 8. E2 trustworthy measurement contract

A length observation can be marked `trusted_substantive` only when the caller can establish:

```text
body_complete = TRUE
extraction_truncated = FALSE
boilerplate_removed = TRUE
```

Structural measurements may additionally record:

```text
paragraph_count
heading_count
prose_ratio
```

Even `trusted_substantive` means only that the measurement is fit for offline threshold analysis. It does **not** activate a hard floor.

Other quality states:

```text
legacy_approximate
incomplete
unknown
```

## 9. E2 interpretation: perceived shortness is not literal length alone

The human evidence strongly suggests at least two latent concepts:

1. **literal shortness** — genuinely little substantive prose;
2. **structural/depth thinness** — article may contain many characters but still feel too short for a Daily Longread because the prose is repetitive, templated, data-heavy, low-density, or lacks enough reporting/argument development.

Examples in the human set labeled `太短/比较短` still have old counts of 6,200, 6,500, 7,000, 8,200 and 9,000 characters. A simple character threshold cannot distinguish them from many accepted Hits.

Therefore E2 remains measurement-first. The next useful evidence is clean body structure/provenance, not a larger threshold search.

## 10. Offline code added

```text
src/longread_collector/v06/eligibility_e1.py
src/longread_collector/v06/eligibility_e2.py
src/longread_collector/v06/eligibility_e2_replay.py
tests/test_v06_standard_longread_eligibility_e1_e2.py
```

Properties:

- no Sheets/network dependency;
- no workflow import;
- no production caller;
- E1 falls back losslessly to E0 when identity is unresolved;
- E2 exposes measurement quality, never a production disposition;
- threshold replay reports human-short capture and known-Hit loss separately;
- missing lengths remain visible and are never treated as passing evidence.

## 11. Task 5 adjudication

### E1

**READY AS OFFLINE HIGH-PRECISION RESOLVER / NOT PRODUCTION-WIRED.**

The historical evidence supports the narrow arXiv and Guardian day-briefing rules. Video identity should continue to rely on explicit page/medium evidence rather than a new heuristic.

### E2

**MEASUREMENT CONTRACT READY / HARD FLOOR NOT READY.**

The human data rejects a useful simple character threshold under current historical provenance. E2 should collect trustworthy substantive-body and structure measurements before any future hard-gate proposal.

## 12. No authorization implied

This replay does not authorize:

- changing Collector candidate filtering;
- changing L4 medium/asset resolution;
- changing frozen L5;
- changing L6;
- changing source cap or network/body budget;
- changing LR-v3.5.2;
- using Collector output in production Editor;
- Promotion or auto-promotion.

Any future production eligibility wiring requires a separate reviewed change after prospective evidence.