"""Additional deterministic page gates from the v0.5.6l zh-midday holdout."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from .models import DiscoveredURL
from .page_gate_policy_v056 import (
    PageGateDecision,
    annotate_page_gate,
    evaluate_page_gate_policy as _base_evaluate,
)

PAGE_GATE_POLICY_VERSION = "page-gate-policy-v0.5.6m"
_MAGAZINE_PATH_RE = re.compile(r"/magazine/\d+(?:\.s?html?)?$", re.I)
_MAGAZINE_TITLE_RE = re.compile(
    r"^\s*20\d{2}\s*年?\s*(?:第\s*)?\d+\s*期(?:\s*[-|｜].*)?$",
    re.I,
)


def evaluate_page_gate_policy_v056m(item: DiscoveredURL) -> PageGateDecision:
    path = (urlsplit(item.url).path or "/").lower()
    title = str(item.title or "").strip()
    if _MAGAZINE_PATH_RE.search(path) and _MAGAZINE_TITLE_RE.search(title):
        decision = PageGateDecision(
            "magazine_issue_landing",
            "magazine_issue_landing",
            "magazine_path_and_issue_title",
        )
        annotate_page_gate(item, decision)
        item.metadata["page_gate"]["policy_version"] = PAGE_GATE_POLICY_VERSION
        return decision

    decision = _base_evaluate(item)
    item.metadata.setdefault("page_gate", {})["policy_version"] = (
        PAGE_GATE_POLICY_VERSION
    )
    return decision


__all__ = [
    "PAGE_GATE_POLICY_VERSION",
    "PageGateDecision",
    "evaluate_page_gate_policy_v056m",
]
