"""Direct HTML adapter for the explicit v0.6 acquisition chain."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ...contracts import DiscoveryRecord
from ..types import ExtractorPayload


DIRECT_HTML_EXTRACTOR_VERSION = "direct-html-extractor-v0.6-pr5"
DirectReader = Callable[[str], Awaitable[tuple[dict[str, Any], dict[str, Any]]]]


class DirectHtmlExtractor:
    name = "direct_html"
    paid = False

    def __init__(self, reader: DirectReader | None = None) -> None:
        self._reader = reader

    async def extract(self, record: DiscoveryRecord) -> ExtractorPayload:
        reader = self._reader
        if reader is None:
            # Lazy import: importing longread_collector.v06 remains isolated from
            # legacy pipeline/classification modules. The parser itself is reused
            # during migration rather than duplicated.
            from ....direct_html_v056m import read_direct_html_v056m

            reader = read_direct_html_v056m
        data, meta = await reader(record.url)
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        canonical_links = _tuple_strings(
            metadata.get("canonical_links") or data.get("canonical_links")
        )
        outbound_links = _tuple_strings(
            metadata.get("outbound_links") or data.get("outbound_links")
        )
        return ExtractorPayload(
            extractor=self.name,
            markdown=str(data.get("markdown") or "").strip(),
            title=str(data.get("title") or record.title_hint or "").strip(),
            author=str(data.get("author") or "").strip(),
            published_at=str(
                data.get("published_at")
                or (record.published_at_hints[0] if record.published_at_hints else "")
            ).strip(),
            canonical_links=canonical_links,
            outbound_links=outbound_links,
            metadata={**metadata, "extractor_version": DIRECT_HTML_EXTRACTOR_VERSION},
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


__all__ = ["DIRECT_HTML_EXTRACTOR_VERSION", "DirectHtmlExtractor"]
