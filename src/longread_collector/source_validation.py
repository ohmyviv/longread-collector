from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from .config import get_settings
from .sheets import GoogleSheetStore, SOURCE_HEADERS

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; LongreadCollectorSourceValidator/1.0; "
    "+https://github.com/ohmyviv/longread-collector)"
)
ARTICLE_HINT = re.compile(
    r"/(?:20\d{2}|article|articles|news|story|stories|detail|content|feature|features|magazine|investigates)/",
    re.IGNORECASE,
)
VALIDATION_HEADERS = [
    "validated_at_bj",
    "source_id",
    "source_name",
    "language",
    "enabled",
    "priority_tier",
    "planned_method",
    "validation_status",
    "selected_endpoint",
    "selected_kind",
    "selected_entry_count",
    "http_status",
    "notes",
]


@dataclass(slots=True)
class EndpointAttempt:
    url: str
    final_url: str = ""
    http_status: int | None = None
    content_type: str = ""
    detected_kind: str = "unknown"
    entry_count: int = 0
    body_bytes: int = 0
    error: str = ""


@dataclass(slots=True)
class SourceValidationResult:
    source_id: str
    source_name: str
    language: str
    enabled: bool
    priority_tier: str
    planned_method: str
    validation_status: str
    selected_endpoint: str
    selected_kind: str
    selected_entry_count: int
    http_status: int | None
    notes: str
    attempts: list[EndpointAttempt]


def _split(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def load_all_sources(store: GoogleSheetStore) -> list[dict[str, Any]]:
    worksheet = store.book.worksheet("source_registry")
    rows = worksheet.get_all_records(expected_headers=SOURCE_HEADERS)
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["enabled"] = str(item.get("enabled", "")).strip().upper() in {
            "TRUE",
            "1",
            "YES",
            "Y",
        }
        item["discovery_method"] = _split(item.get("discovery_method"))
        result.append(item)
    return result


def validate_source_rows(sources: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    allowed_methods = {
        "rss",
        "atom",
        "news_sitemap",
        "sitemap",
        "section_scan",
        "homepage",
        "firecrawl_search",
        "source_scan",
    }
    for index, source in enumerate(sources, start=2):
        source_id = str(source.get("source_id", "")).strip()
        if not source_id:
            errors.append(f"row {index}: missing source_id")
        elif source_id in seen:
            errors.append(f"row {index}: duplicate source_id={source_id}")
        seen.add(source_id)
        if str(source.get("language", "")).strip() not in {"zh", "en"}:
            errors.append(f"{source_id}: language must be zh or en")
        homepage = str(source.get("homepage_url", "")).strip()
        if not homepage.startswith(("http://", "https://")):
            errors.append(f"{source_id}: homepage_url must be HTTP(S)")
        methods = source.get("discovery_method") or []
        if not methods:
            errors.append(f"{source_id}: discovery_method is empty")
        unknown = sorted(set(str(value) for value in methods) - allowed_methods)
        if unknown:
            errors.append(f"{source_id}: unknown discovery methods {unknown}")
        if source.get("enabled") and str(source.get("priority_tier", "")) == "monitor":
            errors.append(f"{source_id}: monitor sources must remain disabled")
    return errors


def detect_document_kind(body: str, content_type: str = "") -> tuple[str, int]:
    sample = body[:750_000]
    lowered = sample.lower()
    if "<rss" in lowered or "<feed" in lowered:
        try:
            root = ET.fromstring(sample)
            items = root.findall(".//item")
            items.extend(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
            return "feed", len(items)
        except ET.ParseError:
            return "feed_like", len(re.findall(r"<(?:item|entry)\b", lowered))
    if "<urlset" in lowered or "<sitemapindex" in lowered:
        try:
            root = ET.fromstring(sample)
            return "sitemap", len(root.findall(".//{*}loc"))
        except ET.ParseError:
            return "sitemap_like", len(re.findall(r"<loc>", lowered))
    if "text/html" in content_type.lower() or "<html" in lowered:
        hrefs = re.findall(r"href=[\"']([^\"']+)", sample, re.IGNORECASE)
        article_links = {href for href in hrefs if ARTICLE_HINT.search(href)}
        return "html", len(article_links)
    return "other", len(sample)


def planned_method(source: dict[str, Any]) -> str:
    methods = [str(value) for value in source.get("discovery_method") or []]
    for method in ("rss", "atom", "news_sitemap", "sitemap", "section_scan", "homepage"):
        if method in methods:
            return method
    return "firecrawl_search"


def candidate_endpoints(source: dict[str, Any]) -> list[str]:
    endpoints: list[str] = []
    for key in ("rss_url", "news_sitemap_url", "sitemap_url"):
        value = str(source.get(key, "")).strip()
        if value:
            endpoints.append(value)
    parser_config = str(source.get("parser_config_json", "")).strip()
    if parser_config:
        try:
            parsed = json.loads(parser_config)
            endpoints.extend(
                str(value).strip()
                for value in parsed.get("section_urls", [])
                if str(value).strip()
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    homepage = str(source.get("homepage_url", "")).strip()
    if homepage:
        endpoints.append(homepage)
    result: list[str] = []
    seen: set[str] = set()
    for endpoint in endpoints:
        if endpoint not in seen:
            result.append(endpoint)
            seen.add(endpoint)
    return result


def attempt_matches_method(attempt: EndpointAttempt, method: str) -> bool:
    if attempt.http_status is None or attempt.http_status >= 400:
        return False
    if method in {"rss", "atom"}:
        return attempt.detected_kind == "feed" and attempt.entry_count > 0
    if method in {"news_sitemap", "sitemap"}:
        return attempt.detected_kind == "sitemap" and attempt.entry_count > 0
    if method in {"section_scan", "homepage"}:
        return attempt.detected_kind == "html" and attempt.entry_count > 0
    return False


async def validate_source(
    client: httpx.AsyncClient,
    source: dict[str, Any],
    *,
    timeout_seconds: float,
) -> SourceValidationResult:
    method = planned_method(source)
    attempts: list[EndpointAttempt] = []
    endpoints = candidate_endpoints(source)
    if method == "firecrawl_search":
        return SourceValidationResult(
            source_id=str(source.get("source_id", "")),
            source_name=str(source.get("source_name", "")),
            language=str(source.get("language", "")),
            enabled=bool(source.get("enabled")),
            priority_tier=str(source.get("priority_tier", "")),
            planned_method=method,
            validation_status="search_only",
            selected_endpoint=endpoints[0] if endpoints else "",
            selected_kind="search",
            selected_entry_count=0,
            http_status=None,
            notes="domain-restricted Firecrawl Search remains the discovery path",
            attempts=[],
        )
    selected: EndpointAttempt | None = None
    for endpoint in endpoints:
        attempt = EndpointAttempt(url=endpoint)
        try:
            response = await client.get(endpoint, follow_redirects=True, timeout=timeout_seconds)
            attempt.final_url = str(response.url)
            attempt.http_status = response.status_code
            attempt.content_type = response.headers.get("content-type", "")
            attempt.body_bytes = len(response.content)
            attempt.detected_kind, attempt.entry_count = detect_document_kind(
                response.text,
                attempt.content_type,
            )
        except Exception as exc:
            attempt.error = f"{type(exc).__name__}: {exc}"[:300]
        attempts.append(attempt)
        if attempt_matches_method(attempt, method):
            selected = attempt
            break
    if selected is not None:
        status = "validated"
        notes = "preferred entrypoint validated"
    else:
        reachable = next(
            (
                attempt
                for attempt in attempts
                if attempt.http_status is not None and attempt.http_status < 400
            ),
            None,
        )
        if reachable is not None:
            selected = reachable
            status = "reachable_fallback_needed"
            notes = "site reachable; preferred parser did not validate, use next fallback"
        else:
            status = "blocked_or_unreachable"
            notes = "runner could not reach a configured endpoint; retain search fallback or observation status"
    return SourceValidationResult(
        source_id=str(source.get("source_id", "")),
        source_name=str(source.get("source_name", "")),
        language=str(source.get("language", "")),
        enabled=bool(source.get("enabled")),
        priority_tier=str(source.get("priority_tier", "")),
        planned_method=method,
        validation_status=status,
        selected_endpoint=selected.url if selected else (endpoints[0] if endpoints else ""),
        selected_kind=selected.detected_kind if selected else "unknown",
        selected_entry_count=selected.entry_count if selected else 0,
        http_status=selected.http_status if selected else None,
        notes=notes,
        attempts=attempts,
    )


async def validate_sources(
    sources: list[dict[str, Any]],
    *,
    timeout_seconds: float = 12.0,
    concurrency: int = 12,
) -> list[SourceValidationResult]:
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    limits = httpx.Limits(
        max_connections=max(concurrency, 1),
        max_keepalive_connections=max(min(concurrency, 8), 1),
    )
    semaphore = asyncio.Semaphore(max(concurrency, 1))
    async with httpx.AsyncClient(headers=headers, limits=limits) as client:
        async def one(source: dict[str, Any]) -> SourceValidationResult:
            async with semaphore:
                return await validate_source(
                    client,
                    source,
                    timeout_seconds=timeout_seconds,
                )

        return await asyncio.gather(*(one(source) for source in sources))


def summarize(results: list[SourceValidationResult]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(results),
        "enabled": sum(result.enabled for result in results),
        "languages": {},
        "statuses": {},
        "methods": {},
    }
    for result in results:
        summary["languages"][result.language] = summary["languages"].get(result.language, 0) + 1
        summary["statuses"][result.validation_status] = summary["statuses"].get(result.validation_status, 0) + 1
        summary["methods"][result.planned_method] = summary["methods"].get(result.planned_method, 0) + 1
    enabled_results = [result for result in results if result.enabled]
    acceptable = sum(
        result.validation_status in {"validated", "reachable_fallback_needed", "search_only"}
        for result in enabled_results
    )
    summary["enabled_acceptable_rate"] = acceptable / len(enabled_results) if enabled_results else 0.0
    return summary


def write_local_outputs(
    results: list[SourceValidationResult],
    output_json: Path,
    output_csv: Path,
) -> dict[str, Any]:
    summary = summarize(results)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(
            {"summary": summary, "results": [asdict(result) for result in results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_HEADERS[1:])
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row.pop("attempts")
            writer.writerow(row)
    return summary


def write_sheet_results(store: GoogleSheetStore, results: list[SourceValidationResult]) -> None:
    try:
        worksheet = store.book.worksheet("source_validation")
    except Exception:
        worksheet = store.book.add_worksheet(
            title="source_validation",
            rows=max(500, len(results) + 20),
            cols=len(VALIDATION_HEADERS),
        )
    now = store._now().strftime("%Y-%m-%d %H:%M:%S")
    rows: list[list[object]] = [VALIDATION_HEADERS]
    for result in results:
        rows.append(
            [
                now,
                result.source_id,
                result.source_name,
                result.language,
                str(result.enabled).upper(),
                result.priority_tier,
                result.planned_method,
                result.validation_status,
                result.selected_endpoint,
                result.selected_kind,
                result.selected_entry_count,
                result.http_status or "",
                result.notes,
            ]
        )
    worksheet.clear()
    worksheet.update(range_name=f"A1:M{len(rows)}", values=rows, value_input_option="USER_ENTERED")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate source_registry entrypoints")
    parser.add_argument("--output-json", type=Path, default=Path("artifacts/source-validation.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("artifacts/source-validation.csv"))
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--minimum-enabled-acceptable-rate", type=float, default=0.65)
    parser.add_argument("--skip-sheet-write", action="store_true")
    args = parser.parse_args()
    store = GoogleSheetStore(get_settings())
    sources = load_all_sources(store)
    structure_errors = validate_source_rows(sources)
    if structure_errors:
        raise SystemExit("\n".join(structure_errors))
    results = asyncio.run(
        validate_sources(sources, timeout_seconds=args.timeout, concurrency=args.concurrency)
    )
    summary = write_local_outputs(results, args.output_json, args.output_csv)
    if not args.skip_sheet_write:
        write_sheet_results(store, results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["enabled_acceptable_rate"] < args.minimum_enabled_acceptable_rate:
        raise SystemExit(
            "enabled acceptable rate below threshold: "
            f"{summary['enabled_acceptable_rate']:.3f} < "
            f"{args.minimum_enabled_acceptable_rate:.3f}"
        )


if __name__ == "__main__":
    main()
