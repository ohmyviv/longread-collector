"""Firecrawl adapter for the explicit v0.6 acquisition chain."""

from __future__ import annotations

from typing import Any

from ...contracts import DiscoveryRecord
from ..types import ExtractorPayload


FIRECRAWL_EXTRACTOR_VERSION = "firecrawl-extractor-v0.6-pr5"


class FirecrawlExtractor:
    name = "firecrawl"
    paid = True

    def __init__(self, client: Any) -> None:
        self.client = client

    async def extract(self, record: DiscoveryRecord) -> ExtractorPayload:
        data, meta = await self.client.scrape(record.url)
        markdown = data.get("markdown")
        if isinstance(markdown, dict):
            markdown = markdown.get("content") or markdown.get("markdown") or ""
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        canonical_links = _tuple_strings(
            metadata.get("canonicalUrl")
            or metadata.get("canonicalURL")
            or metadata.get("canonical_links")
        )
        outbound_links = _tuple_strings(
            metadata.get("outbound_links") or data.get("outbound_links")
        )
        return ExtractorPayload(
            extractor=self.name,
            markdown=str(markdown or "").strip(),
            title=str(metadata.get("title") or record.title_hint or "").strip(),
            author=str(metadata.get("author") or metadata.get("authors") or "").strip(),
            published_at=str(
                metadata.get("publishedTime")
                or metadata.get("publishedDate")
                or metadata.get("date")
                or (record.published_at_hints[0] if record.published_at_hints else "")
            ).strip(),
            canonical_links=canonical_links,
            outbound_links=outbound_links,
            metadata={**metadata, "extractor_version": FIRECRAWL_EXTRACTOR_VERSION},
            latency_ms=int(meta.get("latency_ms") or 0),
            credits_used=float(meta.get("credits_used") or 0.0),
            http_status=int(meta["http_status"]) if meta.get("http_status") else None,
        )


def _tuple_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = []
    return tuple(str(item).strip() for item in values if str(item or "").strip())


__all__ = ["FIRECRAWL_EXTRACTOR_VERSION", "FirecrawlExtractor"]
