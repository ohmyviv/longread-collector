# Full-Funnel Audit v1

## Purpose

`full-funnel-audit-v1` is an artifact-only observability layer for the current
v0.6 parallel shadow. It measures where observed candidates leave the funnel
without changing Collector behavior, frozen L4/L5 semantics, selection policy,
network budgets, or Sheet state.

The audit consumes an already-produced `collector-result.json`. It performs no
network requests and no Google Sheet writes.

## Measurement chain

The headline chain is:

`attempted discovery surfaces → raw discovery observations → unique article URLs → gate acquire → control body observed → acquisition success → canonicalized after acquisition success → editorial eligible for decision → strong/editorial actionable → selected`

Definitions:

- **attempted discovery surfaces**: native source attempts plus configured open
  query attempts. Native source identities come from `source_selection_audit`.
  Open-query identities are recoverable from non-zero `firecrawl_search`
  discovery events; zero-result query attempts remain aggregate-only under the
  current artifact contract and are explicitly reported as unattributed.
- **raw discovery observation**: one `discovery_result` event. This is not
  assumed unique.
- **unique article URL**: distinct `canonical_url_hint`, falling back to the
  observed URL.
- **control body observed**: one v0.6 `acquisition_result` produced by sharing
  control acquisition evidence. No result means the control did not expose a
  body to the shadow; this is an observation boundary, not an acquisition
  failure.
- **acquisition success**: acquisition result with technical status `success`.
  `partial` and `failed` remain separately visible.
- **canonicalized after acquisition success**: successful canonical result for
  an item whose acquisition result was `success`.
- **editorial eligible for decision**: successful-acquisition item with an L5
  verdict other than `insufficient_evidence`.
- **strong / editorial actionable**: frozen L5 verdict `recommend` or
  `consider`. This matches the existing policy set that can proceed into normal
  portfolio selection. `recommend` is also reported separately as
  `high_editorial_value`.
- **selected**: `selection_result.attributes.selected == true`.

The audit does not reinterpret L5 scores and does not change the frozen
`editorial-judge-v0.6-pr7.2`.

## Observation-aware closure

The generic `v06-stage-event-metrics-v1` contract expects all seven result
events, including Projection. The current parallel shadow intentionally does
not emit Projection and only emits Acquisition/Canonical/Editorial when a
control body was observed.

Therefore this audit uses a narrower closure rule appropriate to the current
shadow artifact:

1. every item must have one Discovery, Gate, and Selection result;
2. if Acquisition is observed, Canonical and Editorial must also be observed;
3. if Acquisition is not observed, Canonical and Editorial must not be
   fabricated;
4. Projection is reported as coverage but is not required for v1 observation
   closure.

This prevents unobserved bodies from being mislabeled as technical failures.

## Failure families

Stage-native `technical_status`, `flow_status`, and `reason_code` remain the
authoritative facts. `failure_family` is a derived audit-only grouping:

- `gate_reject`
- `gate_defer`
- `body_not_observed`
- `acquisition_failed`
- `canonical_failed`
- `editorial_insufficient_evidence`
- `editorial_low_value_or_reject`
- `source_chase_required`
- `portfolio_not_selected`
- `selected`
- `instrumentation_incomplete`

No failure-family value is written back into runtime state.

## Current artifact limitations

- Open-query attempt identity is only guaranteed for queries that returned at
  least one discovery result; total attempted query count remains available as
  `queries_count`.
- Projection result events are not emitted by the current shadow runner.
- The shadow portfolio is limited to the shared-control-body subset; the audit
  must not claim quality truth for bodies the control did not acquire.
- Artifact retention is currently seven days, so this is not yet a durable
  multi-month analytical store.

These are observability limitations, not reasons to increase acquisition or
Firecrawl budgets.

## Execution

```bash
python -m longread_collector.full_funnel_audit_v1_runner \
  --input collector-result.json \
  --output full-funnel-audit-v1.json
```

The runner only reads the input file and optionally writes a local JSON output.
It is intentionally not wired into the Collector workflow during the active
Phase 0B natural-acceptance window.
