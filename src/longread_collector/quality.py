from __future__ import annotations

import re
from urllib.parse import urlsplit

from .classification import classify_candidate
from .models import DiscoveredURL
from .normalization import canonicalize_url, domain_from_url

# These domains cannot supply standalone daily candidates, but a result may be
# retained as a discovery lead when its title/description points to credible
# original reporting or a primary document.
BLOCKED_DOMAIN_SUFFIXES = (
    "facebook.com",
    "instagram.com",
    "threads.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "linkedin.com",
    "pinterest.com",
    "quora.com",
)

AUTH_PATH_RE = re.compile(
    r"/(?:login|log-in|signin|sign-in|account|auth|subscribe)(?:/|$)",
    re.IGNORECASE,
)
JOB_PATH_RE = re.compile(
    r"/(?:jobs?|careers?|vacanc(?:y|ies)|hiring|apply)(?:/|$)",
    re.IGNORECASE,
)
SEARCH_OR_LISTING_PATH_RE = re.compile(
    r"/(?:search|tag|tags|category|categories|topics?|authors?|archive|archives)(?:/|$)",
    re.IGNORECASE,
)

GENERIC_OR_BLOCKED_TITLES = {
    "instagram",
    "facebook",
    "sign in",
    "log in",
    "login",
    "just a moment...",
    "just a moment",
    "access denied",
    "are you a robot?",
    "page not found",
    "404 not found",
}

BLOCK_PAGE_MARKERS = (
    "are you a robot?",
    "please confirm you are a human",
    "complete the captcha",
    "captcha challenge",
    "verification successful. waiting for",
    "access denied",
    "enable javascript and cookies to continue",
    "log into instagram",
    "sign in to your account",
    "recaptcha requires verification",
    "could not validate captcha",
)

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
RAW_URL_RE = re.compile(r"https?://\S+")
WHITESPACE_RE = re.compile(r"\s+")


def is_blocked_domain(domain: str) -> bool:
    normalized = domain.lower().removeprefix("www.")
    return any(
        normalized == suffix or normalized.endswith("." + suffix)
        for suffix in BLOCKED_DOMAIN_SUFFIXES
    )


def _normalized_title(title: str) -> str:
    return WHITESPACE_RE.sub(" ", (title or "").strip()).lower()


def discovery_reject_reason(url: str, title: str = "", description: str = "") -> str:
    """Return a reason only when a search result has no candidate/lead value."""

    semantic = classify_candidate(url=url, title=title, description=description)
    if semantic.page_role == "discovery_lead":
        return ""
    if semantic.page_role == "non_content":
        return semantic.reason or f"non_content:{semantic.page_type}"

    domain = domain_from_url(url)
    if is_blocked_domain(domain):
        return "blocked_social_or_ugc_domain"

    parts = urlsplit(url)
    path = parts.path or "/"
    title_norm = _normalized_title(title)

    if title_norm in GENERIC_OR_BLOCKED_TITLES:
        return "blocked_or_generic_title"
    if title_norm.startswith(("sign in |", "log in |", "jobs at ", "careers at ")):
        return "blocked_or_generic_title"
    if AUTH_PATH_RE.search(path):
        return "login_or_account_page"
    if JOB_PATH_RE.search(path) or domain.startswith("jobs."):
        return "job_or_career_page"
    if SEARCH_OR_LISTING_PATH_RE.search(path):
        return "search_or_listing_page"
    if path in {"", "/"} and not parts.query:
        return "homepage"

    combined = f"{title}\n{description}".lower()
    if any(
        marker in combined
        for marker in ("job type", "apply now", "sign in to continue", "page not found")
    ):
        return "non_article_search_result"
    return ""


def markdown_prose_chars(content: str) -> int:
    """Estimate readable prose size while discounting navigation and images."""
    text = MARKDOWN_IMAGE_RE.sub(" ", content or "")
    text = MARKDOWN_LINK_RE.sub(
        lambda match: re.sub(r"[\[\]() ]", " ", match.group(0).split("](", 1)[0]),
        text,
    )
    text = RAW_URL_RE.sub(" ", text)
    text = re.sub(r"[`*_>#|~-]", " ", text)
    return len(WHITESPACE_RE.sub("", text))


def content_quality_reason(url: str, title: str, content: str) -> tuple[bool, str, int]:
    """Classify whether extracted Markdown resembles a readable article body."""
    discovery_reason = discovery_reject_reason(url, title)
    if discovery_reason:
        return False, discovery_reason, markdown_prose_chars(content)

    title_norm = _normalized_title(title)
    prefix = (content or "")[:5000].lower()
    if title_norm in GENERIC_OR_BLOCKED_TITLES or any(
        marker in prefix for marker in BLOCK_PAGE_MARKERS
    ):
        return False, "blocked_login_or_captcha_page", markdown_prose_chars(content)

    prose_chars = markdown_prose_chars(content)
    if prose_chars < 600:
        return False, "insufficient_readable_prose", prose_chars

    long_paragraphs = sum(
        1
        for line in (content or "").splitlines()
        if len(WHITESPACE_RE.sub(" ", line).strip()) >= 90
        and not line.lstrip().startswith(("[", "!", "*   [", "- ["))
    )
    links = len(MARKDOWN_LINK_RE.findall(content or ""))
    if links >= 45 and long_paragraphs < 3:
        return False, "navigation_or_listing_page", prose_chars

    return True, "valid_article_body", prose_chars


def filter_discovered(
    discovered: list[DiscoveredURL],
    *,
    max_urls: int,
    max_per_domain: int = 2,
) -> tuple[list[DiscoveredURL], list[dict[str, str]]]:
    """Remove non-content while preserving credible source-chase leads."""
    accepted: list[DiscoveredURL] = []
    rejected: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    domain_counts: dict[str, int] = {}

    for item in discovered:
        canonical = canonicalize_url(item.url)
        if canonical in seen_urls:
            rejected.append({"url": item.url, "reason": "duplicate_url"})
            continue
        seen_urls.add(canonical)

        reason = discovery_reject_reason(item.url, item.title, item.description)
        domain = domain_from_url(canonical)
        if not reason and domain_counts.get(domain, 0) >= max_per_domain:
            reason = "per_domain_cap"
        if reason:
            rejected.append({"url": item.url, "reason": reason})
            continue

        accepted.append(item)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if len(accepted) >= max_urls:
            break

    return accepted, rejected
