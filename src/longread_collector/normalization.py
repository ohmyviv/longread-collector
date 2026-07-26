from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "spm", "from", "source",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_KEYS and not k.lower().startswith("utm_")]
    query.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def stable_id(url_canonical: str, length: int = 20) -> str:
    return hashlib.sha256(url_canonical.encode("utf-8")).hexdigest()[:length]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def domain_from_url(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def source_from_domain(domain: str) -> str:
    stem = domain.split(":", 1)[0]
    parts = stem.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return stem
