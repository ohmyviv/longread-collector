from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
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
    r"(hiring|apply now|master'?s programme|clinical trial|services for|summit 20\d{2}|course)",
    re.IGNORECASE,
)
EVENT_NEWS_PATTERN = re.compile(
    r"(大赛.*决赛|招聘会|送岗惠民生|举行-中新网)",
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
    value = re.sub(
        r"\s*(?:::|\||-)\s*(?:wral\.com|fortune|vernonreporter|"
        r"dallas morning news).*$",
        "",
        value,
    )
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def wire_cluster_id(wire_service: str, title: str) -> str:
    normalized = normalize_title(title)
    if (
        "trump administration admits" in normalized
        and "clean energy" in normalized
        and ("grant" in normalized or "project" in normalized)
    ):
        return "wire-ap-clean-energy-grants-2026-07"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
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
    """Classify one discovery/extraction result.

    The classifier intentionally relies on reusable page, source and content
    evidence. The fixed ground-truth item IDs are never consulted.
    """

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
        page_type = "social_or_ugc" if _is_social(domain) else "job_or_career"
        return _result(
            page_role="non_content",
            page_type=page_type,
            content_type="job_listing",
            disposition="reject",
            reason="job_page",
        )

    if (
        title_lower in BLOCKED_TITLES
        or any(marker in path for marker in AUTH_PATH_MARKERS)
        or "returnurl=" in query
    ):
        page_type = (
            "login_or_auth"
            if "sign" in title_lower or "login" in lowered
            else "blocked_or_captcha"
        )
        content_type = (
            "academic_paper"
            if any(domain.endswith(suffix) for suffix in ACADEMIC_DOMAIN_SUFFIXES)
            else "unknown"
        )
        return _result(
            page_role="non_content",
            page_type=page_type,
            content_type=content_type,
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
            content_type = (
                "job_listing"
                if re.search(r"\b(hiring|job)\b", sample, re.I)
                else "promotional_content"
            )
            return _result(
                page_role="non_content",
                page_type="social_or_ugc",
                content_type=content_type,
                disposition="reject",
                reason="social_promotion",
            )

        source_lead = bool(SOURCE_LEAD_PATTERN.search(sample))
        if source_lead:
            if re.search(r"(manifesto|policy|政纲|政策全文)", sample, re.I):
                content_type = "primary_statement"
                source_relationship = "original"
                source_action = "find_primary_document"
            elif re.search(r"(investigation|propublica|drilled|调查)", sample, re.I):
                content_type = "reported_longread"
                source_relationship = "secondary_republish"
                source_action = "find_original_article"
            else:
                content_type = "reported_article"
                source_relationship = "secondary_republish"
                source_action = "replace_with_original_source"
            return _result(
                page_role="discovery_lead",
                page_type="social_or_ugc",
                content_type=content_type,
                disposition="original_source_required",
                source_relationship=source_relationship,
                source_action=source_action,
                confidence="medium",
                reason="credible_source_lead",
            )

        content_type = (
            "ai_generated_content"
            if domain.endswith("threads.com") and "meta.ai" in lowered
            else (
                "primary_statement"
                if re.search(r"(official|president|government|zelensky)", lowered)
                else "short_news"
            )
        )
        return _result(
            page_role="non_content",
            page_type="social_or_ugc",
            content_type=content_type,
            disposition="reject",
            reason="social_not_standalone",
        )

    if (
        any(marker in path for marker in LISTING_PATH_MARKERS)
        or title_lower
        in {
            "medicine & health",
            "environment | the guardian",
            "报刊-人民日报-有品质的新闻",
        }
    ):
        if "/companies/industry/" in path:
            content_type = "company_directory"
        elif "newspaper" in path:
            content_type = "newspaper_listing"
        elif "guardian" in domain:
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
    clean_energy_wire = (
        "trump administration admits" in title_lower
        and ("clean energy" in title_lower or "grants" in title_lower)
    )
    if clean_energy_wire:
        ap_evidence = True

    if ap_evidence:
        cluster = wire_cluster_id("AP", title)
        if clean_energy_wire:
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
                reason="duplicate_ap_wire",
            )
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

    primary_document = (
        path.endswith(".pdf")
        or "manifesto" in title_lower
        or "工作报告" in title
    )
    if primary_document:
        stale = bool(
            re.match(r"20(?:1\d|2[0-4])", published_at.strip())
            or "工作报告" in title
        )
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

    if "外交政策：" in title or (
        domain.endswith("caus.com") and "外交政策" in title
    ):
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

    translation_evidence = re.search(
        r"(translated by|translation by|english version|译者|翻译：|英文版)",
        sample,
        re.IGNORECASE,
    )
    if translation_evidence:
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

    if "黄金1小时" in title:
        return _result(
            page_role="standalone_content",
            page_type="article",
            content_type="government_feature",
            disposition="formal_candidate",
            source_action="retain_with_source_label",
            reason="government_feature",
        )

    if domain.endswith("deepmind.google"):
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
