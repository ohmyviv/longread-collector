# Final Recall Attribution Contract v1

Status: design-only / offline / not wired to production or promotion

Date: 2026-08-15

## 1. Purpose

Final Recall v1.2 correctly defines item-level observation windows, strict vs partial measurement coverage, registry membership and effective-route denominators. It does not yet provide enough durable evidence to causally attribute every strict miss below the generic `discovery` stage.

This contract adds an evidence-aware attribution layer without changing any v1.2 denominator, cutoff, item window, source-registry rule, route rule, Collector runtime, source cap, network budget, L4/L5/L6 behavior, or promotion state.

The design principle is:

> Record factual stage evidence first; assign the earliest evidenced broken stage second; preserve `unknown/evidence_gap` whenever the evidence cannot support a narrower causal claim.

A complete-looking cause distribution is less important than a truthful one.

## 2. Non-goals / frozen boundaries

This contract does **not**:

- change `final-recall-audit-v1.2-item-window` or its strict denominator;
- reclassify a late capture after 07:35 as a strict-window hit;
- infer parser failure merely from an absent target snapshot;
- infer source non-selection merely from zero source observations;
- change source registry entries, effective routes, source rotation, freshness reserve, source cap, Firecrawl budget, body budget or acquisition behavior;
- change production L4/L5/L6;
- wire Collector output into the 07:35 Editor;
- change Promotion from `NOT_READY / remain SHADOW`;
- authorize auto-promotion.

## 3. Two-layer model

### 3.1 Factual evidence layer

For each strict/partial final item, store observable facts independently of causal labels:

1. denominator / measurement status;
2. registry membership;
3. effective route status;
4. source-selection evidence during the item window;
5. source-attempt evidence during the item window;
6. source-attempt result and source observation count;
7. target observation / snapshot match;
8. prefilter outcome;
9. body/acquisition outcome where reached;
10. L4 outcome where reached;
11. L5 outcome where reached;
12. portfolio/final-selection outcome where reached;
13. late observation after cutoff;
14. evidence completeness and durable evidence references.

### 3.2 Attribution layer

Only after the factual layer is assembled may the audit assign:

- `primary_stage` — earliest evidenced broken stage;
- `mechanism_code` — narrowest mechanism supported by evidence;
- `evidence_level` — `confirmed`, `strongly_supported`, or `unresolved`;
- `counterfactual` — the minimum upstream condition that would have allowed the item to reach the next stage;
- `evidence_refs` — durable run/snapshot/attempt/audit identifiers.

Downstream stages that were never reached are `not_reached`, not failures.

## 4. Primary-stage taxonomy

Allowed `primary_stage` values:

```text
not_applicable
registry
route
source_selection
source_attempt
surface_observation
prefilter
acquisition
l4
l5
portfolio
persistence
unknown
```

Precedence is the order above, except `not_applicable` is used for non-denominator/manual-only/not-yet-available cases.

### 4.1 Stage semantics

`registry`
: Required source is outside registry for the applicable denominator.

`route`
: Source is registered but no effective route exists.

`source_selection`
: Effective route exists, but promotion-grade evidence shows no successful evidenced source attempt during the item observation window. A source may be eligible for rotation yet not selected before cutoff.

`source_attempt`
: Source was selected/attempted, but the source attempt itself failed in a way supported by durable attempt evidence, e.g. HTTP/access/parser-endpoint failure before a usable source result could be produced.

`surface_observation`
: A usable source attempt completed, but the target article was not emitted into the raw discovery observation pool. Use only when source-attempt evidence distinguishes this from an attempt failure.

`prefilter`
: Target appeared in the raw discovery snapshot but was rejected or capacity-deferred before extraction.

`acquisition`
: Target passed prefilter but body/control acquisition failed or remained incomplete.

`l4`
: Body was observed but Canonical Article eligibility/source/date/page-surface processing blocked the item.

`l5`
: L4 reached decision-eligible state but frozen Editorial Judge rejected/low-valued the item.

`portfolio`
: Editorially actionable item was not selected because of downstream portfolio/source-cap/novelty/section constraints.

`persistence`
: The item was otherwise observed/reached, but audit-critical persistence/readback failed so the strict factual chain cannot be trusted.

`unknown`
: Evidence is insufficient to select a causal stage without guessing.

## 5. Evidence levels

```text
confirmed
strongly_supported
unresolved
```

`confirmed`
: Direct durable evidence proves the relevant stage fact, e.g. matched immutable snapshot, run-scoped source-attempt row, explicit prefilter reason, acquisition event, L4/L5 event, readback invariant.

`strongly_supported`
: Multiple durable facts support the attribution, but one join or negative fact is indirect. This must never be silently promoted to `confirmed`.

`unresolved`
: More than one causal mechanism remains compatible with the durable evidence. `mechanism_code` must remain broad or `evidence_gap`.

## 6. Required source-attempt ledger

The current `collector_discovery_snapshot` is an observation ledger: by design it contains items emitted into the raw discovery pool. It cannot represent a selected source that emitted zero observations.

The historical `native_discovery_shadow` table contains per-source attempts but is not promotion-grade for current runs: it stopped receiving current natural runs, lacks `collector_run_id`, lacks current selection reason, and is not reliably joinable to an item window.

A future observability-only change should add a durable run-scoped source-attempt ledger. Proposed table: `collector_source_attempts_v1`.

Minimum fields:

```text
source_attempt_id
collector_run_id
run_started_at_bj
query_group
source_id
source_name
selection_reason
selection_scan_age_hours
selected_order
attempted
native_success
selected_method
selected_endpoint
results_count
fallback_needed
error_type
error_message
attempts_json
logged_at_bj
ledger_version
```

Contract requirements:

- one row for every selected source in every natural Collector run, including zero-observation attempts;
- `collector_run_id` is mandatory;
- selection evidence and attempt outcome are recorded together or by stable join key;
- a zero-result attempt is persisted, never inferred from absence;
- the ledger is written in Shadow without changing the network request set;
- logging failure must not mutate Collector behavior, but must set an explicit attribution evidence-gap signal;
- promotion-grade attribution may use this ledger only after natural-run persistence/readback acceptance.

`attempts_json` is diagnostic detail, not the primary join contract. If it becomes oversized it must use the existing lossless overflow discipline or an equivalent bounded representation.

## 7. Proposed item-attribution sidecar

Do not append causal fields directly to v1.2 and overwrite its historical contract. Proposed sidecar: `final_recall_attribution_v1`.

Minimum fields:

```text
attribution_id
report_date
final_run_id
v12_audit_id
item_index
final_url_canonical
final_source
measurement_denominator_status
item_observation_started_at_bj
cutoff_at_bj
source_id
registry_status
effective_route_status
source_selection_status
source_selected_run_ids
source_attempt_status
source_attempt_count
source_attempt_run_ids
source_attempt_results_count
target_observed_in_window
target_snapshot_id
prefilter_status
prefilter_reject_reason
acquisition_status
l4_status
l5_status
portfolio_status
late_observation_after_cutoff
late_first_seen_at_bj
primary_stage
mechanism_code
evidence_level
evidence_completeness
evidence_refs_json
counterfactual
attributed_at_bj
attribution_version
```

Factual status fields must support `not_reached`, `unknown`, and `not_applicable` where relevant.

## 8. Deterministic attribution rules

The attribution evaluator walks the chain from upstream to downstream and stops at the earliest evidenced break.

Pseudo-contract:

```text
if not promotion-measurement applicable:
    primary_stage = not_applicable
elif outside_registry:
    primary_stage = registry
elif no_effective_route:
    primary_stage = route
elif target snapshot exists:
    if prefilter rejected/deferred:
        primary_stage = prefilter
    elif acquisition failed/incomplete:
        primary_stage = acquisition
    elif L4 blocked:
        primary_stage = l4
    elif L5 blocked:
        primary_stage = l5
    elif portfolio blocked:
        primary_stage = portfolio
    else:
        primary_stage = not_applicable  # captured/reached expected state
else:
    if source-selection evidence is complete and no source was selected/attempted in window:
        primary_stage = source_selection
    elif source attempt failed with durable attempt evidence:
        primary_stage = source_attempt
    elif source attempt succeeded with durable zero/other observations but target absent:
        primary_stage = surface_observation
    else:
        primary_stage = unknown
```

Negative evidence is valid only when the relevant ledger is known complete for the item window.

## 9. Late-observation rule

A capture after the report cutoff is evidence for diagnosis only.

```text
strict outcome at cutoff: immutable
late_observation_after_cutoff: TRUE/FALSE
late_first_seen_at_bj: timestamp if present
```

A late capture may refine a miss mechanism, e.g. `source_selection_before_cutoff`, but may never turn the same report-date strict miss into a hit.

## 10. Evidence completeness

Recommended `evidence_completeness` values:

```text
complete
snapshot_complete_attempt_incomplete
attempt_complete_snapshot_complete
audit_persistence_gap
legacy_partial
unknown
```

For promotion gating, a causal miss distribution should report both:

1. miss counts by `primary_stage`; and
2. fraction of strict misses with `evidence_level=confirmed` and sufficient completeness.

Do not treat unresolved misses as if they were route/Discovery failures.

## 11. 2026-08-15 strict baseline under this contract

This is a forensic application of the design, not a historical rewrite of v1.2.

### FT — `AI frenzy drives Chinese tech valuations to multiples of US peers`

```text
primary_stage: prefilter
mechanism_code: source_initial_cap_reserve
evidence_level: confirmed
```

Evidence: target immutable snapshot exists in `COL-20260814-231330-BJT-intl_early`, with `prefilter_status=not_selected_capacity` and `prefilter_reject_reason=source_initial_cap_reserve`.

### Reuters — `While the world is distracted, China steps up its strategic game`

Current durable evidence proves:

- registered + effective route;
- source was selected/attempted during the strict window, because `last_scanned_at_bj` is written only for attempted `selected_sources` after `NativeSourceDiscovery.discover(...)`;
- run `COL-20260814-231330-BJT-intl_early` has `snapshot_expected_rows=133`, `snapshot_persisted_rows=133`, `snapshot_readback_performed=TRUE`;
- no `reuters-special` observation was emitted into that run's 133-row immutable raw discovery snapshot.

Without a current run-scoped attempt row, the exact submechanism — access failure, endpoint/parser failure, or a usable zero-result surface — is not promotion-grade durable evidence.

```text
primary_stage: source_attempt_or_surface_observation  # unresolved boundary under legacy evidence
mechanism_code: source_attempted_zero_raw_observations
evidence_level: strongly_supported / unresolved submechanism
evidence_completeness: snapshot_complete_attempt_incomplete
```

When the proposed source-attempt ledger exists, this compound stage must collapse deterministically to either `source_attempt` or `surface_observation`.

### Guardian — `How can we talk about this extreme weather now that it's a battleground in the culture wars?`

Current durable evidence proves:

- registered + effective route;
- item published 2026-08-14;
- registry `last_scanned_at_bj=2026-08-13 04:35:20`, before the item window;
- successful evidenced natural runs before the 07:35 cutoff do not show a later source-attempt timestamp.

```text
primary_stage: source_selection
mechanism_code: no_successful_evidenced_source_attempt_in_item_window
evidence_level: strongly_supported
```

Do not label it parser or surface-observation failure without an attempted-source record.

The three-item strict baseline therefore contains three materially different failure chains. The headline `1/3` Recall value remains valid, but generic `miss_stage=discovery` is insufficient for remediation or promotion decisions.

## 12. Rollout sequence

Design-only sequence; no step is authorized by this document alone:

1. review this contract;
2. implement `collector_source_attempts_v1` as an observability-only sidecar with no request-set change;
3. prove persistence/readback on natural Shadow runs;
4. implement offline `final_recall_attribution_v1` using immutable v1.2 + attempt ledger + existing downstream artifacts;
5. replay the 2026-08-15 strict three-item baseline and regression fixtures;
6. accumulate multi-day stage attribution;
7. only then use stage distributions as one input to a separate Promotion Review.

## 13. Acceptance tests for a future implementation

At minimum:

- selected source + 5 results + target snapshot → not a source-attempt miss;
- selected source + attempt HTTP failure + 0 results → `source_attempt`;
- selected source + successful attempt + 0 results → `surface_observation`;
- effective route + complete selection ledger + no selected source in window → `source_selection`;
- target raw snapshot + `source_initial_cap_reserve` → `prefilter`;
- target raw snapshot + acquisition failure → `acquisition`;
- body observed + L4 block → `l4`;
- L4 eligible + L5 reject → `l5`;
- L5 actionable + portfolio exclusion → `portfolio`;
- missing attempt ledger → `unknown` or compound unresolved boundary, never guessed parser failure;
- post-cutoff target capture sets late-observation fields but does not mutate strict outcome;
- persistence/readback failure produces `persistence` or evidence gap rather than a false causal stage;
- partial-observation v1.2 item remains partial and does not enter strict attribution headline denominator.

## 14. Promotion interpretation

Stage attribution is diagnostic evidence, not a promotion threshold by itself.

Promotion-grade reporting must keep separate:

- strict Recall numerator/denominator;
- stage-attributed strict misses;
- attribution evidence completeness;
- unresolved miss fraction;
- late observations;
- source/language cohort slices;
- Human Utility and multi-day Editorial A/B evidence.

No route rewrite, source-cap expansion, L4/L5/L6 change or promotion action should be inferred from one three-item strict cohort.