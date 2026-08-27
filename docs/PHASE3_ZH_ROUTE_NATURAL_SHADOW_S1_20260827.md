# Phase 3 — Chinese Route Portfolio Natural Shadow S1

Date: 2026-08-27  
Status: **paired natural metadata Shadow only**  
Promotion status: **NOT_READY**

## 1. Purpose

S1 tests whether a richer set of first-party Chinese editorial surfaces improves measurable Discovery coverage before any production route, candidate-selection or body-extraction change is considered.

The experiment is intentionally narrower than a Collector rewrite. It asks:

> When the existing source-selection policy naturally chooses a target Chinese source, what additional recent first-party article metadata would a Treatment route portfolio observe at approximately the same time as the existing Control route?

It does **not** ask yet whether those Treatment items should consume one of the 32 body attempts.

## 2. Paired natural design

The existing Phase 0B source-selection policy remains authoritative.

For each normal scheduled run:

1. Control selects sources exactly as before.
2. Control native discovery runs exactly as before.
3. If and only if the run is a Chinese group (`zh_midday` / `zh_evening`) and a naturally selected source has an S1 Treatment portfolio, Treatment immediately scans the configured first-party metadata surfaces.
4. Treatment returns no candidates to Control. The original Control `NativeDiscoveryBatch` is returned unchanged.
5. Control continues through Firecrawl search, candidate selection, 24+8 staged extraction, article-cache persistence and v0.6 Shadow exactly as before.
6. Only after the authoritative Control run returns `final_status=success` are Treatment route/item observations written to their sidecar sheets.

This ordering prevents two major biases:

- Treatment does not receive a long post-run timing advantage.
- A failed/orphan Control run cannot leave route telemetry that later masquerades as promotion-grade coverage evidence.

## 3. Hard S1 invariants

The following are regression-test requirements, not editorial preferences:

1. `ZH_ROUTE_SHADOW_BODY_MODE=metadata_only`.
2. Treatment body requests = **0**.
3. Treatment never calls Jina Reader or Firecrawl.
4. Treatment never calls candidate selection, reserve allocation or extraction.
5. `MAX_URLS_PER_RUN` remains **32**.
6. `NATIVE_SOURCE_CAP` and `ABSOLUTE_HOST_CAP` remain unchanged.
7. Firecrawl daily/group budgets remain unchanged.
8. `V06_PRIMARY_ENABLED=false`.
9. `AUTO_PROMOTE_WHEN_READY=false`.
10. `EDITOR_0735_CONNECTED=false`.
11. Production `article_cache` does not consume Treatment items.
12. Treatment failure is fail-open and returns the exact Control batch.
13. A source not naturally selected in that run is not scanned by Treatment and cannot be labelled a route miss.
14. Unknown publication time is observable but is **not** counted as proven-recent incremental coverage.
15. Same canonical article observed on several Treatment surfaces keeps all route provenance rows.

## 4. Route Portfolio model

Each first-party endpoint has a stable `surface_id`, a `publication_surface_id`, a transport type and one of five roles:

- `core_editorial` — primary editorial discovery surface.
- `breadth_safety` — limited broad surface to detect omitted editorial baskets.
- `timestamp_enrichment` — evidence-only time/metadata surface; no new candidate identity in S1.
- `noise_control` — explicit negative control such as commercial or micro-market-heavy feeds.
- `special_product` — separate publication/product identity; disabled from the S1 standard route union unless separately approved.

`domain == source domain` is never sufficient to prove publication-surface identity.

## 5. Initial four portfolios

### Yicai

Core:
- `yicai_finance` — `/news/jinrong/`
- `yicai_kechuang` — `/news/kechuang/`
- `yicai_auto` — `/news/automobile/`

Breadth:
- `yicai_news_breadth` — `/news/`

Controls:
- `yicai_info_control` — `/news/info/`
- `yicai_commercial_control` — `/news/ad/`

Commercial-surface items remain observable as negative-control evidence and are never interpreted as Standard Longread editorial coverage.

### EEO

Core:
- `eeo_business_industry` — `/shangyechanye/`
- `eeo_technology_plus` — `/jg/keji/`
- `eeo_politics_rss`
- `eeo_finance_rss`
- `eeo_industry_rss`

Control:
- `eeo_root_rss_control` — `app.eeo.com.cn/rss.php`

Special product (S1 inactive):
- EEO e-paper.

RSS is deliberately parsed over a long diagnostic horizon so HTTP-200 but obsolete feeds become `stale_surface` rather than false successful coverage.

### Caixin

Core:
- `caixin_companies`
- `caixin_finance`
- `caixin_china`

Breadth:
- `caixin_latest`

Control:
- `caixin_promotion_control` (`promote.caixin.com`)

Special product (S1 inactive):
- `caixin_deepview` / 商圈.

Promotion/video/photo/conference subdomains cannot be silently absorbed into ordinary Caixin editorial coverage merely through registrable-domain matching.

### Jiemian

Core:
- `jiemian_medicine` — `/lists/472.html`
- `jiemian_consumer` — `/lists/31.html`
- `jiemian_health_face` — `/lists/441.html`

Breadth:
- `jiemian_health` — `/lists/854.html`

JMedia/account/author surfaces cannot prove Jiemian-native publication coverage.

## 6. Publication-time semantics

S1 can observe the following list/feed evidence without body extraction:

- RSS `pubDate` / published time;
- `今天 HH:MM` / `昨天 HH:MM`;
- `YYYY-MM-DD HH:MM` or Chinese equivalent;
- `MM/DD HH:MM`.

Evidence is stored on the Treatment sidecar only and does not modify the Control `DiscoveredURL.published_at` used by Control freshness/ranking.

A URL with unknown publication time remains in route telemetry for diagnostic purposes, but:

```text
within_freshness = FALSE
```

until independent evidence proves the horizon. This prevents measurement coverage inflation.

## 7. New durable sidecars

S1 creates these tables lazily on the first successful eligible run:

### `collector_route_shadow_observations`

One row per:

```text
successful Control run × naturally selected source × Treatment surface
```

It stores:

- source/surface/publication-surface identity;
- endpoint and transport;
- request/parse success;
- `surface_status` (`observed`, `date_unknown`, `stale_surface`, `empty`, `request_failed`);
- item counts and exact-time counts;
- observed publication bounds;
- Control overlap / Treatment uniqueness;
- explicit noise counts;
- request latency and errors.

### `collector_route_shadow_items`

One row per:

```text
Control run × Treatment surface × canonical URL
```

It retains title, canonical URL, publication evidence, freshness proof, Control overlap, noise reason and full surface provenance.

An article observed on two Treatment surfaces therefore has two route-observation item rows. Canonical dedup is an analysis operation; provenance is not discarded at persistence time.

Both tables are sidecars. Neither participates in candidate selection or Editor input.

## 8. Negative controls and stale routes

S1 deliberately keeps some low-value surfaces because they provide denominator evidence about route quality.

Examples:

- Yicai commercial/info surfaces.
- EEO root RSS with known stock/ETF-flow contamination.
- Caixin promotion surface.

Likewise, an official RSS that is technically reachable but whose newest dated item lies outside the configured freshness window is:

```text
surface_status = stale_surface
```

not `observed` and not valid realized route coverage.

## 9. Frozen regression cases

Tests lock at least these contracts:

- Jiemian Medicine can parse the historical `08/25 09:28` style used by the known gene-therapy miss.
- Yicai relative clock evidence resolves without body extraction.
- EEO 2016-only RSS fixture becomes `stale_surface`.
- Generic substantive ETF reporting is not demoted merely because it contains `ETF`.
- ETF transactional snapshots remain identifiable as micro-market noise.
- Caixin promotion content is explicit noise and cannot leak into Companies coverage.
- Treatment failure returns Control batch unchanged.
- A non-target naturally selected source generates zero Treatment requests.
- Treatment body requests are always zero.
- Multi-surface same-canonical observations preserve multiple provenance rows.
- Workflow keeps the 32-attempt, v06-shadow-only, Editor-disconnected boundaries.

Historical Final misses are used only as regression examples. They are not route-ranking training labels.

## 10. What S1 metrics mean

S1 is allowed to report:

- surfaces attempted;
- request/parse success;
- surface status;
- total observed metadata;
- dated and exact-timestamp rates;
- proven-recent metadata count;
- Control overlap;
- proven-recent Treatment incremental URL count;
- noise composition.

S1 is **not** allowed to call Treatment items `eligible`, `editable`, `selected` or `Final-quality`, because no body/classification path has run on them.

It is also not promotion evidence by itself. Promotion-grade future Final Recall must still join to successful durable Control runs and exact publication-surface/horizon evidence under the v1.3.1 measurement contract.

## 11. S1 exit criteria before S2/S3

Do not move Treatment into candidate selection from one good run or one known historical miss.

The next decision should require several natural Chinese runs and answer, per source/surface:

1. Is the surface reliably reachable and parseable?
2. Does it provide useful exact/high-confidence publication time?
3. What share of proven-recent URLs are already in Control?
4. What share is genuinely incremental?
5. How much explicit commercial/micro-market/partner contamination does it add?
6. Does the route remain healthy across multiple days rather than one snapshot?

Only then should Treatment incremental URLs enter the fixed-32-attempt S3 counterfactual selector. A semantic Discovery change beyond metadata-only S1 requires a new evaluation cohort.
