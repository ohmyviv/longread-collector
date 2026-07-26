from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    firecrawl_api_key: str = Field(alias="FIRECRAWL_API_KEY")
    jina_api_key: str | None = Field(default=None, alias="JINA_API_KEY")
    google_sheet_id: str = Field(alias="GOOGLE_SHEET_ID")
    google_service_account_file: Path = Field(alias="GOOGLE_SERVICE_ACCOUNT_FILE")

    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")
    max_concurrency: int = Field(default=2, alias="MAX_CONCURRENCY")
    max_urls_per_run: int = Field(default=32, alias="MAX_URLS_PER_RUN")
    min_body_chars: int = Field(default=1200, alias="MIN_BODY_CHARS")
    editor_min_body_chars: int = Field(default=2500, alias="EDITOR_MIN_BODY_CHARS")
    content_cell_limit: int = Field(default=45000, alias="CONTENT_CELL_LIMIT")
    cache_hours: int = Field(default=168, alias="CACHE_HOURS")
    firecrawl_tbs: str | None = Field(default=None, alias="FIRECRAWL_TBS")
    firecrawl_fallback_daily_limit: int = Field(default=3, alias="FIRECRAWL_FALLBACK_DAILY_LIMIT")
    collector_token: str | None = Field(default=None, alias="COLLECTOR_TOKEN")

    firecrawl_base_url: str = "https://api.firecrawl.dev"
    jina_reader_base_url: str = "https://r.jina.ai"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
