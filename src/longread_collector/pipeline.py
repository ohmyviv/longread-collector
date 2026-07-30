from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import yaml

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings
from .extraction import FallbackBudget, extract_article
from .models import DiscoveredURL, ExtractedArticle
from .normalization import canonicalize_url, domain_from_url, stable_id
from .quality import filter_discovered
from .sheets import GoogleSheetStore


def load_queries(path: Path, group_id: str | None = None) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    queries = raw.get("queries", [])
    if not isinstance(queries, list):
        raise ValueError("queries.yaml must contain a list under 'queries'")
    result = [query for query in queries if isinstance(query, dict) and query.get("query")]
    if group_id:
        result = [query for query in result if str(query.get("group_id", "")) == group_id]
    return sorted(result, key=lambda item: int(item.get("sequence", 0)))


def _source_domain(homepage_url: str) -> str:
    return urlsplit(homepage_url).netloc.lower().removeprefix("www.")


def build_directed_source_queries(
    sources: list[dict[str, Any]],
    *,
    group_id: str | None,
    started: datetime,
    max_sources: int = 3,
) -> list[dict[str, Any]]:
    """Rotate a bounded number of enabled source-registry entries per run."""
    if not sources or max_sources <= 0:
        return []
    offset = started.toordinal() + started.hour + sum(ord(char) for char in (group_id or "all"))
    ordered = sources[offset % len(sources):] + sources[: offset % len(sources)]
    selected = ordered[: min(max_sources, len(ordered))]
    result: list[dict[str, Any]] = []
    for sequence, source in enumerate(selected, start=1):
        domain = _source_domain(str(source.get("homepage_url", "")))
        if not domain:
            continue
        language = str(source.get("language", "en")).strip() or "en"
        query = (
            "最新 深度 调查 分析 长文"
            if language == "zh"
            else "latest longform investigation analysis"
        )
        result.append(
            {
                "query_id": f"source:{source.get('source_id')}",
                "group_id": group_id or "all",
                "scheduled_time_bj": started.strftime("%H:%M"),
                "sequence": -100 + sequence,
                "language": language,
                "query": query,
                "limit": 4,
                "tbs": "qdr:d3",
                "country": "",
                "location": "",
                "include_domains": [domain],
                "exclude_domains": [],
                "categories": [],
                "purpose": "directed_source_scan",
                "source_id": str(source.get("source_id", "")),
            }
        )
    return result


class CollectorPipeline:
    def __init__(self, settings: Settings, store: GoogleSheetStore | None = None) -> None:
        self.settings = settings
        self.firecrawl = FirecrawlClient(
            settings.firecrawl_base_url, settings.firecrawl_api_key
        )
        self.jina = JinaReaderClient(
            settings.jina_reader_base_url, settings.jina_api_key
        )
        self.store = store or GoogleSheetStore(settings)
        self.tz = ZoneInfo(settings.timezone)

    async def _discover(
        self, queries: list[dict[str, Any]]
    ) -> tuple[list[DiscoveredURL], list[dict[str, Any]]]:
        async def one(query_cfg: dict[str, Any]):
            results, meta = await self.firecrawl.search(
                str(query_cfg["query"]),
                int(query_cfg.get("limit", 8)),
                str(query_cfg.get("tbs") or self.settings.firecrawl_tbs or "") or None,
                country=str(query_cfg.get("country") or "") or None,
                location=str(query_cfg.get("location") or "") or None,
                include_domains=list(query_cfg.get("include_domains") or []),
                exclude_domains=list(query_cfg.get("exclude_domains") or []),
                categories=list(query_cfg.get("categories") or []),
            )
            for item in results:
                item.language = str(query_cfg.get("language", ""))
                item.query_or_source = str(
                    query_cfg.get("query_id")
                    or query_cfg.get("id")
                    or query_cfg["query"]
                )
                item.metadata["query_group"] = str(query_cfg.get("group_id", ""))
                item.metadata["scheduled_time_bj"] = str(
                    query_cfg.get("scheduled_time_bj", "")
                )
                item.metadata["purpose"] = str(query_cfg.get("purpose", ""))
                item.metadata["source_id"] = str(query_cfg.get("source_id", ""))
            return results, {
                "query_id": query_cfg.get("query_id") or query_cfg.get("id"),
                "purpose": query_cfg.get("purpose", ""),
                **meta,
            }

        output = await asyncio.gather(
            *(one(query) for query in queries), return_exceptions=True
        )
        found: list[DiscoveredURL] = []
        logs: list[dict[str, Any]] = []
        for item in output:
            if isinstance(item, Exception):
                logs.append(
                    {
                        "success": False,
                        "error_type": type(item).__name__,
                        "error_message": str(item),
                    }
                )
                continue
            results, meta = item
            found.extend(results)
            logs.append({"success": True, **meta})
        return found, logs

    async def _extract_all(
        self,
        discovered: list[DiscoveredURL],
        fallback_budget: FallbackBudget,
    ) -> list[ExtractedArticle]:
        semaphore = asyncio.Semaphore(self.settings.max_concurrency)

        async def one(item: DiscoveredURL) -> ExtractedArticle:
            async with semaphore:
                return await extract_article(
                    item,
                    self.jina,
                    self.firecrawl,
                    self.settings,
                    fallback_budget,
                )

        return await asyncio.gather(*(one(item) for item in discovered))

    async def collect(
        self,
        group_id: str | None = None,
        query_file: Path | None = None,
    ) -> dict[str, Any]:
        started = datetime.now(self.tz)
        run_id = f"COL-{started.strftime('%Y%m%d-%H%M%S')}-BJT-{group_id or 'all'}"
        directed_queries: list[dict[str, Any]] = []
        if query_file is None:
            queries = self.store.load_queries(group_id)
            language = "zh" if str(group_id or "").startswith("zh_") else "en"
            directed_queries = build_directed_source_queries(
                self.store.load_source_registry(language),
                group_id=group_id,
                started=started,
            )
            queries = directed_queries + queries
        else:
            queries = load_queries(query_file, group_id)
        if not queries:
            raise ValueError(f"No enabled queries found for group={group_id!r}")

        used_today = self.store.count_firecrawl_scrapes_today()
        remaining = max(
            0,
            self.settings.firecrawl_fallback_daily_limit - used_today,
        )
        fallback_budget = FallbackBudget(remaining=remaining)
        summary: dict[str, Any] = {
            "collector_run_id": run_id,
            "started_at_bj": started.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "source_registry+firecrawl_search+jina_reader+budgeted_firecrawl_fallback",
            "query_group": group_id or "all",
            "queries_count": len(queries),
            "sources_scanned": len(directed_queries),
            "scrape_attempts_today": used_today,
            "fallback_remaining": remaining,
        }
        try:
            discovered, discovery_logs = await self._discover(queries)
            summary["search_credits"] = sum(
                int(log.get("credits_used") or 0)
                for log in discovery_logs
                if log.get("success")
            )
            summary["urls_discovered"] = len(discovered)
            discovered_domains = {
                domain_from_url(canonicalize_url(item.url)) for item in discovered
            }
            deduped, prefilter_rejections = filter_discovered(
                discovered,
                max_urls=self.settings.max_urls_per_run,
                max_per_domain=2,
            )
            existing = self.store.existing_article_ids()
            summary["urls_new"] = sum(
                1
                for item in deduped
                if stable_id(canonicalize_url(item.url)) not in existing
            )
            articles = await self._extract_all(deduped, fallback_budget)
            pairs = list(zip(deduped, articles, strict=True))
            summary["jina_success"] = sum(
                1
                for article in articles
                if article.extractor_used == "jina"
                and article.extraction_status == "success"
            )
            summary["firecrawl_success"] = sum(
                1
                for article in articles
                if article.extractor_used == "firecrawl"
                and article.extraction_status == "success"
            )
            summary["failed"] = sum(
                1 for article in articles if article.extraction_status != "success"
            )
            summary["written_cache"] = self.store.upsert_articles(run_id, pairs)
            self.store.append_extraction_logs(articles)
            actual_fallbacks = sum(
                1
                for article in articles
                for attempt in article.extraction_attempts
                if attempt.get("extractor") == "firecrawl"
                and attempt.get("error_type") != "DailyFallbackBudgetExhausted"
            )
            summary["scrape_attempts_today"] = used_today + actual_fallbacks
            summary["fallback_remaining"] = fallback_budget.remaining
            summary["final_status"] = "success"

            rejection_counts = Counter(
                rejection["reason"] for rejection in prefilter_rejections
            )
            disposition_counts = Counter(
                article.candidate_disposition for article in articles
            )
            page_role_counts = Counter(article.page_role for article in articles)
            canonical_sources = {
                article.canonical_source
                for article in articles
                if article.canonical_source
                and article.candidate_disposition != "reject"
            }
            content_clusters = {
                article.content_cluster_id
                for article in articles
                if article.content_cluster_id
            }
            summary["notes"] = (
                f"classification_version=collector-v0.4.0; "
                f"dispositions={dict(disposition_counts)}; "
                f"page_roles={dict(page_role_counts)}; "
                f"eligible_for_editor={sum(article.eligible_for_editor for article in articles)}; "
                f"valid_extractions={sum(article.extraction_status == 'success' for article in articles)}; "
                f"directed_sources={len(directed_queries)}; "
                f"discovered_technical_domains={len(discovered_domains)}; "
                f"nonreject_canonical_sources={len(canonical_sources)}; "
                f"content_clusters={len(content_clusters)}; "
                f"prefilter_rejected={len(prefilter_rejections)}; "
                f"prefilter_reasons={dict(rejection_counts)}; "
                f"discovery_failures={sum(not log.get('success', False) for log in discovery_logs)}"
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
                        "error": (
                            f"{type(promote_exc).__name__}: {promote_exc}"
                        )[:1000],
                    }
        return summary
