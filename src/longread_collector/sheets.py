from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from .clients import compact_json
from .config import Settings
from .models import DiscoveredURL, ExtractedArticle

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

ARTICLE_HEADERS = [
    "article_id", "discovered_at_bj", "discovery_run_id", "discovery_method", "query_or_source",
    "url", "url_canonical", "domain", "title", "author", "published_at", "language",
    "canonical_source", "hosting_source", "description", "extractor_used", "extraction_status",
    "verification_level", "content_chars", "content_sha256", "content_markdown", "content_truncated",
    "metadata_json", "discovered_rank", "is_new_source_30d", "eligible_for_editor", "reject_reason",
    "first_seen_at_bj", "last_extracted_at_bj", "expires_at_bj", "selected_run_id", "selected_status", "notes",
    "page_role", "page_type", "content_type", "candidate_disposition", "special_candidate_type",
    "source_relationship", "original_publisher", "original_url", "wire_service", "source_action",
    "duplicate_type", "content_cluster_id", "classification_confidence", "classification_version",
    "classification_reason",
]

EXTRACTION_HEADERS = [
    "extraction_id", "article_id", "url", "attempted_at_bj", "extractor", "attempt_no", "http_status",
    "success", "body_chars", "title_found", "author_found", "date_found", "error_type", "error_message",
    "latency_ms", "credits_used", "response_meta_json",
]

RUN_HEADERS = [
    "collector_run_id", "started_at_bj", "completed_at_bj", "mode", "query_group", "queries_count",
    "sources_scanned", "urls_discovered", "urls_new", "jina_success", "firecrawl_success", "failed",
    "written_cache", "search_credits", "scrape_attempts_today", "fallback_remaining", "final_status",
    "error_message", "notes",
]

QUERY_HEADERS = [
    "query_id", "group_id", "scheduled_time_bj", "sequence", "language", "query", "limit", "tbs",
    "country", "location", "include_domains", "exclude_domains", "categories", "enabled", "purpose",
    "updated_at_bj",
]

SOURCE_HEADERS = [
    "source_id", "source_name", "language", "country_region", "subject_groups", "homepage_url", "rss_url",
    "sitemap_url", "news_sitemap_url", "author_pages", "newsletter_url", "access_type",
    "discovery_method", "preferred_extractor", "parser_config_json", "priority_tier", "enabled",
    "last_scanned_at_bj", "parser_success_rate_30d", "discovered_30d", "extracted_30d", "selected_30d",
    "notes", "updated_at_bj",
]


class GoogleSheetStore:
    def __init__(self, settings: Settings) -> None:
        creds = Credentials.from_service_account_file(
            str(settings.google_service_account_file), scopes=SCOPES
        )
        self.client = gspread.authorize(creds)
        self.book = self.client.open_by_key(settings.google_sheet_id)
        self.settings = settings
        self.tz = ZoneInfo(settings.timezone)

    def _now(self) -> datetime:
        return datetime.now(self.tz)

    def health_check(self) -> dict[str, Any]:
        required = {
            "source_registry", "article_cache", "extraction_log", "collector_runs",
            "collector_queries", "collector_config", "collector_health", "collector_ground_truth",
        }
        actual = {ws.title for ws in self.book.worksheets()}
        missing = sorted(required - actual)
        return {"spreadsheet_title": self.book.title, "missing_sheets": missing, "ok": not missing}

    def load_queries(self, group_id: str | None = None) -> list[dict[str, Any]]:
        ws = self.book.worksheet("collector_queries")
        rows = ws.get_all_records(expected_headers=QUERY_HEADERS)
        result: list[dict[str, Any]] = []
        for row in rows:
            enabled = str(row.get("enabled", "")).strip().upper() in {"TRUE", "1", "YES", "Y"}
            if not enabled:
                continue
            if group_id and str(row.get("group_id", "")).strip() != group_id:
                continue
            item = dict(row)
            for key in ("include_domains", "exclude_domains", "categories"):
                item[key] = [x.strip() for x in str(item.get(key, "")).split("|") if x.strip()]
            try:
                item["limit"] = int(item.get("limit") or 8)
            except (TypeError, ValueError):
                item["limit"] = 8
            try:
                item["sequence"] = int(item.get("sequence") or 0)
            except (TypeError, ValueError):
                item["sequence"] = 0
            result.append(item)
        return sorted(result, key=lambda x: (str(x.get("group_id", "")), int(x.get("sequence", 0))))

    def load_source_registry(self, language: str | None = None) -> list[dict[str, Any]]:
        """Return enabled directed sources for source-aware discovery."""
        ws = self.book.worksheet("source_registry")
        rows = ws.get_all_records(expected_headers=SOURCE_HEADERS)
        result: list[dict[str, Any]] = []
        for row in rows:
            enabled = str(row.get("enabled", "")).strip().upper() in {"TRUE", "1", "YES", "Y"}
            if not enabled:
                continue
            if language and str(row.get("language", "")).strip() != language:
                continue
            item = dict(row)
            item["subject_groups"] = [
                value.strip() for value in str(item.get("subject_groups", "")).split("|") if value.strip()
            ]
            item["discovery_method"] = [
                value.strip() for value in str(item.get("discovery_method", "")).split("|") if value.strip()
            ]
            result.append(item)
        priority = {"rotate": 0, "explore": 1, "monitor": 2}
        return sorted(
            result,
            key=lambda item: (
                priority.get(str(item.get("priority_tier", "")).strip(), 9),
                str(item.get("source_id", "")),
            ),
        )

    def existing_article_ids(self) -> dict[str, int]:
        ws = self.book.worksheet("article_cache")
        values = ws.col_values(1)
        return {value: index + 1 for index, value in enumerate(values[1:], start=1) if value}

    def existing_sources_30d(self) -> set[str]:
        ws = self.book.worksheet("article_cache")
        rows = ws.get_all_records(expected_headers=ARTICLE_HEADERS)
        threshold = self._now() - timedelta(days=30)
        result: set[str] = set()
        for row in rows:
            source = str(row.get("canonical_source") or "").strip()
            discovered = str(row.get("discovered_at_bj") or "")
            if not source:
                continue
            try:
                dt = datetime.fromisoformat(discovered.replace(" ", "T"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=self.tz)
                if dt >= threshold:
                    result.add(source)
            except ValueError:
                result.add(source)
        return result

    def count_firecrawl_scrapes_today(self) -> int:
        ws = self.book.worksheet("extraction_log")
        rows = ws.get_all_records(expected_headers=EXTRACTION_HEADERS)
        today = self._now().strftime("%Y-%m-%d")
        return sum(
            1 for row in rows
            if str(row.get("attempted_at_bj", "")).startswith(today)
            and str(row.get("extractor", "")).strip().lower() == "firecrawl"
            and str(row.get("error_type", "")).strip() != "DailyFallbackBudgetExhausted"
        )

    def upsert_articles(
        self,
        run_id: str,
        pairs: Iterable[tuple[DiscoveredURL, ExtractedArticle]],
    ) -> int:
        ws = self.book.worksheet("article_cache")
        id_rows = self.existing_article_ids()
        known_sources = self.existing_sources_30d()
        now = self._now()
        new_rows: list[list[object]] = []
        updates: list[tuple[int, list[object]]] = []
        written = 0
        for discovered, article in pairs:
            is_new_source = bool(
                article.canonical_source and article.canonical_source not in known_sources
            )
            row = [
                article.article_id, now.strftime("%Y-%m-%d %H:%M:%S"), run_id,
                discovered.discovery_method, discovered.query_or_source, article.url,
                article.url_canonical, article.domain, article.title, article.author,
                article.published_at, article.language or discovered.language,
                article.canonical_source, article.hosting_source, article.description,
                article.extractor_used, article.extraction_status, article.verification_level,
                article.content_chars, article.content_sha256, article.content_markdown,
                str(article.content_truncated).upper(), compact_json(article.metadata),
                discovered.rank, str(is_new_source).upper(),
                str(article.eligible_for_editor).upper(), article.reject_reason,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                now.strftime("%Y-%m-%d %H:%M:%S"),
                (now + timedelta(hours=self.settings.cache_hours)).strftime("%Y-%m-%d %H:%M:%S"),
                "", "", "",
                article.page_role, article.page_type, article.content_type,
                article.candidate_disposition, article.special_candidate_type,
                article.source_relationship, article.original_publisher, article.original_url,
                article.wire_service, article.source_action, article.duplicate_type,
                article.content_cluster_id, article.classification_confidence,
                article.classification_version, article.classification_reason,
            ]
            if article.article_id in id_rows:
                existing_row = id_rows[article.article_id]
                current = ws.row_values(existing_row)
                if len(current) >= 33:
                    row[27] = current[27] or row[27]
                    row[30] = current[30] if len(current) > 30 else ""
                    row[31] = current[31] if len(current) > 31 else ""
                    row[32] = current[32] if len(current) > 32 else ""
                updates.append((existing_row, row))
            else:
                new_rows.append(row)
            written += 1
        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED", table_range="A:AV")
        for row_no, row in updates:
            ws.update(
                range_name=f"A{row_no}:AV{row_no}",
                values=[row],
                value_input_option="USER_ENTERED",
            )
        return written

    def append_extraction_logs(self, articles: Iterable[ExtractedArticle]) -> None:
        ws = self.book.worksheet("extraction_log")
        now_dt = self._now()
        now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        rows: list[list[object]] = []
        for article in articles:
            for index, attempt in enumerate(article.extraction_attempts, start=1):
                extraction_id = f"{article.article_id}-{index}-{int(now_dt.timestamp())}"
                rows.append([
                    extraction_id, article.article_id, article.url, now,
                    attempt.get("extractor", ""), index, attempt.get("http_status", ""),
                    str(bool(attempt.get("success"))).upper(), attempt.get("body_chars", 0),
                    str(bool(article.title)).upper(), str(bool(article.author)).upper(),
                    str(bool(article.published_at)).upper(), attempt.get("error_type", ""),
                    attempt.get("error_message", ""), attempt.get("latency_ms", ""),
                    attempt.get("credits_used", ""), compact_json(attempt),
                ])
        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A:Q")

    def append_collector_run(self, values: dict[str, object]) -> None:
        ws = self.book.worksheet("collector_runs")
        ws.append_row([values.get(key, "") for key in RUN_HEADERS], value_input_option="USER_ENTERED")

    @staticmethod
    def _metric_value(ws: gspread.Worksheet, metric: str) -> str:
        for row in ws.get_all_values()[1:]:
            if row and str(row[0]).strip() == metric:
                return str(row[1] if len(row) > 1 else "").strip()
        return ""

    def maybe_auto_promote(self) -> dict[str, Any]:
        """Read the named promotion gate; auto-promotion remains opt-in."""
        config_ws = self.book.worksheet("collector_config")
        rows = config_ws.get_all_records()
        config_rows = {
            str(row.get("config_key", "")).strip(): (idx + 2, row)
            for idx, row in enumerate(rows)
        }
        auto_row = config_rows.get("auto_promote_when_ready")
        auto_enabled = bool(auto_row) and str(
            auto_row[1].get("value", "")
        ).strip().upper() in {"TRUE", "1", "YES", "Y"}
        mode_row = config_rows.get("mode")
        current_mode = str(mode_row[1].get("value", "")).strip() if mode_row else ""
        health_ws = self.book.worksheet("collector_health")
        promotion_gate = self._metric_value(health_ws, "promotion_gate").upper()
        result = {
            "auto_promote_enabled": auto_enabled,
            "previous_mode": current_mode,
            "promotion_gate": promotion_gate,
            "promoted": False,
        }
        if (
            not auto_enabled
            or current_mode != "shadow"
            or promotion_gate != "READY"
            or not mode_row
        ):
            return result
        row_no = mode_row[0]
        now = self._now().strftime("%Y-%m-%d %H:%M:%S")
        config_ws.update(
            range_name=f"B{row_no}:F{row_no}",
            values=[[
                "cache_primary",
                mode_row[1].get("value_type", "string"),
                mode_row[1].get("status", "active"),
                "双健康门和影子验证通过后自动切换；默认仍应保持关闭",
                now,
            ]],
            value_input_option="USER_ENTERED",
        )
        result["promoted"] = True
        result["current_mode"] = "cache_primary"
        return result
