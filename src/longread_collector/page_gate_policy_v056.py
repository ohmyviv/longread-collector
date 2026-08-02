"""False-positive guards for the general v0.5.6 page gates."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .page_gates_v056 import (
    PAGE_GATE_VERSION,
    PageGateDecision,
    annotate_page_gate,
    evaluate_page_gate as _base_evaluate_page_gate,
)

PAGE_GATE_POLICY_VERSION = "page-gate-policy-v0.5.6c"

_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|news|story|stories|feature|features|analysis|"
    r"investigation|detail|content)/|\.s?html?$",
    re.I,
)
_EXPLICIT_PROGRAM_RE = re.compile(
    r"\b(?:academic|graduate|undergraduate|degree|certificate)\s+program\b|"
    r"\b(?:bachelor|master(?:'s)?|phd|doctorate)\s+(?:of|in)\b|"
    r"\badmissions?\b|(?:专业介绍|培养方案|招生项目|学位项目|课程设置)",
    re.I,
)
_REPORTED_TITLE_RE = re.compile(
    r"\b(?:investigation|investigates?|finds?|found|reveals?|inside|how|why|"
    r"reporting|analysis)\b|(?:调查|暗访|发现|揭秘|追踪|如何|为何|背后)",
    re.I,
)
_EVENT_ACTION_RE = re.compile(
    r"\b(?:register|registration|join us|tickets?|book now|rsvp|apply now|"
    r"event agenda|webinar details)\b|(?:报名|注册参加|活动议程|购票|参会)",
    re.I,
)
_EVENT_NEGATION_RE = re.compile(
    r"\b(?:no|without|not an?)\s+(?:registration|event agenda|invitation)\b|"
    r"(?:无需报名|不是活动通知|无活动议程)",
    re.I,
)
_FORMAL_NOTICE_RE = re.compile(
    r"^(?:关于.{0,80}(?:的)?(?:公示|公告|通知)|"
    r"(?:公示|公告|通知)[:：\s]|推荐参评|拟推荐|获奖名单|结果公告|征集通知)|"
    r"^(?:award notice|public notice|call for nominations)\b",
    re.I,
)
_PROFILE_END_RE = re.compile(
    r"(?:研究中心|研究院|实验室|课题组|中心简介|机构简介)$|"
    r"\b(?:research cent(?:er|re)|institute|laboratory|lab)\b$",
    re.I,
)


def _guard(
    item: DiscoveredURL,
    decision: PageGateDecision,
    evidence: str,
) -> PageGateDecision:
    guarded = PageGateDecision("", "article_or_document", evidence)
    annotate_page_gate(item, guarded)
    item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
    item.metadata["page_gate"]["guarded_from"] = decision.page_type
    return guarded


def evaluate_page_gate_policy(item: DiscoveredURL) -> PageGateDecision:
    decision = _base_evaluate_page_gate(item)
    if not decision.rejected:
        item.metadata.setdefault("page_gate", {})["policy_version"] = (
            PAGE_GATE_POLICY_VERSION
        )
        return decision

    parts = urlsplit(item.url)
    path = (parts.path or "/").lower()
    title = str(item.title or "").strip()
    description = str(item.description or "").strip()
    sample = f"{title} {description}"
    article_path = bool(_ARTICLE_PATH_RE.search(path))

    # Reported articles can discuss a degree programme without being a course
    # landing page. Journalistic language on an article route takes priority.
    if decision.page_type == "course_or_program_page" and article_path:
        if _REPORTED_TITLE_RE.search(title) or not _EXPLICIT_PROGRAM_RE.search(title):
            return _guard(item, decision, "reported_article_program_guard")

    # A conference can be the subject of reporting. On an article route, only
    # retain the event gate when there is a positive call to register/join and
    # no explicit negation.
    if decision.page_type == "event_or_release_announcement" and article_path:
        actionable = bool(_EVENT_ACTION_RE.search(sample))
        negated = bool(_EVENT_NEGATION_RE.search(sample))
        if not actionable or negated or _REPORTED_TITLE_RE.search(title):
            return _guard(item, decision, "reported_article_event_guard")

    # Institution names can appear in reported headlines. Reject profiles only
    # when the title itself ends as an institution label and the path is not an
    # article route.
    if decision.page_type == "institution_profile":
        if article_path or not _PROFILE_END_RE.search(title):
            return _guard(item, decision, "profile_false_positive_guard")

    # Avoid treating an article that merely quotes an announcement as the
    # announcement itself. The formal notice marker must lead the title or the
    # URL must itself be a notice/announcement route.
    if decision.page_type == "award_or_public_notice":
        notice_path = bool(
            re.search(r"/(?:notices?|announcements?|gongshi|gonggao)(?:/|$)", path, re.I)
        )
        if not notice_path and not _FORMAL_NOTICE_RE.search(title):
            return _guard(item, decision, "notice_false_positive_guard")

    annotate_page_gate(item, decision)
    item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
    return decision


__all__ = [
    "PAGE_GATE_POLICY_VERSION",
    "PAGE_GATE_VERSION",
    "PageGateDecision",
    "evaluate_page_gate_policy",
]
