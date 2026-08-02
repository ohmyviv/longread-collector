"""General pre-extraction page-type gates for v0.5.6 PR-C."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .prefilter_v055 import discovery_hard_gate_reason as legacy_hard_gate_reason

PAGE_GATE_VERSION = "general-page-gates-v0.5.6"

_PRESS_PATH_RE = re.compile(
    r"/(?:press[-_]?releases?|news[-_]?releases?|media[-_]?releases?)(?:/|$)", re.I
)
_NEWSLETTER_RE = re.compile(
    r"\bnewsletter\b|\bdaily briefing\b|\bmorning briefing\b|"
    r"\bnews roundup\b|\bpharmalittle\s*:|(?:每日|每周|一周)(?:简报|速览|回顾)",
    re.I,
)
_PODCAST_RE = re.compile(r"\bpodcast\b|(?:播客|音频节目)", re.I)
_BUYING_GUIDE_RE = re.compile(
    r"\bbest\s+(?:organic\s+)?(?:mattresses?|laptops?|phones?|headphones?|"
    r"vacuums?|coffee makers?|products?)\b|\bbuying guide\b|"
    r"\bwe may earn (?:a )?commission\b|(?:购买指南|选购指南|好物推荐)",
    re.I,
)
_ESSAY_FARM_RE = re.compile(
    r"\b\d{2,}\+?\s+.+essay\s+(?:topics?|examples?)\b|"
    r"\bessay examples?\b|\bwrite my essay\b|(?:论文代写|范文大全|作文题目大全)",
    re.I,
)
_PUBLIC_NOTICE_RE = re.compile(
    r"(?:公示|公告|推荐参评|拟推荐|获奖名单|结果公告|征集通知)|"
    r"\b(?:award notice|public notice|call for nominations)\b",
    re.I,
)
_EVENT_RE = re.compile(
    r"\b(?:webinar|conference|workshop|summit|symposium|forum|launch event|"
    r"press conference)\b|(?:发布会|研讨会|峰会|论坛|大会|工作坊|宣讲会)",
    re.I,
)
_EVENT_ACTION_RE = re.compile(
    r"\b(?:register|registration|agenda|save the date|join us|tickets?)\b|"
    r"(?:报名|议程|参会|举办|举行|召开|开幕)",
    re.I,
)
_NEGATED_EVENT_ACTION_RE = re.compile(
    r"\b(?:no|without)\s+(?:registration|agenda|tickets?)"
    r"(?:\s+or\s+(?:event\s+)?(?:registration|agenda|tickets?))*\b",
    re.I,
)
_INSTITUTION_RE = re.compile(
    r"(?:研究中心|研究院|实验室|课题组|中心简介|机构简介)$|"
    r"\b(?:research center|research centre|institute|laboratory|lab)\b$",
    re.I,
)
_PROGRAM_RE = re.compile(
    r"\b(?:degree|major|minor|academic program|graduate program|undergraduate program|"
    r"certificate program|admissions?)\b|(?:专业介绍|培养方案|招生项目|学位项目|课程设置)",
    re.I,
)
_RESOURCE_RE = re.compile(
    r"\b(?:databases?|resource guide|research guide|journal articles?\s*[-–:]\s*databases?)\b|"
    r"(?:数据库导航|资源导航|研究指南)",
    re.I,
)
_PROJECT_RE = re.compile(
    r"\b(?:project overview|project outline|research project)\b|(?:项目简介|项目概况|课题简介)",
    re.I,
)
_CATEGORY_TITLE_RE = re.compile(
    r"^(?:宏观经济|行业研究|新闻动态|research|resources|articles|news|analysis|opinions?)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class PageGateDecision:
    reject_reason: str
    page_type: str
    evidence: str

    @property
    def rejected(self) -> bool:
        return bool(self.reject_reason)


def _domain_path(item: DiscoveredURL) -> tuple[str, str]:
    parts = urlsplit(item.url)
    return parts.netloc.lower().removeprefix("www."), (parts.path or "/").lower()


def _sample(item: DiscoveredURL) -> str:
    return f"{item.title or ''} {item.description or ''}".strip()


def evaluate_page_gate(item: DiscoveredURL) -> PageGateDecision:
    domain, path = _domain_path(item)
    title = str(item.title or "").strip()
    sample = _sample(item)

    # Preserve the long-standing invariant that a host root is a homepage,
    # before an unknown-date policy has a chance to classify it generically.
    if path in {"", "/"}:
        return PageGateDecision("homepage", "homepage", "root_path")

    if _PRESS_PATH_RE.search(path) or re.search(r"^press release\s*[:–-]", title, re.I):
        return PageGateDecision("press_release", "press_release", "url_or_title")

    if "/podcast" in path or _PODCAST_RE.search(title):
        return PageGateDecision("podcast_page", "podcast_page", "url_or_title")

    if _NEWSLETTER_RE.search(title) or "/newsletter" in path:
        return PageGateDecision(
            "newsletter_or_roundup", "newsletter_or_roundup", "url_or_title"
        )

    if (
        _BUYING_GUIDE_RE.search(sample)
        or "/buying-guide" in path
        or re.search(r"/(?:best|reviews?)/", path, re.I)
        and re.search(r"\b(?:best|review|tested)\b", title, re.I)
    ):
        return PageGateDecision(
            "commerce_or_buying_guide", "commerce_or_buying_guide", "commercial_signals"
        )

    if (
        _ESSAY_FARM_RE.search(sample)
        or domain.endswith(("domyessay.com", "papersowl.com", "ivypanda.com"))
        and re.search(r"\bessay\b", sample, re.I)
    ):
        return PageGateDecision("seo_essay_farm", "seo_essay_farm", "title_or_domain")

    if re.search(r"/(?:jobs?|careers?|vacancies)(?:/|$)", path, re.I):
        return PageGateDecision("job_or_career_page", "job_or_career_page", "url_path")

    if _PUBLIC_NOTICE_RE.search(title):
        return PageGateDecision("award_or_public_notice", "award_or_public_notice", "title")

    event_action_sample = _NEGATED_EVENT_ACTION_RE.sub("", sample)
    if (
        re.search(r"/(?:events?|conference|webinars?)(?:/|$)", path, re.I)
        or _EVENT_RE.search(title)
    ) and _EVENT_ACTION_RE.search(event_action_sample):
        return PageGateDecision(
            "event_or_release_announcement", "event_or_release_announcement", "event_signals"
        )

    if (
        domain.startswith("libguides.")
        or re.search(r"/(?:databases?|libguides?|resource-guides?)(?:/|$)", path, re.I)
        or _RESOURCE_RE.search(title)
    ):
        return PageGateDecision(
            "database_or_resource_index", "database_or_resource_index", "resource_signals"
        )

    if re.search(r"/(?:category|categories|topics?|tags?)(?:/|$)", path, re.I):
        return PageGateDecision(
            "category_or_channel_page", "category_or_channel_page", "url_path"
        )
    if _CATEGORY_TITLE_RE.fullmatch(title) and len([p for p in path.split("/") if p]) <= 2:
        return PageGateDecision(
            "category_or_channel_page", "category_or_channel_page", "generic_title_shallow_path"
        )

    explicit_program_path = re.search(
        r"/(?:programs?|courses?|degrees?|majors?|admissions?|areas-of-study)(?:/|$)",
        path,
        re.I,
    )
    nested_study_path = re.search(
        r"/(?:undergraduate|graduate)/(?:areas-of-study|programs?|degrees?|majors?)(?:/|$)",
        path,
        re.I,
    )
    if (
        (explicit_program_path or nested_study_path)
        and not re.search(r"/(?:news|article|story|research)/", path, re.I)
    ) or _PROGRAM_RE.search(title):
        return PageGateDecision(
            "course_or_program_page", "course_or_program_page", "program_signals"
        )

    if (
        re.search(r"/(?:about|centers?|centres?|institutes?|labs?)(?:/|$)", path, re.I)
        and _INSTITUTION_RE.search(title)
    ) or (_INSTITUTION_RE.search(title) and len(title) < 80 and not _EVENT_RE.search(title)):
        return PageGateDecision(
            "institution_profile", "institution_profile", "profile_title_and_path"
        )

    if (
        re.search(r"/(?:projects?|project-details?)(?:/|$)", path, re.I)
        and _PROJECT_RE.search(sample)
    ):
        return PageGateDecision("project_landing_page", "project_landing_page", "project_signals")

    legacy = legacy_hard_gate_reason(item)
    if legacy:
        legacy_types = {
            "listing_page": "category_or_channel_page",
            "search_or_listing_page": "category_or_channel_page",
            "correction_notice": "correction_notice",
            "news_roundup": "newsletter_or_roundup",
            "press_release": "press_release",
            "market_report_sales": "market_report_sales",
            "course_or_training": "course_or_program_page",
            "event_page": "event_or_release_announcement",
            "institutional_event_news": "event_or_release_announcement",
        }
        return PageGateDecision(legacy, legacy_types.get(legacy, legacy), "legacy_gate")

    item.metadata.setdefault("page_gate", {}).update(
        {
            "version": PAGE_GATE_VERSION,
            "page_type": "article_or_document",
            "evidence": "no_deterministic_gate",
        }
    )
    return PageGateDecision("", "article_or_document", "")


def annotate_page_gate(item: DiscoveredURL, decision: PageGateDecision) -> None:
    item.metadata["page_gate"] = {
        "version": PAGE_GATE_VERSION,
        "page_type": decision.page_type,
        "reject_reason": decision.reject_reason,
        "evidence": decision.evidence,
    }


__all__ = [
    "PAGE_GATE_VERSION",
    "PageGateDecision",
    "annotate_page_gate",
    "evaluate_page_gate",
]
