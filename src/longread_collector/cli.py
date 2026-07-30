from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from .clients import FirecrawlClient, JinaReaderClient
from .config import get_settings
from .evaluation import evaluate_ground_truth
from .extraction import extract_article
from .models import DiscoveredURL
from .pipeline import CollectorPipeline
from .sheets import GoogleSheetStore

app = typer.Typer(no_args_is_help=True)


@app.command()
def collect(
    group: Optional[str] = typer.Option(None, help="collector_queries group_id"),
    query_file: Optional[Path] = typer.Option(None, exists=True, readable=True),
) -> None:
    """Run one scheduled query group and sync results to Google Sheet."""
    pipeline = CollectorPipeline(get_settings())
    result = asyncio.run(pipeline.collect(group_id=group, query_file=query_file))
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("evaluate-ground-truth")
def evaluate_ground_truth_command() -> None:
    """Evaluate v0.4 against the fixed 48-item release fixture."""
    store = GoogleSheetStore(get_settings())
    result = evaluate_ground_truth(store)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def doctor(
    test_remote: bool = typer.Option(
        False,
        help="Also make one Jina and one Firecrawl request",
    )
) -> None:
    """Validate credentials, Sheet schema, query groups, and optional APIs."""
    settings = get_settings()
    store = GoogleSheetStore(settings)
    report: dict[str, object] = {
        "sheet": store.health_check(),
        "groups": {},
        "directed_sources": {},
        "jina": "not_tested",
        "firecrawl": "not_tested",
    }
    for group in ("intl_early", "pre_report", "zh_midday", "zh_evening"):
        report["groups"][group] = len(store.load_queries(group))
    for language in ("en", "zh"):
        report["directed_sources"][language] = len(
            store.load_source_registry(language)
        )
    if test_remote:
        jina = JinaReaderClient(
            settings.jina_reader_base_url,
            settings.jina_api_key,
        )
        firecrawl = FirecrawlClient(
            settings.firecrawl_base_url,
            settings.firecrawl_api_key,
        )
        try:
            data, _ = asyncio.run(jina.read("https://example.com"))
            report["jina"] = {
                "ok": bool(data.get("markdown")),
                "chars": len(str(data.get("markdown", ""))),
            }
        except Exception as exc:
            report["jina"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        try:
            results, meta = asyncio.run(
                firecrawl.search("long-form journalism", limit=1, tbs="qdr:d")
            )
            report["firecrawl"] = {
                "ok": True,
                "results": len(results),
                "credits_used": meta.get("credits_used"),
            }
        except Exception as exc:
            report["firecrawl"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    if (
        not report["sheet"]["ok"]
        or any(value == 0 for value in report["groups"].values())
        or any(value == 0 for value in report["directed_sources"].values())
    ):
        raise typer.Exit(code=1)


@app.command()
def extract(url: str, language: str = "") -> None:
    """Test a single URL without writing it to the Sheet."""
    settings = get_settings()
    firecrawl = FirecrawlClient(
        settings.firecrawl_base_url,
        settings.firecrawl_api_key,
    )
    jina = JinaReaderClient(
        settings.jina_reader_base_url,
        settings.jina_api_key,
    )
    article = asyncio.run(
        extract_article(
            DiscoveredURL(url=url, language=language),
            jina,
            firecrawl,
            settings,
        )
    )
    typer.echo(
        json.dumps(
            {
                "article_id": article.article_id,
                "url_canonical": article.url_canonical,
                "title": article.title,
                "author": article.author,
                "published_at": article.published_at,
                "extractor_used": article.extractor_used,
                "verification_level": article.verification_level,
                "content_chars": article.content_chars,
                "page_role": article.page_role,
                "page_type": article.page_type,
                "content_type": article.content_type,
                "candidate_disposition": article.candidate_disposition,
                "source_relationship": article.source_relationship,
                "original_publisher": article.original_publisher,
                "source_action": article.source_action,
                "duplicate_type": article.duplicate_type,
                "content_cluster_id": article.content_cluster_id,
                "classification_confidence": article.classification_confidence,
                "classification_version": article.classification_version,
                "classification_reason": article.classification_reason,
                "eligible_for_editor": article.eligible_for_editor,
                "reject_reason": article.reject_reason,
                "attempts": article.extraction_attempts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    uvicorn.run("longread_collector.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
