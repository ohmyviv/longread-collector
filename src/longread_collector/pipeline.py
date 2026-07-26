from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
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
    result = [q for q in queries if isinstance(q, dict) and q.get("query")]
    if group_id:
        result = [q for q in result if str(q.get("group_id", "")) == group_id]
    return sorted(result, key=lambda x: int(x.get("sequence", 0)))


class CollectorPipeline:
    def __init__(self, settings: Settings, store: GoogleSheetStore | None = None) -> None:
        self.settings = settings
        self.firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)
        self.jina = JinaReaderClient(settings.jina_reader_base_url, settings.jina_api_key)
        self.store = store or GoogleSheetStore(settings)
        self.tz = ZoneInfo(settings.timezone)

    async def _discover(self, queries: list[dict[str, Any]]) -> tuple[list[DiscoveredURL], list[dict[str, Any]]]:
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
                item.query_or_source = str(query_cfg.get("query_id") or query_cfg.get("id") or query_cfg["query"])
                item.metadata["query_group"] = str(query_cfg.get("group_id", ""))
                item.metadata["scheduled_time_bj"] = str(query_cfg.get("scheduled_time_bj", ""))
            return results, {"query_id": query_cfg.get("query_id") or query_cfg.get("id"), **meta}

        output = await asyncio.gather(*(one(q) for q in queries), return_exceptions=True)
        found: list[DiscoveredURL] = []
        logs: list[dict[str, Any]] = []
        for item in output:
            if isinstance(item, Exception):
                logs.append({"success": False, "error_type": type(item).__name__, "error_message": str(item)})
                continue
            results, meta = item
            found.extend(results)
            logs.append({"success": True, **meta})
        return found, logs

    async def _extract_all(self, discovered: list[DiscoveredURL], fallback_budget: FallbackBudget) -> list[ExtractedArticle]:
        semaphore = asyncio.Semaphore(self.settings.max_concurrency)

        async def one(item: DiscoveredURL) -> ExtractedArticle:
            async with semaphore:
                return await extract_article(item, self.jina, self.firecrawl, self.settings, fallback_budget)

        return await asyncio.gather(*(one(item) for item in discovered))

    async def collect(self, group_id: str | None = None, query_file: Path | None = None) -> dict[str, Any]:
        started = datetime.now(self.tz)
        run_id = f"COL-{started.strftime('%Y%m%d-%H%M%S')}-BJT-{group_id or 'all'}"
        if query_file is None:
            queries = self.store.load_queries(group_id)
        else:
            queries = load_queries(query_file, group_id)
        if not queries:
            raise ValueError(f"No enabled queries found for group={group_id!r}")

        used_today = self.store.count_firecrawl_scrapes_today()
        remaining = max(0, self.settings.firecrawl_fallback_daily_limit - used_today)
        fallback_budget = FallbackBudget(remaining=remaining)
        summary: dict[str, Any] = {
            "collector_run_id": run_id,
            "started_at_bj": started.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "firecrawl_search+jina_reader+budgeted_firecrawl_fallback",
            "query_group": group_id or "all",
            "queries_count": len(queries),
            "sources_scanned": 0,
            "scrape_attempts_today": used_today,
            "fallback_remaining": remaining,
        }
        try:
            discovered, discovery_logs = await self._discover(queries)
            summary["search_credits"] = sum(int(x.get("credits_used") or 0) for x in discovery_logs if x.get("success"))
            summary["urls_discovered"] = len(discovered)
            summary["sources_scanned"] = len({domain_from_url(canonicalize_url(item.url)) for item in discovered})
            deduped, prefilter_rejections = filter_discovered(
                discovered,
                max_urls=self.settings.max_urls_per_run,
                max_per_domain=2,
            )
            existing = self.store.existing_article_ids()
            summary["urls_new"] = sum(1 for item in deduped if stable_id(canonicalize_url(item.url)) not in existing)
            articles = await self._extract_all(deduped, fallback_budget)
            pairs = list(zip(deduped, articles, strict=True))
            summary["jina_success"] = sum(1 for a in articles if a.extractor_used == "jina" and a.extraction_status == "success")
            summary["firecrawl_success"] = sum(1 for a in articles if a.extractor_used == "firecrawl" and a.extraction_status == "success")
            summary["failed"] = sum(1 for a in articles if a.extraction_status != "success")
            summary["written_cache"] = self.store.upsert_articles(run_id, pairs)
            self.store.append_extraction_logs(articles)
            actual_fallbacks = sum(
                1 for a in articles for attempt in a.extraction_attempts
                if attempt.get("extractor") == "firecrawl" and attempt.get("error_type") != "DailyFallbackBudgetExhausted"
            )
            summary["scrape_attempts_today"] = used_today + actual_fallbacks
            summary["fallback_remaining"] = fallback_budget.remaining
            summary["final_status"] = "success"
            rejection_counts: dict[str, int] = {}
            for rejection in prefilter_rejections:
                reason = rejection["reason"]
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            summary["notes"] = (
                f"eligible_for_editor={sum(a.eligible_for_editor for a in articles)}; "
                f"valid_extractions={sum(a.extraction_status == 'success' for a in articles)}; "
                f"prefilter_rejected={len(prefilter_rejections)}; "
                f"prefilter_reasons={rejection_counts}; "
                f"discovery_failures={sum(not x.get('success', False) for x in discovery_logs)}"
            )
        except Exception as exc:
            summary["final_status"] = "failed"
            summary["error_message"] = f"{type(exc).__name__}: {exc}"[:2000]
            raise
        finally:
            summary["completed_at_bj"] = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")
            self.store.append_collector_run(summary)
            if summary.get("final_status") == "success":
                await asyncio.sleep(2)
                try:
                    promotion = self.store.maybe_auto_promote()
                    summary["promotion"] = promotion
                except Exception as promote_exc:
                    summary["promotion"] = {
                        "promoted": False,
                        "error": f"{type(promote_exc).__name__}: {promote_exc}"[:1000],
                    }
        return summary
