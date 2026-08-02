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
    article_path = bool(_ARTICLE_PATH_RE.search(path))

    # A news or research article that happens to discuss a degree/program is
    # not a programme landing page. Require explicit programme language when
    # the URL itself has article structure.
    if decision.page_type == "course_or_program_page" and article_path:
        if not _EXPLICIT_PROGRAM_RE.search(title):
            guarded = PageGateDecision("", "article_or_document", "article_path_guard")
            annotate_page_gate(item, guarded)
            item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
            item.metadata["page_gate"]["guarded_from"] = decision.page_type
            return guarded

    # Institution names can appear in reported headlines. Reject profiles only
    # when the title itself ends as an institution label and the path is not an
    # article route.
    if decision.page_type == "institution_profile":
        if article_path or not _PROFILE_END_RE.search(title):
            guarded = PageGateDecision("", "article_or_document", "profile_false_positive_guard")
            annotate_page_gate(item, guarded)
            item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
            item.metadata["page_gate"]["guarded_from"] = decision.page_type
            return guarded

    # Avoid treating an article that merely quotes an announcement as the
    # announcement itself. The formal notice marker must lead the title or the
    # URL must itself be a notice/announcement route.
    if decision.page_type == "award_or_public_notice":
        notice_path = bool(
            re.search(r"/(?:notices?|announcements?|gongshi|gonggao)(?:/|$)", path, re.I)
        )
        if not notice_path and not _FORMAL_NOTICE_RE.search(title):
            guarded = PageGateDecision("", "article_or_document", "notice_false_positive_guard")
            annotate_page_gate(item, guarded)
            item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
            item.metadata["page_gate"]["guarded_from"] = decision.page_type
            return guarded

    annotate_page_gate(item, decision)
    item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
    return decision


__all__ = [
    "PAGE_GATE_POLICY_VERSION",
    "PAGE_GATE_VERSION",
    "PageGateDecision",
    "evaluate_page_gate_policy",
]
