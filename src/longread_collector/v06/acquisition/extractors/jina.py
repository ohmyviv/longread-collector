"""Jina Reader adapter for the explicit v0.6 acquisition chain."""

from __future__ import annotations

from typing import Any

from ...contracts import DiscoveryRecord
from ..types import ExtractorPayload


JINA_EXTRACTOR_VERSION = "jina-extractor-v0.6-pr5"


class JinaExtractor:
    name = "jina"
    paid = False

    def __init__(self, client: Any) -> None:
        self.client = client

    async def extract(self, record: DiscoveryRecord) -> ExtractorPayload:
        data, meta = await self.client.read(record.url)
        content = str(data.get("markdown") or "").strip()
        return ExtractorPayload(
            extractor=self.name,
            markdown=content,
            title=str(data.get("title") or record.title_hint or "").strip(),
            author=str(data.get("author") or "").strip(),
            published_at=str(
                data.get("published_at")
                or (record.published_at_hints[0] if record.published_at_hints else "")
            ).strip(),
            metadata={
                **{
                    str(key): value
                    for key, value in data.items()
                    if key not in {"raw", "markdown"}
                },
                "extractor_version": JINA_EXTRACTOR_VERSION,
            },
            latency_ms=int(meta.get("latency_ms") or 0),
            credits_used=float(meta.get("credits_used") or 0.0),
            http_status=int(meta["http_status"]) if meta.get("http_status") else None,
        )


__all__ = ["JINA_EXTRACTOR_VERSION", "JinaExtractor"]
