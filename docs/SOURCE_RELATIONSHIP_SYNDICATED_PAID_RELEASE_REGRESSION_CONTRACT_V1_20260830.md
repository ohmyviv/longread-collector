# Source Relationship / Syndicated Paid Release Regression Contract v1

Date: 2026-08-30  
Status: **DESIGN / OFFLINE REGRESSION ONLY**  
Tracks: Issue #40  
Production effect: **NONE**

## 1. First-principles problem

The host domain is a transport/location fact. It is not necessarily the editorial publisher and cannot by itself establish editorial trust.

A page hosted on Yahoo Finance, MSN, aggregation portals or distribution networks may represent:
- independent editorial work by the host;
- licensed wire copy;
- syndicated editorial work from another publisher;
- a paid press release;
- a market-research promotion;
- other externally supplied content.

Collector must preserve `hosting_source`, `canonical/original publisher`, and `source_relationship` as separate evidence dimensions.

## 2. Reference failure

Fixed reference from #40:
`https://finance.yahoo.com/news/ai-drug-discovery-transforms-pharmaceutical-163843229.html`

Historical behavior:
- hosting surface = Yahoo Finance `/news/`;
- predicted = `formal_candidate`;
- human review = deterministic severe false accept;
- body structure was a third-party market-research / promotional release, not independent Yahoo Finance editorial reporting.

The defect is a source-relationship + genre-evidence failure, not a reason to blacklist all Yahoo Finance pages.

## 3. Frozen causal dimensions

A future canonical/source-resolution layer should reason independently about:
- `hosting_source`;
- `declared_byline_or_wire`;
- `original_publisher`;
- `source_relationship`;
- `editorial_genre`;
- `promotion/market-report signals`.

Possible semantic relationship classes include:
- host_original_editorial;
- syndicated_editorial;
- licensed_wire;
- syndicated_paid_release;
- unknown_external_origin.

Exact enum names remain implementation details; the separation is frozen.

## 4. High-confidence paid-release evidence

No single token is sufficient in every context. High-confidence evidence should combine source attribution and body/template signals such as:
- `GLOBE NEWSWIRE`, `PR Newswire`, `Business Wire` attribution;
- named market-research vendor attribution;
- market-size/CAGR forecast framing dominating the article;
- `download sample`, `request sample`, `buy report`, contact/sales CTA;
- report-title / segmentation boilerplate;
- repeated promotional market forecast language;
- external release metadata.

When sufficiently strong, the canonical relationship should be represented as an externally supplied paid/promotional release and remain distinguishable from host editorial work.

## 5. Counterexamples required before any implementation

A future patch must include controlled examples for at least:

### A. Syndicated paid release
Expected: source relationship reflects paid/external release; longread formal candidacy rejected downstream.

### B. Reuters/AP/AFP or another clearly editorial wire story hosted on the same/analogous portal
Expected: do not reject merely because hosting domain is an aggregator/portal; preserve editorial origin and apply normal duplicate/editorial policy.

### C. Host-original editorial article
Expected: do not downgrade because the host also carries paid releases elsewhere.

### D. Ambiguous external content
Expected: explicit uncertainty/defer or ordinary evidence path; do not convert absence of proof into deterministic paid-release classification.

## 6. Acceptance invariants

A future runtime patch is acceptable only if:
1. the fixed #40 reference no longer enters formal longread candidacy;
2. the decision is attributable to source-relationship/genre evidence, not a blanket Yahoo domain blacklist;
3. trusted editorial wire/host-original controls do not regress;
4. hosting and canonical/original source remain independently auditable;
5. source relationship is resolved before downstream policy projection;
6. no 07:35 Editor, auto-promotion, source cap or network-budget change is bundled with the fix.

## 7. Recommended implementation sequence

1. capture structural metadata/text snippets sufficient for offline fixtures;
2. implement source-relationship evidence extraction in the v0.6 Canonical Article layer or a pure helper;
3. run fixed positive and counterexample regressions;
4. replay the known human-review corpus;
5. only after separate runtime authorization, expose the relationship in v0.6 Shadow;
6. observe natural false-positive/false-negative behavior before primary use.

Do not solve this as a host-domain denylist.

## 8. Readiness interpretation

This contract primarily advances **Measurement integrity (M-axis)** and the canonical/source-resolution portion of **Acquisition/Canonical readiness**. It does not prove source value or authorize Production promotion.
