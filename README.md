# Longread Collector / 每日深度长文采集器

A source-discovery, acquisition, normalization, and editorial-candidate pipeline for the **每日深度长文推荐** workflow.

> **Project status:** experimental and under shadow evaluation. The current control pipeline remains `v0.5.6m`; the `v0.6` architecture runs in parallel for validation and has **not** been promoted to production.

## What it does

The collector is designed to turn a broad set of public web sources into a smaller, auditable pool of long-form reading candidates.

At a high level, it:

1. discovers candidate URLs from registered sources and bounded open-web discovery;
2. decides which candidates are worth acquiring;
3. retrieves public article content and metadata;
4. normalizes each item into a canonical article representation;
5. evaluates editorial suitability and content risks;
6. applies freshness, source, and portfolio policies before producing a candidate set.

The project separates **technical retrieval success** from **editorial suitability**. Successfully fetching a page does not automatically make it a recommendation candidate.

## Current architecture

The `v0.6` pipeline is organized into six layers:

```text
L1  Discovery
L2  Acquisition Gate
L3  Acquisition
L4  Canonical Article
L5  Editorial Judge
L6  Policy & Portfolio
```

This architecture is being introduced with a strangler pattern:

```text
v0.5.6m control pipeline
        │
        ├── production/control behavior
        │
        └── shared evidence ──> v0.6 shadow pipeline
                               │
                               └── evaluation only
```

The shadow pipeline is intentionally isolated from production promotion. Manual runs, replay tests, and green CI alone are not sufficient to promote it; natural scheduled-run evidence and editorial quality gates are also required.

For the architecture and migration design, see [docs/V0.6_ARCHITECTURE_AND_MIGRATION.md](docs/V0.6_ARCHITECTURE_AND_MIGRATION.md).

## Discovery and acquisition

The collector supports multiple discovery and retrieval routes, including:

- RSS and Atom feeds;
- publication section and archive pages;
- publication APIs where available;
- sitemaps and other source-native routes;
- Jina Reader for public-page retrieval;
- bounded Firecrawl fallback when a source-native route is unavailable or unsuitable.

The implementation prefers source-native and lower-cost routes before using paid fallback services.

## Access policy

This project is intended for **publicly accessible content only**.

It does not attempt to bypass:

- login requirements;
- paywalls;
- authentication controls;
- robots or site-level access restrictions;
- other technical access controls.

Credentials for external services are supplied at runtime through environment variables or GitHub Actions Secrets and are not stored in the repository.

## Editorial model

The pipeline distinguishes several questions that are easy to conflate in a web collector:

- **Can the page be discovered?**
- **Should network/body acquisition budget be spent on it?**
- **Was a usable article body retrieved?**
- **What is the canonical article and publication date?**
- **Is the item editorially suitable?**
- **Should it enter the final candidate portfolio today?**

This separation is especially important for pages that are technically valid HTML but are poor editorial candidates, such as navigation pages, promotional pages, event listings, transcripts, duplicated syndication, or stale material.

## Local development

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e . pytest
pytest -q
```

To use external services locally, copy the example environment file and provide your own credentials:

```bash
cp .env.example .env
```

The example file contains placeholders only. Do not commit real API keys, service-account files, tokens, or `.env` files.

Useful CLI commands include:

```bash
# Check local configuration and connected dependencies
longread-collector doctor

# Include remote connectivity checks
longread-collector doctor --test-remote

# Run a configured collection group
longread-collector collect --group pre_report

# Inspect extraction behavior for one public URL
longread-collector extract "https://example.com/article"
```

Some commands require a configured Google Sheet and external-service credentials.

## Testing and validation

The repository contains unit, regression, replay, workflow-boundary, and shadow-pipeline tests.

The ordinary pull-request CI path is intentionally public-safe: it runs repository tests without access to production credentials or production Google Sheet writes.

Live validation workflows are separate trusted workflows and may require repository secrets.

The project also distinguishes between:

- **offline/replay validation** — deterministic regression evidence;
- **manual live validation** — operational smoke testing;
- **natural shadow runs** — scheduled evidence used for promotion decisions.

These evidence types are not interchangeable.

## Repository security

Before the repository was made public, its reachable Git history was scanned with Gitleaks and TruffleHog and the results were manually adjudicated. Public-readiness controls and the audit procedure are documented in:

- [docs/PUBLIC_READINESS.md](docs/PUBLIC_READINESS.md)
- [docs/SECRET_SCAN_ADJUDICATION_2026-08-08.md](docs/SECRET_SCAN_ADJUDICATION_2026-08-08.md)

GitHub Actions artifacts used for operational validation are retained for a limited period.

## Documentation

Key design documents include:

- [v0.6 architecture and migration](docs/V0.6_ARCHITECTURE_AND_MIGRATION.md)
- [v0.6 canonical article](docs/V0.6_PR2_CANONICAL_ARTICLE.md)
- [v0.6 editorial judge](docs/V0.6_PR3_EDITORIAL_JUDGE.md)
- [v0.6 policy and portfolio](docs/V0.6_PR4_POLICY_PORTFOLIO.md)
- [v0.6 acquisition service](docs/V0.6_PR5_ACQUISITION_SERVICE.md)
- [v0.6 discovery and acquisition gate](docs/V0.6_PR6_DISCOVERY_ACQUISITION_GATE.md)
- [v0.6 quality calibration](docs/V0.6_PR7_1_QUALITY_CALIBRATION.md)

Older version documents remain in `docs/` as implementation history and should not be interpreted as the current production state.

## Current production boundary

As of the current `v0.6` shadow phase:

```text
control pipeline:      v0.5.6m
v0.6 mode:             shadow evaluation
v0.6 primary writes:   disabled
automatic promotion:   disabled
editor integration:    not promoted
```

The repository may therefore contain newer architecture than the version currently trusted as the production control. That difference is deliberate.