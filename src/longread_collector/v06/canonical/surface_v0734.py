"""PR-7.3.4 narrow page-surface recovery for newspaper issue containers.

The PR-2 medium resolver intentionally prefers substantive prose, but a digital
newspaper issue/index can contain many complete articles and therefore look like
an unusually long standalone article. This module adds a fail-closed override
only when issue identity and multi-article structure are both explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from ..contracts import (
    AcquisitionBundle,
    CanonicalArticle,
    ContentMedium,
    DiscoveryRecord,
    Evidence,
    PageSurface,
)
from .evidence import make_evidence, normalize_space

SURFACE_VERSION = "canonical-surface-v0.6-pr7.3.4"

_ISSUE_TITLE_RE = re.compile(
    r"(?:微报纸|微報紙|电子报|電子報|数字报|數字報|数字报纸|數字報紙|"
    r"e[-\s]?paper|epaper)",
    re.IGNORECASE,
)
_ISSUE_PATH_RE = re.compile(
    r"/(?:PageArticleIndex[^/]*|IssueIndex)[.]html?$",
    re.IGNORECASE,
)
_EDITION_HEADING_RE = re.compile(
    r"(?m)^\s*#{2,6}\s+\d{1,2}版\s*[：:]",
)
_ARTICLE_LINK_RE = re.compile(
    r"https?://[^)\s]+/(?:Articel|Article)\d+[A-Za-z0-9_-]*[.]html?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SurfaceRecovery:
    page_surface: PageSurface
    main_content_medium: ContentMedium
    confidence: float
    evidence: tuple[Evidence, ...]


def recover_newspaper_issue_listing(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    article: CanonicalArticle,
) -> SurfaceRecovery | None:
    """Recover explicit multi-article newspaper issue/index pages as LISTING.

    The override is intentionally conjunctive. A long article mentioning an
    electronic newspaper, a category page with many headings, or an index-like
    URL without acquired multi-article structure is not enough by itself.
    """

    if article.page_surface is not PageSurface.ARTICLE_PAGE:
        return None
    if article.main_content_medium is not ContentMedium.WRITTEN_ARTICLE:
        return None

    body = bundle.body_markdown or bundle.body_text or ""
    if not body:
        return None

    title = normalize_space(article.resolved_title or bundle.raw_title or record.title_hint)
    path = urlsplit(record.url).path
    title_signal = bool(_ISSUE_TITLE_RE.search(title))
    path_signal = bool(_ISSUE_PATH_RE.search(path))
    if not (title_signal or path_signal):
        return None

    # Newspaper issue navigation and its article links are expected near the
    # beginning of the acquired body. Keeping a bounded window avoids turning a
    # distant recommendation/reference section into page-surface evidence.
    sample = body[:30000]
    edition_heading_count = len(_EDITION_HEADING_RE.findall(sample))
    current_host = _normalized_host(record.url)
    article_links = frozenset(
        link
        for link in _ARTICLE_LINK_RE.findall(sample)
        if current_host and _normalized_host(link) == current_host
    )
    article_link_count = len(article_links)

    if edition_heading_count < 3 or article_link_count < 5:
        return None

    confidence = 0.99
    identity_signals = ",".join(
        signal
        for signal, present in (
            ("issue_title", title_signal),
            ("issue_index_path", path_signal),
        )
        if present
    )
    excerpt = (
        f"identity={identity_signals}; edition_headings={edition_heading_count}; "
        f"same_host_article_links={article_link_count}"
    )
    evidence = (
        make_evidence(
            record.item_id,
            "newspaper_issue_listing_surface",
            "page_surface",
            PageSurface.LISTING.value,
            confidence=confidence,
            excerpt=excerpt,
            extractor=SURFACE_VERSION,
        ),
        make_evidence(
            record.item_id,
            "newspaper_issue_listing_medium",
            "main_content_medium",
            ContentMedium.UNKNOWN.value,
            confidence=confidence,
            excerpt=excerpt,
            extractor=SURFACE_VERSION,
        ),
    )
    return SurfaceRecovery(
        page_surface=PageSurface.LISTING,
        main_content_medium=ContentMedium.UNKNOWN,
        confidence=confidence,
        evidence=evidence,
    )


def _normalized_host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


__all__ = [
    "SURFACE_VERSION",
    "SurfaceRecovery",
    "recover_newspaper_issue_listing",
]
