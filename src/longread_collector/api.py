from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, HttpUrl

from .clients import FirecrawlClient, JinaReaderClient
from .config import Settings, get_settings
from .extraction import extract_article
from .models import DiscoveredURL
from .pipeline import CollectorPipeline

app = FastAPI(title="Longread Collector", version="0.2.0")


class ExtractRequest(BaseModel):
    url: HttpUrl
    language: str = ""


class CollectRequest(BaseModel):
    group: str | None = None
    query_file: str | None = None


def authorize(
    x_collector_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Settings:
    if settings.collector_token and x_collector_token != settings.collector_token:
        raise HTTPException(status_code=401, detail="invalid collector token")
    return settings


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/collect")
async def collect(request: CollectRequest, settings: Settings = Depends(authorize)):
    pipeline = CollectorPipeline(settings)
    query_file = Path(request.query_file) if request.query_file else None
    return await pipeline.collect(group_id=request.group, query_file=query_file)


@app.post("/extract")
async def extract(request: ExtractRequest, settings: Settings = Depends(authorize)):
    firecrawl = FirecrawlClient(settings.firecrawl_base_url, settings.firecrawl_api_key)
    jina = JinaReaderClient(settings.jina_reader_base_url, settings.jina_api_key)
    item = DiscoveredURL(url=str(request.url), language=request.language, discovery_method="api_extract")
    article = await extract_article(item, jina, firecrawl, settings)
    return {
        "article_id": article.article_id,
        "url_canonical": article.url_canonical,
        "title": article.title,
        "author": article.author,
        "published_at": article.published_at,
        "extractor_used": article.extractor_used,
        "verification_level": article.verification_level,
        "content_chars": article.content_chars,
        "eligible_for_editor": article.eligible_for_editor,
        "reject_reason": article.reject_reason,
        "content_markdown": article.content_markdown,
        "attempts": article.extraction_attempts,
    }
