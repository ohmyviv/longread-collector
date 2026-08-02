"""Registry matching helpers for recall-denominator audits."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import tldextract

from .final_recall_audit import _source_key
from .normalization import canonicalize_url, domain_from_url


def _host(value: str) -> str:
    if not value:
        return ""
    try:
        return domain_from_url(canonicalize_url(value))
    except Exception:
        return urlsplit(value).netloc.lower().removeprefix("www.")


def registrable_domain(value: str) -> str:
    host = _host(value)
    if not host:
        return ""
    extracted = tldextract.extract(host)
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}".lower()
    return host.lower()


def match_registry(
    final_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    final_source = _source_key(
        str(final_row.get("final_source") or final_row.get("canonical_source") or "")
    )
    final_url = str(
        final_row.get("final_url_canonical")
        or final_row.get("url_canonical")
        or final_row.get("final_url")
        or final_row.get("url")
        or ""
    )
    final_domain = registrable_domain(final_url)

    for source in source_rows:
        source_name = _source_key(str(source.get("source_name", "")))
        domains = {
            registrable_domain(str(source.get(key, "") or ""))
            for key in (
                "homepage_url",
                "rss_url",
                "sitemap_url",
                "news_sitemap_url",
                "newsletter_url",
            )
            if str(source.get(key, "") or "").strip()
        }
        domains.discard("")
        if (final_source and source_name == final_source) or (
            final_domain and final_domain in domains
        ):
            return source
    return None


__all__ = ["match_registry", "registrable_domain"]
