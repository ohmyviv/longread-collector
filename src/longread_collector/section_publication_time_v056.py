"""P1-A.4: conservative publication-time observability for section routes.

Section scans historically returned URL/title metadata without publication-time
observations. This module observes only explicit relative calendar-day clocks
(`今天 HH:MM` / `昨天 HH:MM`) on explicitly supported first-party list pages.

The observation is telemetry-only. It deliberately does NOT populate
``DiscoveredURL.published_at`` because that field participates in Control
freshness filtering/ranking. Coverage telemetry consumes the dedicated metadata
field instead, preserving selection semantics while allowing measured route
horizons.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from . import effective_route_v056 as _effective
from .normalization import canonicalize_url

SECTION_PUBLICATION_TIME_VERSION = "section-publication-time-observability-v0.2"
SECTION_PUBLICATION_CLOCK_KEY = "section_publication_clock_iso"
SECTION_PUBLICATION_CLOCK_SOURCE = "section_relative_day_clock"
_SUPPORTED_SOURCE_IDS = {"yicai", "jiemian-depth"}
_RELATIVE_DAY_CLOCK_RE = re.compile(
    r"(?P<day>今天|昨天)\s*(?P<hour>(?:[01]?\d|2[0-3])):(?P<minute>[0-5]\d)"
)


class _SectionEventParser(HTMLParser):
    """Preserve document order for anchors and surrounding visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, str, str]] = []
        self._href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        values = {str(key).lower(): value or "" for key, value in attrs}
        self._href = values.get("href", "")
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        text = _effective._clean_text(data)
        if not text:
            return
        if self._href is not None:
            self._anchor_text.append(text)
        else:
            self.events.append(("text", "", text))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = _effective._clean_text(" ".join(self._anchor_text))
        self.events.append(("anchor", self._href, title))
        self._href = None
        self._anchor_text = []


def _is_article_anchor(url: str, source: dict[str, Any]) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return False
    if _effective._base_domain(url) != _effective._base_domain(
        str(source.get("homepage_url", ""))
    ):
        return False
    path = parts.path or "/"
    return not _effective.NON_ARTICLE_PATH_RE.search(path) and _effective._is_article_path(
        path
    )


def _article_contexts(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    target_urls: set[str],
) -> dict[str, str]:
    parser = _SectionEventParser()
    parser.feed(body)
    chunks: dict[str, list[str]] = defaultdict(list)
    current: str | None = None

    for kind, href, text in parser.events:
        if kind == "anchor":
            url = urljoin(endpoint, href)
            if _is_article_anchor(url, source):
                canonical = canonicalize_url(url)
                current = canonical if canonical in target_urls else None
                continue
            if current and text:
                chunks[current].append(text)
            continue
        if current and text:
            chunks[current].append(text)

    return {key: " ".join(values) for key, values in chunks.items()}


def _relative_day_clock(
    text: str,
    *,
    observed_at: datetime,
) -> tuple[datetime, str] | None:
    """Resolve only explicit 今天/昨天 clock evidence against observation day."""

    matches = list(_RELATIVE_DAY_CLOCK_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    day = observed_at.date()
    if match.group("day") == "昨天":
        day -= timedelta(days=1)
    parsed = datetime(
        day.year,
        day.month,
        day.day,
        int(match.group("hour")),
        int(match.group("minute")),
        tzinfo=observed_at.tzinfo,
    )
    if parsed > observed_at:
        return None
    return parsed, match.group(0)


def enrich_section_publication_times(
    body: str,
    *,
    source: dict[str, Any],
    endpoint: str,
    items: list[Any],
    observed_at: datetime | None = None,
) -> list[Any]:
    """Attach explicit list-page clock evidence as telemetry-only metadata."""

    source_id = str(source.get("source_id", "") or "").strip()
    if source_id not in _SUPPORTED_SOURCE_IDS or not items:
        return items

    clock = observed_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    target_urls = {canonicalize_url(str(item.url)) for item in items}
    contexts = _article_contexts(
        body,
        source=source,
        endpoint=endpoint,
        target_urls=target_urls,
    )

    for item in items:
        canonical = canonicalize_url(str(item.url))
        evidence = _relative_day_clock(contexts.get(canonical, ""), observed_at=clock)
        if evidence is None:
            continue
        observed_publication_time, raw = evidence
        # Deliberately do not mutate item.published_at. That field is selection-
        # semantic input to the freshness policy. Keep this observation isolated
        # for source-run coverage measurement only.
        item.metadata.update(
            {
                SECTION_PUBLICATION_CLOCK_KEY: observed_publication_time.isoformat(),
                "section_publication_clock_source": SECTION_PUBLICATION_CLOCK_SOURCE,
                "section_publication_clock_confidence": "high",
                "section_publication_clock_raw": raw,
                "section_publication_time_version": SECTION_PUBLICATION_TIME_VERSION,
            }
        )
    return items


def install_section_publication_time_observability() -> None:
    """Patch the section parser with metadata-only publication-time observation."""

    current = _effective.parse_section_html_v056
    if getattr(current, "_section_publication_time_version", "") == SECTION_PUBLICATION_TIME_VERSION:
        return

    original: Callable[..., list[Any]] = current

    def parse_section_html_with_time(
        body: str,
        *,
        source: dict[str, Any],
        endpoint: str,
        limit: int,
    ) -> list[Any]:
        items = original(body, source=source, endpoint=endpoint, limit=limit)
        return enrich_section_publication_times(
            body,
            source=source,
            endpoint=endpoint,
            items=items,
        )

    setattr(
        parse_section_html_with_time,
        "_section_publication_time_version",
        SECTION_PUBLICATION_TIME_VERSION,
    )
    _effective.parse_section_html_v056 = parse_section_html_with_time


__all__ = [
    "SECTION_PUBLICATION_CLOCK_KEY",
    "SECTION_PUBLICATION_CLOCK_SOURCE",
    "SECTION_PUBLICATION_TIME_VERSION",
    "enrich_section_publication_times",
    "install_section_publication_time_observability",
]
