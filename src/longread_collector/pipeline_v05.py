from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .native_discovery import NativeSourceDiscovery, select_sources_for_run
from .normalization import canonicalize_url, domain_from_url, stable_id
from .pipeline import (
    CollectorPipeline,
    build_directed_source_queries,
    load_queries,
)
from .quality import filter_discovered
from .runtime_config import load_collector_runtime_config
from .shadow import append_shadow_ab
from .source_chase import build_source_chase_queries
from .source_chase_identity_v056j import (
    evaluate_source_chase_identity,
    reject_source_chase_mismatch,
)
from .source_registry_metrics import update_source_registry_metrics
from .extraction import FallbackBudget


class NativeCollectorPipeline(CollectorPipeline):
    """Collector v0.5 shadow pipeline with native source discovery first."""

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        started = datetime.now(self.tz)
        run_id = f"COL-{started.strftime('%Y%m%d-%H%M%S')}-BJT-{group_id or 'all'}"
        runtime = load_collector_runtime_config(self.store)
        source_registry: list[dict[str, Any]] = []
        selected_sources: list[dict[str, Any]] = []
        fallback_queries: list[dict[str, Any]] = []

        if query_file is None:
            queries = self.store.load_queries(group_id)
            language = "zh" if str(group_id or "").startswith("zh_") else "en"
            source_registry = self.store.load_source_registry(language)
            selected_sources = select_sources_for_run(
                source_registry,
                started=started,
                max_sources=runtime.native_source_scans_per_run,
            )
        else:
            queries = load_queries(query_file, group_id)

        if not queries and not selected_sources:
            raise ValueError(f"No enabled queries or sources found for group={group_id!r}")

        used_today = self.store.count_firecrawl_scrapes_today()
        remaining = max(0, self.settings.firecrawl_fallback_daily_limit - used_today)
        fallback_budget = FallbackBudget(remaining=remaining)
        summary: dict[str, Any] = {
            "collector_run_id": run_id,
            "started_at_bj": started.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": (
                "native_source_discovery+firecrawl_search_fallback+jina_reader+"
                "source_chase+budgeted_firecrawl_scrape_fallback"
            ),
            "query_group": group_id or "all",
            "queries_count": len(queries),
            "sources_scanned": len(selected_sources),
            "scrape_attempts_today": used_today,
            "fallback_remaining": remaining,
        }

        try:
            native_items = []
            native_logs: list[dict[str, Any]] = []
            fallback_sources: list[dict[str, Any]] = []
            if selected_sources:
                native = NativeSourceDiscovery(
                    timeout=float(runtime.native_source_timeout_seconds),
                    concurrency=runtime.native_source_concurrency,
                )
                native_batch = await native.discover(
                    selected_sources,
                    limit_per_source=runtime.native_source_results_per_source,
                    started=started,
                    freshness_days=runtime.native_source_freshness_days,
                )
                native_items = native_batch.items
                native_logs = native_batch.logs
                fallback_sources = native_batch.fallback_sources
                fallback_queries = build_directed_source_queries(
                    fallback_sources,
                    group_id=group_id,
                    started=started,
                    max_sources=len(fallback_sources),
                    result_limit=runtime.directed_source_results_per_query,
                    freshness=runtime.directed_source_freshness,
                )

            firecrawl_items, firecrawl_logs = await self._discover(
                fallback_queries + queries
            )
            discovered = native_items + firecrawl_items
            discovery_logs = native_logs + firecrawl_logs
            summary["queries_count"] = len(queries) + len(fallback_queries)
            summary["native_sources_succeeded"] = sum(
                bool(log.get("success")) for log in native_logs
            )
            summary["native_items_discovered"] = len(native_items)
            summary["native_fallback_sources"] = len(fallback_sources)

            initial_discovered_count = len(discovered)
            discovered_domains = {
                domain_from_url(canonicalize_url(item.url)) for item in discovered
            }
            deduped, prefilter_rejections = filter_discovered(
                discovered,
                max_urls=self.settings.max_urls_per_run,
                max_per_domain=2,
            )
            articles = await self._extract_all(deduped, fallback_budget)

            if runtime.source_registry_writeback:
                update_source_registry_metrics(
                    self.store,
                    attempted_source_ids=[
                        str(source.get("source_id", "")) for source in selected_sources
                    ],
                    discovered=deduped,
                    articles=articles,
                    completed_at=datetime.now(self.tz),
                )

            chase_queries = (
                build_source_chase_queries(
                    articles,
                    source_registry,
                    limit=runtime.source_chase_max_per_run,
                )
                if runtime.source_chase_max_depth > 0
                else []
            )
            chased_discovered, chase_logs = await self._chase_sources(
                chase_queries,
                runtime,
            )
            initial_urls = {canonicalize_url(item.url) for item in deduped}
            chased_discovered = [
                item
                for item in chased_discovered
                if canonicalize_url(item.url) not in initial_urls
            ]
            chased_deduped, chase_prefilter_rejections = filter_discovered(
                chased_discovered,
                max_urls=(
                    runtime.source_chase_max_per_run
                    * runtime.source_chase_results_per_query
                ),
                max_per_domain=2,
            )
            chased_articles = await self._extract_all(chased_deduped, fallback_budget)

            parents = {article.article_id: article for article in articles}
            source_chase_resolved = 0
            source_chase_identity_rejected = 0
            for discovered_item, chased_article in zip(
                chased_deduped,
                chased_articles,
                strict=True,
            ):
                parent_id = str(
                    discovered_item.metadata.get("source_chase_parent_article_id", "")
                )
                parent = parents.get(parent_id)
                if parent is None:
                    continue
                included_domains = set(
                    discovered_item.metadata.get("source_chase_include_domains", [])
                )
                identity = evaluate_source_chase_identity(
                    parent=parent,
                    chased=chased_article,
                    included_domains=included_domains,
                )
                identity_payload = identity.as_dict()
                chased_article.metadata["source_chase_identity"] = identity_payload
                parent.metadata.setdefault("source_chase_attempts", [])
                parent.metadata["source_chase_attempts"].append(
                    {
                        "resolved_article_id": chased_article.article_id,
                        "resolved_url": chased_article.url_canonical,
                        "seed_title": parent.title,
                        "chased_title": chased_article.title,
                        "identity_score": identity.score,
                        "identity_gate_result": identity.result,
                        "identity_evidence": identity.evidence,
                    }
                )

                if identity.matched:
                    parent.original_url = chased_article.url_canonical
                    parent.canonical_source = chased_article.canonical_source
                    parent.metadata.setdefault("source_chase", {})
                    parent.metadata["source_chase"].update(
                        {
                            "resolved": True,
                            "resolved_article_id": chased_article.article_id,
                            "resolved_url": chased_article.url_canonical,
                            "seed_title": parent.title,
                            "chased_title": chased_article.title,
                            "identity_score": identity.score,
                            "identity_gate_result": identity.result,
                            "identity_evidence": identity.evidence,
                        }
                    )
                    source_chase_resolved += 1
                    continue

                reject_source_chase_mismatch(chased_article, identity)
                source_chase_identity_rejected += 1
                source_chase_state = parent.metadata.setdefault("source_chase", {})
                if not source_chase_state.get("resolved"):
                    source_chase_state.update(
                        {
                            "resolved": False,
                            "reason": "chase_no_match",
                            "last_attempt_article_id": chased_article.article_id,
                            "last_attempt_url": chased_article.url_canonical,
                            "seed_title": parent.title,
                            "chased_title": chased_article.title,
                            "identity_score": identity.score,
                            "identity_gate_result": identity.result,
                            "identity_evidence": identity.evidence,
                        }
                    )

            all_discovered = deduped + chased_deduped
            all_articles = articles + chased_articles
            pairs = list(zip(all_discovered, all_articles, strict=True))
            existing = self.store.existing_article_ids()
            summary["urls_discovered"] = initial_discovered_count + len(chased_discovered)
            summary["urls_new"] = sum(
                1
                for item in all_discovered
                if stable_id(canonicalize_url(item.url)) not in existing
            )
            summary["jina_success"] = sum(
                1
                for article in all_articles
                if article.extractor_used == "jina"
                and article.extraction_status == "success"
            )
            summary["firecrawl_success"] = sum(
                1
                for article in all_articles
                if article.extractor_used == "firecrawl"
                and article.extraction_status == "success"
            )
            summary["failed"] = sum(
                1 for article in all_articles if article.extraction_status != "success"
            )
            summary["written_cache"] = self.store.upsert_articles(run_id, pairs)
            self.store.append_extraction_logs(all_articles)
            if runtime.shadow_ab_writeback:
                append_shadow_ab(
                    self.store,
                    run_id=run_id,
                    query_group=group_id or "all",
                    articles=all_articles,
                    completed_at=datetime.now(self.tz),
                )
            actual_fallbacks = sum(
                1
                for article in all_articles
                for attempt in article.extraction_attempts
                if attempt.get("extractor") == "firecrawl"
                and attempt.get("error_type") != "DailyFallbackBudgetExhausted"
            )
            summary["scrape_attempts_today"] = used_today + actual_fallbacks
            summary["fallback_remaining"] = fallback_budget.remaining
            summary["search_credits"] = sum(
                int(log.get("credits_used") or 0)
                for log in discovery_logs + chase_logs
                if log.get("success")
            )
            summary["source_chase_identity_rejected"] = source_chase_identity_rejected
            summary["final_status"] = "success"

            all_rejections = prefilter_rejections + chase_prefilter_rejections
            rejection_counts = Counter(item["reason"] for item in all_rejections)
            disposition_counts = Counter(
                article.candidate_disposition for article in all_articles
            )
            page_role_counts = Counter(article.page_role for article in all_articles)
            canonical_sources = {
                article.canonical_source
                for article in all_articles
                if article.canonical_source
                and article.candidate_disposition != "reject"
            }
            content_clusters = {
                article.content_cluster_id
                for article in all_articles
                if article.content_cluster_id
            }
            native_method_counts = Counter(
                str(log.get("selected_method", ""))
                for log in native_logs
                if log.get("success")
            )
            summary["notes"] = (
                f"classification_version=collector-v0.4.0; "
                f"discovery_version=collector-v0.5.0-shadow; "
                f"dispositions={dict(disposition_counts)}; "
                f"page_roles={dict(page_role_counts)}; "
                f"eligible_for_editor={sum(article.eligible_for_editor for article in all_articles)}; "
                f"valid_extractions={sum(article.extraction_status == 'success' for article in all_articles)}; "
                f"selected_sources={len(selected_sources)}; "
                f"native_source_successes={sum(bool(log.get('success')) for log in native_logs)}; "
                f"native_methods={dict(native_method_counts)}; "
                f"native_items={len(native_items)}; "
                f"native_fallback_sources={len(fallback_sources)}; "
                f"firecrawl_directed_fallback_queries={len(fallback_queries)}; "
                f"source_chase_attempts={len(chase_queries)}; "
                f"source_chase_results={len(chased_deduped)}; "
                f"source_chase_resolved={source_chase_resolved}; "
                f"source_chase_identity_rejected={source_chase_identity_rejected}; "
                f"discovered_technical_domains={len(discovered_domains)}; "
                f"nonreject_canonical_sources={len(canonical_sources)}; "
                f"content_clusters={len(content_clusters)}; "
                f"prefilter_rejected={len(all_rejections)}; "
                f"prefilter_reasons={dict(rejection_counts)}; "
                f"discovery_failures={sum(not log.get('success', False) for log in discovery_logs)}; "
                f"source_chase_failures={sum(not log.get('success', False) for log in chase_logs)}"
            )
        except Exception as exc:
            summary["final_status"] = "failed"
            summary["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
            raise
        finally:
            summary["completed_at_bj"] = datetime.now(self.tz).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self.store.append_collector_run(summary)
            if summary.get("final_status") == "success":
                await asyncio.sleep(2)
                try:
                    summary["promotion"] = self.store.maybe_auto_promote()
                except Exception as promote_exc:
                    summary["promotion"] = {
                        "promoted": False,
                        "error": f"{type(promote_exc).__name__}: {promote_exc}"[:1000],
                    }
        return summary
