from __future__ import annotations

import re
from dataclasses import replace
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from .classification import ClassificationResult, classify_candidate as _base_classify_candidate

CLASSIFICATION_VERSION = "collector-v0.5.5"

PRESS_RELEASE_DOMAINS = (
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
    "eurekalert.org",
)
ACADEMIC_DOMAIN_SUFFIXES = (
    "mdpi.com",
    "sciencedirect.com",
    "onlinelibrary.wiley.com",
    "link.springer.com",
    "journals.sagepub.com",
    "academic.oup.com",
    "frontiersin.org",
    "cambridge.org",
    "tandfonline.com",
)
ORIGINAL_REPORTING_DOMAINS = (
    "bellingcat.com",
    "propublica.org",
    "lawfaremedia.org",
    "occrp.org",
    "theatlantic.com",
    "technologyreview.com",
)

CORRECTION_RE = re.compile(
    r"^(?:author\s+)?correction\s*:|^corrigendum\b|^erratum\b|^(?:更正|勘误)[：:]?",
    re.IGNORECASE,
)
TAKEAWAYS_RE = re.compile(
    r"\b(?:three|four|five|six|seven|eight|nine|ten|\d+)\s+takeaways?\b|"
    r"\bwhat\s+to\s+know\b|(?:要点|重点)速览",
    re.IGNORECASE,
)
ROUNDUP_RE = re.compile(
    r"\bcheat\s+sheet\b|^the\s+download\s*:|^briefing\s+chat\s*:|"
    r"\bbooks?\s+in\s+brief\b|\bweek(?:ly)?\s+in\s+review\b|"
    r"\bdaily\s+briefing\b|\bmorning\s+briefing\b|(?:一周|每周)(?:简报|回顾|速览)",
    re.IGNORECASE,
)
MARKET_REPORT_RE = re.compile(
    r"\bmarket\s+(?:report|size|forecast)\b.*\b20\d{2}\s*[-–]\s*20\d{2}\b|"
    r"\bworth\s+\$?[\d,.]+\s+(?:million|billion|trillion)\s+by\s+20\d{2}\b",
    re.IGNORECASE,
)
EVENT_RE = re.compile(
    r"\b(?:annual\s+)?(?:workshop|webinar|conference|summit|symposium|forum)\b|"
    r"(?:研讨会|峰会|论坛|大会|工作坊).*(?:报名|日程|举办|开幕)",
    re.IGNORECASE,
)
COURSE_RE = re.compile(
    r"\bbest\s+.+\s+(?:courses?|programs?)\b|\bcourses?\s+after\b|"
    r"\btraining\s+(?:course|program)\b|(?:课程|培训班|研修班|招生简章)",
    re.IGNORECASE,
)
INSTITUTION_RE = re.compile(
    r"^(?:college|school|department|faculty|institute)\s+of\b|"
    r"(?:学院|研究院|实验室)(?:简介|介绍)$",
    re.IGNORECASE,
)
GOV_EVENT_RE = re.compile(
    r"(?:开展|举办|举行|召开).{0,20}(?:实践|活动|座谈会|交流会|培训|宣讲)|"
    r"(?:圆满举行|顺利举办|调研实践)",
    re.IGNORECASE,
)
PRIMARY_DOCUMENT_RE = re.compile(
    r"\b(?:testimony|hearing statement|federal register|research agenda|"
    r"regulation|rulemaking|official statement|survey results?)\b|"
    r"(?:条例|办法|规定|规划|行动方案|调查公报|就业调查|统计公报|政策文件|立法说明|立场文件)",
    re.IGNORECASE,
)
PROMOTION_POST_RE = re.compile(
    r"\bnew\s+article\s+on\b|\bread\s+the\s+full\s+(?:article|investigation|report)\b|"
    r"\bfull\s+story\s+at\b|(?:阅读全文|完整调查|原文链接)",
    re.IGNORECASE,
)
DEPTH_RE = re.compile(
    r"(?:深度|调查|特稿|专访|访谈|解析|长文|in[- ]depth|investigation|"
    r"long\s*read|feature|analysis|interview)",
    re.IGNORECASE,
)
GOV_REPUBLISH_RE = re.compile(
    r"(?:来源|转载自|转自)[：:]?\s*(?:新华社|新华网|人民日报|商务部|国务院|中国政府网)|"
    r"(?:新华社|商务部).{0,20}(?:电|消息|发布)",
    re.IGNORECASE,
)
STRONG_WIRE_RE = re.compile(
    r"^(?:by\s+)?reuters\b|\breporting\s+by\b|\b©\s*reuters\b|"
    r"^(?:by\s+)?associated\s+press\b|\b—\s*ap\b",
    re.IGNORECASE | re.MULTILINE,
)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _new_result(
    *,
    page_role: str,
    page_type: str,
    content_type: str,
    disposition: str,
    reason: str,
    special_candidate_type: str = "",
    source_relationship: str = "original",
    original_publisher: str = "",
    source_action: str = "none",
    confidence: str = "high",
) -> ClassificationResult:
    return ClassificationResult(
        page_role=page_role,
        page_type=page_type,
        content_type=content_type,
        candidate_disposition=disposition,
        special_candidate_type=special_candidate_type,
        source_relationship=source_relationship,
        original_publisher=original_publisher,
        source_action=source_action,
        confidence=confidence,
        reason=reason,
    )


def _parse_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError, OverflowError):
        pass
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw[:40], fmt).date()
        except ValueError:
            continue
    return None


def _is_academic(domain: str, path: str, title: str, markdown: str) -> bool:
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in ACADEMIC_DOMAIN_SUFFIXES):
        if domain.endswith("frontiersin.org") and "/journals/" in path and "/articles/" not in path:
            return False
        return True
    if domain.endswith("nature.com") and ("/articles/" in path or re.search(r"\bdoi\b", markdown[:1500], re.I)):
        return True
    if path.endswith(".pdf") and re.search(r"\b(thesis|dissertation|journal|volume|doi)\b", f"{title} {markdown[:2000]}", re.I):
        return True
    return False


def _is_primary_document(domain: str, path: str, sample: str) -> bool:
    government = (
        domain.endswith(".gov")
        or domain.endswith(".gov.cn")
        or domain.endswith(".gov.mo")
        or "embassy.gov.cn" in domain
        or domain == "federalregister.gov"
    )
    return government and (PRIMARY_DOCUMENT_RE.search(sample) is not None or path.endswith(".pdf"))


def _known_listing(domain: str, path: str, title: str) -> bool:
    lowered = title.strip().lower()
    if domain == "cen.acs.org" and re.search(r"/explore/(?:features|perspectives|interviews)\.html$", path):
        return True
    if domain == "lawfaremedia.org" and ("/topics/" in path or lowered in {
        "armed conflict", "congress", "courts & litigation", "criminal justice & rule of law",
        "cybersecurity & tech", "democracy & elections",
    }):
        return True
    if domain.endswith("eurekalert.org") and lowered.startswith("eurekalert! news by subject"):
        return True
    if domain.endswith("mdpi.com") and "special issues" in lowered:
        return True
    if domain.endswith("frontiersin.org") and lowered.startswith("frontiers in ") and "/articles/" not in path:
        return True
    return False


def classify_candidate_v055(
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
    domain = _domain(url)
    path = (urlsplit(url).path or "/").lower()
    sample = " ".join((title, description, author, markdown[:8000])).strip()
    lowered = sample.lower()

    if _known_listing(domain, path, title):
        return _new_result(
            page_role="non_content", page_type="channel_or_listing",
            content_type="news_listing", disposition="reject", reason="listing_page_v055",
        )
    if CORRECTION_RE.search(title):
        return _new_result(
            page_role="non_content", page_type="correction_notice",
            content_type="correction_notice", disposition="reject", reason="correction_notice",
        )
    if ROUNDUP_RE.search(title):
        return _new_result(
            page_role="non_content", page_type="newsletter_or_roundup",
            content_type="news_roundup", disposition="reject", reason="news_roundup",
        )
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in PRESS_RELEASE_DOMAINS):
        return _new_result(
            page_role="non_content", page_type="press_release",
            content_type="press_release", disposition="reject", reason="press_release",
        )
    if MARKET_REPORT_RE.search(sample) or (domain.endswith("marketsandmarkets.com") and "report" in lowered):
        return _new_result(
            page_role="non_content", page_type="market_report_sales",
            content_type="promotional_content", disposition="reject", reason="market_report_sales",
        )
    if COURSE_RE.search(sample):
        return _new_result(
            page_role="non_content", page_type="course_or_training",
            content_type="promotional_content", disposition="reject", reason="course_or_training",
        )
    if INSTITUTION_RE.search(title):
        return _new_result(
            page_role="non_content", page_type="institution_profile",
            content_type="promotional_content", disposition="reject", reason="institution_profile",
        )
    if EVENT_RE.search(title) and re.search(r"\b(register|registration|agenda|save the date)\b|(?:报名|议程|参会)", lowered):
        return _new_result(
            page_role="non_content", page_type="event_page",
            content_type="event_news", disposition="reject", reason="event_page",
        )
    if GOV_EVENT_RE.search(title):
        return _new_result(
            page_role="non_content", page_type="event_news",
            content_type="event_news", disposition="reject", reason="institutional_event_news",
        )
    if re.search(r"\bcontact\s+us\b", lowered) and re.search(r"\bour\s+services\b|\bhow\s+we\s+can\s+help\b", lowered):
        return _new_result(
            page_role="non_content", page_type="service_landing",
            content_type="promotional_content", disposition="reject", reason="service_landing",
        )

    if TAKEAWAYS_RE.search(title):
        return _new_result(
            page_role="discovery_lead", page_type="article",
            content_type="reported_longread", disposition="original_source_required",
            source_relationship="secondary_republish", source_action="find_original_article",
            reason="takeaways_requires_main_article",
        )
    if PROMOTION_POST_RE.search(sample):
        return _new_result(
            page_role="discovery_lead", page_type="article_promotion_post",
            content_type="reported_longread", disposition="original_source_required",
            source_relationship="secondary_republish", source_action="find_original_article",
            reason="article_promotion_requires_original",
        )
    if domain.endswith("occrp.org") and ("/project" in path or "investigation project" in lowered):
        return _new_result(
            page_role="discovery_lead", page_type="investigation_project_page",
            content_type="reported_longread", disposition="original_source_required",
            source_action="find_original_article", reason="investigation_project_requires_article",
        )
    if GOV_REPUBLISH_RE.search(sample) and not domain.endswith(("xinhuanet.com", "mofcom.gov.cn", "gov.cn")):
        publisher = "新华社" if "新华社" in sample else "商务部" if "商务部" in sample else "中央原始发布"
        return _new_result(
            page_role="discovery_lead", page_type="article",
            content_type="primary_statement", disposition="original_source_required",
            source_relationship="secondary_republish", original_publisher=publisher,
            source_action="replace_with_original_source", reason="government_republish_requires_original",
        )

    if _is_academic(domain, path, title, markdown):
        return _new_result(
            page_role="standalone_content", page_type="article",
            content_type="academic_paper", disposition="special_candidate",
            special_candidate_type="academic", reason="academic_special_v055",
        )
    if _is_primary_document(domain, path, sample):
        special_type = "primary_data" if re.search(r"(?:survey|统计|调查公报|就业调查)", sample, re.I) else "primary_document"
        return _new_result(
            page_role="standalone_content", page_type="document",
            content_type="primary_document", disposition="special_candidate",
            special_candidate_type=special_type, reason="primary_document_special_v055",
        )

    result = _base_classify_candidate(
        url=url,
        title=title,
        description=description,
        author=author,
        markdown=markdown,
        published_at=published_at,
        verification_level=verification_level,
        content_chars=content_chars,
    )

    if result.candidate_disposition == "original_source_required" and result.original_publisher in {"Reuters", "Associated Press"}:
        strong = domain.endswith(("reuters.com", "apnews.com")) or bool(STRONG_WIRE_RE.search("\n".join((author, markdown[:1500]))))
        trusted_original = any(domain == suffix or domain.endswith("." + suffix) for suffix in ORIGINAL_REPORTING_DOMAINS)
        if trusted_original and not strong and verification_level in {"A", "B"} and content_chars >= 2500:
            result = replace(
                result,
                page_role="standalone_content",
                content_type="reported_article",
                candidate_disposition="formal_candidate",
                source_relationship="original",
                original_publisher="",
                source_action="none",
                confidence="high",
                reason="original_outlet_not_wire_republish_v055",
            )

    published = _parse_date(published_at)
    today = datetime.now(timezone.utc).date()
    if (
        result.candidate_disposition == "formal_candidate"
        and published is not None
        and (today - published).days > 14
        and not DEPTH_RE.search(sample)
        and content_chars < 7000
    ):
        result = replace(
            result,
            page_role="standalone_content",
            content_type="stale_ordinary_article",
            candidate_disposition="reject",
            confidence="high",
            reason="stale_ordinary_article_over_14d",
        )

    return result


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v055"]
