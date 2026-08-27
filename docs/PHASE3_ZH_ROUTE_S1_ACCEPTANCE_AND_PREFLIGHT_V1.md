# Phase 3 — Chinese Route Shadow S1 Acceptance & Pre-flight Contract v1

Date: 2026-08-27  
Status: **frozen before first evaluable prospective S1 exposure**  
Scope: measurement / evidence readiness only  
Production promotion: **NOT AUTHORIZED**

## 1. First-principles purpose

S1 is not trying to prove that more URLs are better. It is trying to determine whether, for the exact Chinese sources naturally selected by Control, a richer first-party Route Portfolio supplies additional recent article metadata without changing Control behavior or consuming the fixed body-extraction budget.

The causal comparison is always **same-run Control vs Treatment**. Historical Control data is only an anomaly detector; it never substitutes for the paired Control.

The evidence chain is therefore:

1. a natural scheduled Control run exists;
2. Control is durable and measurement-valid;
3. Treatment is isolated from Control semantics;
4. Treatment telemetry is internally reconstructable;
5. route technical health is observed;
6. route incremental supply is described;
7. only later, after repeated eligible exposures, may S2/S3 test product eligibility and fixed-32 displacement.

Historical known misses are regression fixtures only. They are never route-ranking or tuning labels.

## 2. Day-0 is not route evaluation

Two questions are deliberately separated.

**Day-0 Acceptance:** did the experiment execute correctly and leave trustworthy evidence?

**S1 Route Evaluation:** does a route repeatedly add useful supply?

A route may return zero useful articles and the run may still be a valid Day-0 PASS. Conversely, a route may recover a known attractive article while the run is invalid because snapshot or telemetry invariants failed.

## 3. Machine audit layers

The deterministic read-only audit engine is:

`src/longread_collector/zh_route_shadow_s1_audit_v1.py`

It consumes only persisted rows and performs no Discovery, HTTP request, body extraction or Sheet write.

### L0 — Scheduler availability

- no durable Collector run → `NOT_EVALUABLE`, never S1 FAIL;
- duplicate durable `collector_run_id` → FAIL;
- non-Chinese group → `NOT_EVALUABLE`.

This prevents GitHub scheduler delay/drop from contaminating S1 route performance.

### L1 — Control validity

Required evidence:

- `final_status=success`;
- `source_run_coverage_persisted=TRUE`;
- current `run-source-coverage-v0.2` evidence;
- coverage row count agrees with the run ledger;
- snapshot persistence success;
- snapshot expected rows > 0;
- expected = persisted;
- durable readback TRUE;
- where the v0.6 run summary is available, `full_snapshot_invariant=TRUE`, `capture_gap_count=0`, and Control result preserved.

A failed Control is not an S1 exposure even if any orphan sidecar row somehow exists.

### L2 — Experimental isolation

Runtime-observable checks:

- route rows only belong to naturally selected target sources;
- all persisted Treatment rows remain `metadata_only`;
- Control body attempts remain within the existing 32-attempt cap;
- `native_source_cap=4` and `absolute_host_cap=4` remain unchanged;
- static Route Portfolio contract remains valid.

Three S1 v1 isolation claims are deliberately marked **not independently observable per natural run** rather than asserted from Sheet evidence:

- Treatment `body_requests=0`;
- Treatment never enters candidate selection;
- Treatment never enters production `article_cache`.

These are currently guaranteed by code/workflow regression tests and the architecture, not by a separate persisted run-level Treatment ledger. The audit reports that distinction explicitly.

### L3 — Telemetry integrity

For every naturally selected target source:

- expected active Treatment surface set must equal actual observation surface set;
- exactly one route observation per expected surface;
- observation and item rows must foreign-key to the same Control run;
- Route Contract / Discovery / Telemetry versions must match current S1 versions;
- every item must have a matching parent surface observation;
- item role, publication surface, endpoint and transport must match the parent;
- persisted surface aggregates must be exactly recomputable from item rows:
  - raw / unique;
  - recent;
  - dated;
  - exact timestamp;
  - Control overlap;
  - Treatment unique;
  - noise count and reason composition.

L3 is an evidence-integrity gate, not a quality judgment.

### L4 — Route technical health

Descriptive only on Day-0:

- `observed`;
- `date_unknown`;
- `stale_surface`;
- `empty`;
- `request_failed`;
- request / parse success;
- dated and exact-timestamp observability.

Poor technical yield is a finding, not an automatic invalidation of an otherwise correctly isolated experiment.

### L5 — Route utility evidence

Metadata-only descriptive output:

- canonical observed URLs;
- canonical proven-recent URLs;
- Control overlap;
- proven-recent Treatment incremental URLs;
- explicit noise among incremental URLs.

S1 is forbidden to label these metadata-only URLs `eligible`, `editable`, `selected` or `Final-quality`.

## 4. Eligible exposure, not raw run count

Do not say “3–5 runs and then S2.” The correct denominator is **eligible exposure**.

A source receives one eligible exposure only when:

1. the source was naturally selected by Control;
2. L0–L3 are valid;
3. all its expected active Treatment surfaces are represented in the telemetry contract.

Suggested maturity vocabulary is descriptive rather than threshold gaming:

- **technical observed** — at least one eligible exposure;
- **technical repeatable** — repeated valid exposures on different natural dates;
- **preliminary utility signal** — repeated non-zero incremental supply not explained primarily by explicit negative-control contamination;
- **S2-ready** — route identity and freshness are interpretable and incremental supply is repeatable enough to justify lightweight product-scope/eligibility auditing.

No percentage threshold is frozen before prospective evidence exists.

## 5. Static 21-surface pre-flight

The machine contract freezes **21 active S1 surfaces** across four target sources.

| Source | Surface | Role | Transport | Pre-flight interpretation |
|---|---|---|---|---|
| Yicai | `yicai_finance` | core_editorial | section | first-party editorial |
| Yicai | `yicai_kechuang` | core_editorial | section | first-party editorial |
| Yicai | `yicai_auto` | core_editorial | section | first-party editorial |
| Yicai | `yicai_news_breadth` | breadth_safety | section | breadth only; not privileged quality |
| Yicai | `yicai_info_control` | noise_control | section | explicit negative control |
| Yicai | `yicai_commercial_control` | noise_control | section | commercial negative control |
| EEO | `eeo_business_industry` | core_editorial | section | first-party editorial |
| EEO | `eeo_technology_plus` | core_editorial | section | first-party editorial |
| EEO | `eeo_politics_rss` | core_editorial | rss | must become stale, not healthy, if old |
| EEO | `eeo_finance_rss` | core_editorial | rss | must become stale, not healthy, if old |
| EEO | `eeo_industry_rss` | core_editorial | rss | must become stale, not healthy, if old |
| EEO | `eeo_root_rss_control` | noise_control | rss | stock/ETF-flow negative control |
| Caixin | `caixin_companies` | core_editorial | section | first-party editorial identity |
| Caixin | `caixin_finance` | core_editorial | section | first-party editorial identity |
| Caixin | `caixin_china` | core_editorial | section | first-party editorial identity |
| Caixin | `caixin_latest` | breadth_safety | section | breadth only |
| Caixin | `caixin_promotion_control` | noise_control | section | promotion identity; never generic Caixin editorial coverage |
| Jiemian | `jiemian_medicine` | core_editorial | section | native editorial; historical miss only regression |
| Jiemian | `jiemian_consumer` | core_editorial | section | native editorial |
| Jiemian | `jiemian_health_face` | core_editorial | section | native editorial; freshness must be observed |
| Jiemian | `jiemian_health` | breadth_safety | section | breadth only |

Two special-product surfaces remain deliberately inactive: EEO e-paper and Caixin Deepview/商圈.

Static regression checks require:

- globally unique surface identities;
- first-party endpoint host for every configured surface;
- non-empty `publication_surface_id`;
- only `section` or `rss` transports;
- positive metadata item caps;
- special products inactive;
- exact four-surface negative-control set frozen;
- Caixin promotion content cannot be reclassified as ordinary editorial coverage;
- Jiemian account/author/JMedia paths cannot appear as active native editorial surfaces.

## 6. Publication-time evidence boundary

S1 list/feed time evidence is useful for **S1 freshness observation**. It is not automatically Final Recall A-level publication-time evidence.

The generic section parser associates clock text appearing after an admitted article anchor and before the next admitted article anchor. That is intentionally lightweight and body-free, but it is not a DOM-card provenance proof for every publisher template.

Therefore:

> S1 `publication_time_confidence=high` means strong evidence inside the S1 route-observation contract; promotion-grade Final Recall must continue to apply its independent evidence hierarchy and fail-closed conflict rules.

This prevents the measurement layer from silently upgrading its own evidence.

## 7. Historical Control baseline role

Historical Control is an **anomaly detector only**.

Use it to ask whether the same-run Control appears abnormally weak or delayed compared with a recent version-compatible operating window. Never use historical averages as the causal comparator for Treatment.

The frozen late-Phase-2 reference window is documented separately in:

`docs/benchmarks/2026-08-27_zh_control_version_aware_baseline.md`

## 8. Exit to S2/S3

S2 is not authorized merely because Day-0 passes.

S2 may be considered per source/surface after repeated eligible exposures show interpretable, non-zero incremental metadata supply that is not primarily stale/commercial/partner/micro-market contamination.

S3 remains the fixed-budget counterfactual:

> Control pool + qualified Treatment incrementals, with total body attempts still capped at 32.

Only S3 can answer whether new route supply deserves to displace existing body attempts.

No part of this contract changes production source routes, source/host caps, body budget, L4/L5/L6, `v06_primary`, 07:35 Editor or automatic promotion.
