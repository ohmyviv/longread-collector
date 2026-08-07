"""Extractor adapters for v0.6 Acquisition Service."""

from .direct_html import DIRECT_HTML_EXTRACTOR_VERSION, DirectHtmlExtractor
from .firecrawl import FIRECRAWL_EXTRACTOR_VERSION, FirecrawlExtractor
from .jina import JINA_EXTRACTOR_VERSION, JinaExtractor

__all__ = [
    "DIRECT_HTML_EXTRACTOR_VERSION",
    "DirectHtmlExtractor",
    "FIRECRAWL_EXTRACTOR_VERSION",
    "FirecrawlExtractor",
    "JINA_EXTRACTOR_VERSION",
    "JinaExtractor",
]
