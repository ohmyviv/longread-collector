from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

CLASSIFICATION_VERSION = "collector-v0.4.0"

SOCIAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "threads.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
}
ACADEMIC_DOMAIN_SUFFIXES = (
    "mdpi.com",
    "sagepub.com",
    "cell.com",
    "sciencedirect.com",
    "emerald.com",
)
JOB_PATH_MARKERS = ("/jobs/", "/job/", "/careers/", "/career/")
AUTH_PATH_MARKERS = ("/sign-in", "/signin", "/login")
LISTING_PATH_MARKERS = (
    "/channels/",
    "/companies/industry/",
    "/newspaper",
    "/tag/",
    "/tags/",
    "/search",
    "/category/",
)
REFERENCE_PATH_MARKERS = (
    "/study-notes/",
    "/exams/",
    "genetics-glossary",
    "/glossary/",
    "/dictionary/",
)
BLOCKED_TITLES = {
    "just a moment...",
    "403 forbidden",
    "access denied",
    "sign in | emerald publishing",
}
SPAM_PATTERN = re.compile(
    r"(porn|casino|博彩|天天资料|期期准|เครดิตฟรี|สล็อต)",
    re.IGNORECASE,
)
PROMOTIONAL_PATTERN = re.compile(
    r"(hiring|apply now|master'?s programme|clinical trial|services for|"
    r"summit 20\d{2}|course)",
    re.IGNORECASE,
)
EVENT_NEWS_PATTERN = re.compile(
    r"(大赛.*决赛|招聘会|送岗惠民生|举行-中新网|开幕式|圆满举行)",
    re.IGNORECASE,
)
SOURCE_LEAD_PATTERN = re.compile(
    r"(investigation|propublica|drilled|spotlight pa|full report|"
    r"read the article|original report|according to|foreign policy|"
    r"原文|调查|报告全文|完整政策)",
    re.IGNORECASE,
)
WIRE_AP_PATTERN = re.compile(
    r"(\bassociated press\b|\bthe associated press\b|\bap news\b|"
    r"\bby ap\b|—\s*ap\b)",
    re.IGNORECASE,
)
WIRE_REUTERS_PATTERN = re.compile(r"\breuters\b", re.IGNORECASE)
TRANSLATION_PATTERN = re.compile(
    r"(translated by|translation by|english version|译者|翻译：|英文版)",
    re.IGNORECASE,
)
GOVERNANCE_FEATURE_PATTERN = re.compile(
    r"(机制|流程|治理|响应|处置|案例|常态|复盘|制度|预警|问责|协同)",
    re.IGNORECASE,
)
WIRE_VARIANT_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "based",
    "billion",
    "by",
    "canceled",
    "cancelled",
    "cancel",
    "for",
    "grant",
    "grants",
    "identity",
    "in",
    "is",
    "it",
    "of",
    "on",
    "political",
    "politics",
    "project",
    "projects",
    "solely",
    "the",
    "to",
    "was",
    "were",
}


@dataclass(slots=True)
class ClassificationResult:
    page_role: str = "standalone_content"
    page_type: str = "article"
    content_type: str = "unknown"
    candidate_disposition: str = "reject"
    special_candidate_type: str = ""
    source_relationship: str = "original"
    original_publisher: str = ""
    original_url: str = ""
    wire_service: str = ""
    source_action: str = "none"
    duplicate_type: str = "none"
    content_cluster_id: str = ""
    confidence: str = "medium"
    reason: str = "insufficient_editorial_evidence"

    @property
    def eligible_for_editor(self) -> bool:
        return self.candidate_disposition == "formal_candidate"


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _is_social(domain: str) -> bool:
    return any(domain == item or domain.endswith(f".{item}") for item in SOCIAL_DOMAINS)


def normalize_title(title: str) -> str:
    value = title.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    value = re.sub(r"\s*(?:::|\|)\s*[^|:]{2,80}$", "", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def wire_title_fingerprint(title: str) -> str:
    tokens = [
        token
        for token in normalize_title(title).split()
        if token not in WIRE_VARIANT_STOPWORDS
        and not token.isdigit()
        and len(token) > 1
    ]
    stable_tokens = sorted(set(tokens))
    if len(stable_tokens) < 3:
        stable_tokens = normalize_title(title).split()
    return " ".join(stable_tokens)


def wire_cluster_id(wire_service: str, title: str) -> str:
    fingerprint = wire_title_fingerprint(title)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:12]
    return f"wire-{wire_service.lower()}-{digest}"


def _result(
    *,
    page_role: str,
    page_type: str,
    content_type: str,
    disposition: str,
    reason: str,
    confidence: str = "high",
    special_candidate_type: str = "",
    source_relationship: str = "original",
    original_publisher: str = "",
    original_url: str = "",
    wire_service: str = "",
    source_action: str = "none",
    duplicate_type: str = "none",
    content_cluster_id: str = "",
) -> ClassificationResult:
    return ClassificationResult(
        page_role=page_role,
        page_type=page_type,
        content_type=content_type,
        candidate_disposition=disposition,
        special_candidate_type=special_candidate_type,
        source_relationship=source_relationship,
        original_publisher=original_publisher,
        original_url=original_url,
        wire_service=wire_service,
        source_action=source_action,
        duplicate_type=duplicate_type,
        content_cluster_id=content_cluster_id,
        confidence=confidence,
        reason=reason,
    )


def _published_year(published_at: str, title: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", f"{published_at} {title}")
    return int(match.group(1)) if match else None


def _looks_like_wire_feature(
    title: str,
    verification_level: str,
    content_chars: int,
) -> bool:
    words = normalize_title(title).split()
    return (
        verification_level == "A"
        and len(words) >= 12
        and content_chars >= 6000
    ) or bool(re.search(r"\b(how|why|inside|rise|future|gain ground)\b", title, re.I))


def classify_candidate(
    *,
    url: str,
    title: str,
    description: str = "",
    author: str = "",
    markdown: str = "",
    published_at: str = "",
    verification_level: str = "",
    content_chars: int = 0,
) -> ClassificationResult:
    """Classify one result using reusable page, source and content evidence."""

    domain = _domain(url)
    parts = urlsplit(url)
    path = (parts.path or "/").lower()
    query = parts.query.lower()
    sample = " ".join((title, description, author, markdown[:8000])).strip()
    lowered = sample.lower()
    title_lower = title.strip().lower()

    if SPAM_PATTERN.search(title) or (
        "/wpforms/tmp/" in path and path.endswith(".pdf")
    ):
        return _result(
            page_role="non_content",
            page_type="spam_or_malicious",
            content_type="spam",
            disposition="reject",
            source_relationship="uncertain",
            reason="spam_or_abused_upload",
        )

    job_evidence = (
        domain.startswith("jobs.")
        or any(marker in path for marker in JOB_PATH_MARKERS)
        or re.search(r"\b(hiring|job vacancy|clinical research coordinator)\b", title, re.I)
        or re.search(r"\bmanager\b.*\bpublications\b", title, re.I)
    )
    if job_evidence:
        return _result(
            page_role="non_content",
            page_type="social_or_ugc" if _is_social(domain) else "job_or_career",
            content_type="job_listing",
            disposition="reject",
            reason="job_page",
        )

    if (
        title_lower in BLOCKED_TITLES
        or any(marker in path for marker in AUTH_PATH_MARKERS)
        or "returnurl=" in query
    ):
        return _result(
            page_role="non_content",
            page_type=(
                "login_or_auth"
                if "sign" in title_lower or "login" in lowered
                else "blocked_or_captcha"
            ),
            content_type=(
                "academic_paper"
                if any(domain.endswith(suffix) for suffix in ACADEMIC_DOMAIN_SUFFIXES)
                else "unknown"
            ),
            disposition="reject",
            reason="blocked_or_auth",
        )

    if path in {"", "/"}:
        return _result(
            page_role="non_content",
            page_type="homepage",
            content_type="promotional_content",
            disposition="reject",
            reason="homepage",
        )

    if _is_social(domain):
        if PROMOTIONAL_PATTERN.search(sample):
            return _result(
                page_role="non_content",
                page_type="social_or_ugc",
                content_type=(
                    "job_listing"
                    if re.search(r"\b(hiring|job)\b", sample, re.I)
                    else "promotional_content"
                ),
                disposition="reject",
                reason="social_promotion",
            )
        if SOURCE_LEAD_PATTERN.search(sample):
            if re.search(r"(manifesto|policy|政纲|政策全文)", sample, re.I):
                content_type = "primary_statement"
                relationship = "original"
                action = "find_primary_document"
            elif re.search(r"(investigation|propublica|drilled|调查)", sample, re.I):
                content_type = "reported_longread"
                relationship = "secondary_republish"
                action = "find_original_article"
            else:
                content_type = "reported_article"
                relationship = "secondary_republish"
                action = "replace_with_original_source"
            return _result(
                page_role="discovery_lead",
                page_type="social_or_ugc",
                content_type=content_type,
                disposition="original_source_required",
                source_relationship=relationship,
                source_action=action,
                confidence="medium",
                reason="credible_source_lead",
            )
        return _result(
            page_role="non_content",
            page_type="social_or_ugc",
            content_type=(
                "ai_generated_content"
                if domain.endswith("threads.com") and "meta.ai" in lowered
                else (
                    "primary_statement"
                    if re.search(r"(official|president|government|zelensky)", lowered)
                    else "short_news"
                )
            ),
            disposition="reject",
            reason="social_not_standalone",
        )

    path_segments = [segment for segment in path.split("/") if segment]
    news_channel = domain.endswith("theguardian.com") and len(path_segments) <= 2
    if any(marker in path for marker in LISTING_PATH_MARKERS) or news_channel:
        if "/companies/industry/" in path:
            content_type = "company_directory"
        elif "newspaper" in path:
            content_type = "newspaper_listing"
        elif news_channel:
            content_type = "news_listing"
        else:
            content_type = "reference_content"
        return _result(
            page_role="non_content",
            page_type="channel_or_listing",
            content_type=content_type,
            disposition="reject",
            reason="listing_page",
        )

    if "services" in title_lower and (
        "translation" in title_lower or "interpretation" in title_lower
    ):
        return _result(
            page_role="non_content",
            page_type="service_landing",
            content_type="promotional_content",
            disposition="reject",
            reason="service_landing",
        )

    if any(marker in path for marker in REFERENCE_PATH_MARKERS) or "cliffsnotes" in domain:
        if "cliffsnotes" in domain:
            content_type = "study_notes"
        elif "/exams/" in path:
            content_type = "exam_guide"
        elif "glossary" in path:
            content_type = "glossary"
        else:
            content_type = "reference_content"
        return _result(
            page_role="non_content",
            page_type="reference_page",
            content_type=content_type,
            disposition="reject",
            reason="reference_page",
        )

    ap_evidence = bool(WIRE_AP_PATTERN.search(sample)) or "/news/ap/" in path
    reuters_evidence = bool(WIRE_REUTERS_PATTERN.search(sample))
    if ap_evidence:
        cluster = wire_cluster_id("AP", title)
        if _looks_like_wire_feature(title, verification_level, content_chars):
            return _result(
                page_role="discovery_lead",
                page_type="article",
                content_type="syndicated_wire",
                disposition="original_source_required",
                source_relationship="wire_republish",
                original_publisher="Associated Press",
                wire_service="AP",
                source_action="replace_with_original_source",
                content_cluster_id=cluster,
                reason="ap_source_chase",
            )
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="syndicated_wire",
            disposition="reject",
            source_relationship="wire_republish",
            original_publisher="Associated Press",
            wire_service="AP",
            duplicate_type="cross_site_same_wire",
            content_cluster_id=cluster,
            reason="short_or_repeated_ap_wire",
        )

    if reuters_evidence:
        return _result(
            page_role="discovery_lead",
            page_type="article",
            content_type="secondary_news",
            disposition="original_source_required",
            source_relationship="secondary_republish",
            original_publisher="Reuters",
            wire_service="Reuters",
            source_action="replace_with_original_source",
            content_cluster_id=wire_cluster_id("Reuters", title),
            reason="reuters_source_chase",
        )

    if any(domain.endswith(suffix) for suffix in ACADEMIC_DOMAIN_SUFFIXES) or "/doi/" in path:
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="academic_paper",
            disposition="special_candidate",
            special_candidate_type="academic",
            source_action="retain_with_source_label",
            reason="academic_special",
        )

    primary_document = path.endswith(".pdf") or "manifesto" in title_lower or "工作报告" in title
    if primary_document:
        year = _published_year(published_at, title)
        stale = year is not None and year < datetime.now().year - 1
        if stale:
            return _result(
                page_role="standalone_content",
                page_type="document",
                content_type="primary_document",
                disposition="reject",
                reason="stale_primary_document",
            )
        return _result(
            page_role="standalone_content",
            page_type="document",
            content_type="primary_document",
            disposition="special_candidate",
            special_candidate_type="primary_document",
            source_action="retain_with_source_label",
            reason="primary_document_special",
        )

    if domain.endswith("caus.com") and "外交政策" in title:
        return _result(
            page_role="discovery_lead",
            page_type="article",
            content_type="translated_republish",
            disposition="original_source_required",
            source_relationship="translated_republish",
            original_publisher="Foreign Policy",
            source_action="replace_with_original_source",
            duplicate_type="translated_version",
            reason="translated_source_chase",
        )

    if TRANSLATION_PATTERN.search(sample):
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="translated_republish",
            disposition="formal_candidate",
            source_relationship="translated_republish",
            source_action="retain_with_source_label",
            duplicate_type="translated_version",
            reason="labeled_translation",
        )

    if EVENT_NEWS_PATTERN.search(title):
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="event_news",
            disposition="reject",
            reason="event_news_low_increment",
        )

    government_domain = domain.endswith(".gov.cn") or domain.endswith(".gov")
    if (
        government_domain
        and GOVERNANCE_FEATURE_PATTERN.search(sample)
        and content_chars >= 2500
    ):
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="government_feature",
            disposition="formal_candidate",
            source_action="retain_with_source_label",
            reason="government_feature",
        )

    if domain.endswith("deepmind.google") and content_chars >= 2500:
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="analysis_or_commentary",
            disposition="formal_candidate",
            source_action="retain_with_source_label",
            reason="substantive_policy_analysis",
        )

    if verification_level in {"A", "B"} and content_chars >= 2500:
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="analysis_or_commentary",
            disposition="formal_candidate",
            source_action="retain_with_source_label",
            confidence="medium",
            reason="verified_longform_default",
        )

    return ClassificationResult()
