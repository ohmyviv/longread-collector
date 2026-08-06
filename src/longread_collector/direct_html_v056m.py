"""Zero-credit direct HTML recovery used before Firecrawl fallback."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import json
import re
import time
from typing import Any, Iterable

import httpx

DIRECT_HTML_VERSION = "direct-html-recovery-v0.5.6m"
_ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "reportagenewsarticle",
    "analysisnewsarticle",
    "interview",
    "blogposting",
}
_BODY_KEYS = (
    "articleBody",
    "article_body",
    "articleContent",
    "article_content",
    "content",
    "body",
    "text",
    "detail",
)
_TITLE_KEYS = ("headline", "title", "name")
_DATE_KEYS = ("datePublished", "dateCreated", "publishTime", "publishedAt", "published_at")
_AUTHOR_KEYS = ("author", "authors", "creator", "byline")
_SCRIPT_JSON_RE = re.compile(
    r"<script\b[^>]*(?:type=[\"']application/(?:ld\+)?json[\"']|id=[\"']__NEXT_DATA__[\"'])[^>]*>"
    r"(?P<body>.*?)</script>",
    re.I | re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_H1_RE = re.compile(r"(?m)^\s*#\s+\S")
_STOP_HEADING_RE = re.compile(
    r"^(?:我要评论|热点|最新|热议|相关推荐|相关阅读|推荐阅读|更多推荐|直播)$",
    re.I,
)
_META_TITLE_KEYS = {"og:title", "twitter:title", "headline"}
_META_DATE_KEYS = {
    "article:published_time",
    "datepublished",
    "pubdate",
    "publishdate",
    "publish_time",
    "date",
}
_META_AUTHOR_KEYS = {"author", "article:author", "byline"}
_META_DESCRIPTION_KEYS = {"description", "og:description", "twitter:description"}


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|section|article|li|h[1-6]|blockquote)>", "\n\n", text)
    text = _TAG_RE.sub(" ", text)
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n\n".join(line for line in lines if line)


def _with_title_heading(markdown: str, title: str) -> str:
    body = str(markdown or "").strip()
    clean_title = _clean_text(title).strip()
    if clean_title and body and not _H1_RE.search(body):
        return f"# {clean_title}\n\n{body}"
    return body


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _type_tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    return {str(item or "").replace(" ", "").lower() for item in values if item}


def _author_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("headline") or "").strip()
    if isinstance(value, list):
        names = [_author_text(item) for item in value]
        return ", ".join(name for name in names if name)
    return str(value or "").strip()


def _first_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


class _ArticleTextParser(HTMLParser):
    _SKIP = {"script", "style", "nav", "footer", "header", "form", "svg", "noscript", "aside"}
    _CAPTURE = {"h1", "h2", "h3", "p", "blockquote", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.main_depth = 0
        self.capture_tag = ""
        self.buffer: list[str] = []
        self.main_lines: list[str] = []
        self.article_lines: list[str] = []
        self.fallback_lines: list[str] = []
        self.article_started = False
        self.article_finished = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "meta":
            mapping = {str(key or "").lower(): str(value or "") for key, value in attrs}
            key = (
                mapping.get("property")
                or mapping.get("name")
                or mapping.get("itemprop")
                or ""
            ).lower()
            content = mapping.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
            return
        if tag in self._SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"article", "main"}:
            self.main_depth += 1
        if tag in self._CAPTURE:
            self.capture_tag = tag
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.skip_depth or not self.capture_tag:
            return
        text = _WS_RE.sub(" ", data).strip()
        if text:
            self.buffer.append(text)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == self.capture_tag:
            text = " ".join(self.buffer).strip()
            if text:
                prefix = {"h1": "# ", "h2": "## ", "h3": "### ", "blockquote": "> "}.get(tag, "")
                line = prefix + text
                self.fallback_lines.append(line)
                if self.main_depth:
                    self.main_lines.append(line)

                if tag == "h1" and not self.article_started:
                    self.article_started = True
                elif (
                    self.article_started
                    and tag in {"h2", "h3"}
                    and _STOP_HEADING_RE.fullmatch(text)
                ):
                    self.article_finished = True

                if self.article_started and not self.article_finished:
                    self.article_lines.append(line)
            self.capture_tag = ""
            self.buffer = []
        if tag in {"article", "main"} and self.main_depth:
            self.main_depth -= 1

    def _dedupe(self, lines: list[str]) -> str:
        output: list[str] = []
        previous = ""
        for line in lines:
            if line == previous:
                continue
            output.append(line)
            previous = line
        return "\n\n".join(output)

    def markdown(self) -> str:
        main = self._dedupe(self.main_lines)
        article = self._dedupe(self.article_lines)
        fallback = self._dedupe(self.fallback_lines)
        if len(main) >= 600:
            return main
        if len(article) >= 600:
            return article
        return fallback

    def meta_value(self, keys: set[str]) -> str:
        for key in keys:
            value = self.meta.get(key, "").strip()
            if value:
                return value
        return ""


def parse_direct_html_v056m(html_text: str, *, url: str = "") -> dict[str, Any]:
    """Extract article-like JSON-LD/SSR data, then fall back to semantic HTML tags."""

    raw = str(html_text or "")
    best: dict[str, Any] = {}
    best_score = -1
    parse_errors = 0

    for match in _SCRIPT_JSON_RE.finditer(raw):
        payload = unescape(match.group("body")).strip()
        if not payload:
            continue
        try:
            value = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            parse_errors += 1
            continue
        for node in _walk_json(value):
            body_value = _first_value(node, _BODY_KEYS)
            if not isinstance(body_value, str):
                continue
            body = _clean_text(body_value)
            if len(body) < 600:
                continue
            title = str(_first_value(node, _TITLE_KEYS) or "").strip()
            types = _type_tokens(node.get("@type") or node.get("type"))
            article_type = bool(types & _ARTICLE_TYPES)
            structural = int(bool(title)) + int(bool(_first_value(node, _DATE_KEYS))) + int(bool(_first_value(node, _AUTHOR_KEYS)))
            score = len(body) + (5000 if article_type else 0) + structural * 500
            if not article_type and not title and len(body) < 1800:
                continue
            if score <= best_score:
                continue
            best_score = score
            best = {
                "markdown": _with_title_heading(body, title),
                "title": title,
                "published_at": str(_first_value(node, _DATE_KEYS) or "").strip(),
                "author": _author_text(_first_value(node, _AUTHOR_KEYS)),
                "description": str(node.get("description") or "").strip(),
                "metadata": {
                    "direct_html_version": DIRECT_HTML_VERSION,
                    "direct_html_method": "embedded_json",
                    "schema_types": sorted(types),
                    "url": url,
                },
            }

    if best:
        best["metadata"]["json_parse_errors"] = parse_errors
        return best

    parser = _ArticleTextParser()
    try:
        parser.feed(raw)
    except Exception:
        pass
    markdown = parser.markdown()
    title_match = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", raw)
    title = parser.meta_value(_META_TITLE_KEYS)
    if not title and title_match:
        title = _clean_text(title_match.group(1))
    clean_title = _clean_text(title)
    markdown = _with_title_heading(markdown, clean_title)
    return {
        "markdown": markdown,
        "title": clean_title,
        "published_at": parser.meta_value(_META_DATE_KEYS),
        "author": _clean_text(parser.meta_value(_META_AUTHOR_KEYS)),
        "description": _clean_text(parser.meta_value(_META_DESCRIPTION_KEYS)),
        "metadata": {
            "direct_html_version": DIRECT_HTML_VERSION,
            "direct_html_method": "semantic_html",
            "json_parse_errors": parse_errors,
            "article_boundary_used": bool(parser.article_lines),
            "title_heading_injected": bool(clean_title and _H1_RE.search(markdown)),
            "meta_fields": sorted(parser.meta),
            "url": url,
        },
    }


async def read_direct_html_v056m(
    url: str,
    *,
    timeout: float = 22.0,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    started = time.perf_counter()
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers)
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = parse_direct_html_v056m(response.text, url=str(response.url))
        return data, {
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "http_status": response.status_code,
            "direct_html_version": DIRECT_HTML_VERSION,
            "request_sent": True,
        }
    finally:
        if owns_client:
            await client.aclose()


__all__ = [
    "DIRECT_HTML_VERSION",
    "parse_direct_html_v056m",
    "read_direct_html_v056m",
]
