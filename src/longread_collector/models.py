from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DiscoveredURL:
    url: str
    title: str = ""
    description: str = ""
    published_at: str = ""
    discovery_method: str = "firecrawl_search"
    query_or_source: str = ""
    language: str = ""
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedArticle:
    article_id: str
    url: str
    url_canonical: str
    domain: str
    title: str = ""
    author: str = ""
    published_at: str = ""
    language: str = ""
    canonical_source: str = ""
    hosting_source: str = ""
    description: str = ""
    extractor_used: str = ""
    extraction_status: str = "failed"
    verification_level: str = "D"
    content_markdown: str = ""
    content_chars: int = 0
    content_sha256: str = ""
    content_truncated: bool = False
    eligible_for_editor: bool = False
    reject_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_attempts: list[dict[str, Any]] = field(default_factory=list)
