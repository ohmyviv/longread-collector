"""Conservative freshness policy built on auditable date evidence for PR-C."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import re

from .freshness_v056 import (
    DateEvidence,
    FRESHNESS_VERSION,
    collect_date_evidence,
    parse_datetime,
)
from .models import DiscoveredURL

BJ = ZoneInfo("Asia/Shanghai")
FRESHNESS_POLICY_VERSION = "freshness-policy-v0.5.6f"

_NOW: ContextVar[datetime | None] = ContextVar("freshness_now_v056", default=None)

_DEPTH_RE = re.compile(
    r"(?:深度|调查|特稿|专访|访谈|解析|长文|追踪|in[- ]depth|investigation|"
    r"long\s*read|longform|feature|analysis|interview|explainer)",
    re.I,
)
_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|story|stories|feature|features|analysis|investigation|"
    r"long-read|longread|news|detail|content|issue)/|\.s?html?$",
    re.I,
)
_SPECIAL_PATH_RE = re.compile(
    r"\.pdf$|/(?:doi|journals?|papers?|working-paper|white-paper|guidance|"
    r"research-report|official-report|task-force-reports?|publications?|"
    r"publicaciones|chapters?|read)/",
    re.I,
)
_SPECIAL_TITLE_RE = re.compile(
    r"\b(?:research report|working paper|white paper|guidance document|"
    r"journal article|systematic review|regulatory guidance|official report|"
    r"task force report)\b|"
    r"(?:研究报告|工作论文|指导文件|白皮书|学术论文|系统综述|监管指引|官方报告)",
    re.I,
)
_ACADEMIC_DOMAIN_RE = re.compile(
    r"(?:^|\.)(?:doi\.org|ncbi\.nlm\.nih\.gov|academic\.oup\.com|"
    r"sciencedirect\.com|tandfonline\.com|onlinelibrary\.wiley\.com|"
    r"link\.springer\.com|jstor\.org|iopscience\.iop\.org)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class FreshnessPolicyDecision:
    allowed: bool
    reject_reason: str
    track: str
    age_days: int | None
    exception_reason: str
    unknown: bool
    score_ordinal: int
    score_penalty: int
    phase: str


def _normalise(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BJ)
    return value.astimezone(BJ)


def begin_freshness_clock(value: datetime) -> Token:
    return _NOW.set(_normalise(value))


def end_freshness_clock(token: Token) -> None:
    _NOW.reset(token)


def current_freshness_time() -> datetime:
    value = _NOW.get()
    return value if value is not None else datetime.now(timezone.utc).astimezone(BJ)


def _corrected_evidence(item: DiscoveredURL) -> list[DateEvidence]:
    corrected: list[DateEvidence] = []
    for entry in collect_date_evidence(item):
        # Generic sitemap lastmod describes crawl/update time, not publication.
        if entry.source == "sitemap_lastmod":
            corrected.append(
                replace(
                    entry,
                    source="sitemap_lastmod_modified",
                    confidence="low",
                    priority=25,
                    role="modified",
                )
            )
        else:
            corrected.append(entry)
    return corrected


def _special_document(item: DiscoveredURL) -> bool:
    parts = urlsplit(item.url)
    domain = parts.netloc.lower().removeprefix("www.")
    path = parts.path.lower()
    sample = f"{item.title or ''} {item.description or ''}"
    if path.endswith(".pdf") or _SPECIAL_PATH_RE.search(path):
        return True
    if _ACADEMIC_DOMAIN_RE.search(domain) and not re.search(
        r"/(?:news|blog|opinion|podcast|events?)/", path, re.I
    ):
        return True
    if _SPECIAL_TITLE_RE.search(sample):
        return True
    if domain.endswith((".gov", ".gov.cn")) and re.search(
        r"(?:指导|指引|办法|条例|报告|白皮书|数据发布)|"
        r"\b(?:guidance|regulation|report|data release)\b",
        sample,
        re.I,
    ):
        return True
    return False


def _depth_and_structure(item: DiscoveredURL) -> tuple[bool, bool]:
    sample = f"{item.title or ''} {item.description or ''}"
    depth = bool(_DEPTH_RE.search(sample))
    path = urlsplit(item.url).path.lower()
    structure = bool(_ARTICLE_PATH_RE.search(path)) or len(
        [part for part in path.split("/") if part]
    ) >= 3
    return depth, structure


def resolve_publication_evidence(item: DiscoveredURL) -> dict[str, Any]:
    evidence = _corrected_evidence(item)
    published = [entry for entry in evidence if entry.role == "published"]
    modified = [entry for entry in evidence if entry.role == "modified"]
    # Stable sort preserves the parser's evidence order within one priority.
    published.sort(key=lambda entry: entry.priority, reverse=True)
    modified.sort(key=lambda entry: entry.priority, reverse=True)
    chosen = published[0] if published else None

    conflicts: list[str] = []
    if chosen is not None:
        for entry in published[1:]:
            if abs((entry.value.date() - chosen.value.date()).days) > 2:
                conflicts.append(f"{entry.source}={entry.value.date().isoformat()}")
    ignored = [
        key
        for key in (
            "captured_at_bj",
            "first_seen_at_bj",
            "captured_at",
            "first_seen_at",
        )
        if item.metadata.get(key)
    ]
    result = {
        "version": FRESHNESS_VERSION,
        "policy_version": FRESHNESS_POLICY_VERSION,
        "published_at_resolved": chosen.value.isoformat() if chosen else "",
        "published_at_source": chosen.source if chosen else "unknown",
        "published_at_confidence": chosen.confidence if chosen else "unknown",
        "date_modified_at": modified[0].value.isoformat() if modified else "",
        "date_conflict_reason": (
            "publication_evidence_conflict:" + "|".join(conflicts[:4])
            if conflicts
            else ""
        ),
        "freshness_unknown": chosen is None,
        "ignored_non_publication_fields": ignored,
        "evidence": [
            {**asdict(entry), "value": entry.value.isoformat()}
            for entry in sorted(evidence, key=lambda entry: entry.priority, reverse=True)
        ],
    }
    item.metadata["freshness"] = result
    return result


def evaluate_freshness_policy(
    item: DiscoveredURL,
    *,
    phase: str = "prefilter",
    now: datetime | None = None,
) -> FreshnessPolicyDecision:
    now_bj = _normalise(now or current_freshness_time())
    resolved = resolve_publication_evidence(item)
    parsed = parse_datetime(resolved["published_at_resolved"])
    special = _special_document(item)
    depth, structure = _depth_and_structure(item)
    native = str(item.metadata.get("purpose", "")) == "native_source_scan"

    if special:
        age = (now_bj.date() - parsed.date()).days if parsed else None
        decision = FreshnessPolicyDecision(
            True,
            "",
            "special_document",
            age,
            "independent_special_candidate_freshness",
            parsed is None,
            parsed.date().toordinal() if parsed else 0,
            0,
            phase,
        )
    elif parsed is None:
        if phase == "prefilter":
            if native:
                allowed = True
                reason = ""
                track = "ordinary_unknown_native"
                exception = "registered_candidate_pending_body_date"
                penalty = -3
            elif structure:
                allowed = True
                reason = ""
                track = "ordinary_unknown_open_structured"
                exception = "structured_candidate_pending_body_date"
                penalty = -7 if not depth else -5
            else:
                allowed = False
                reason = "freshness_unknown_insufficient_evidence"
                track = "ordinary_unknown"
                exception = ""
                penalty = -10
        else:
            if native and (structure or depth):
                allowed = True
                reason = ""
                track = "ordinary_unknown_native_post"
                exception = "registered_article_without_resolved_date"
                penalty = -5
            elif depth and structure:
                allowed = True
                reason = ""
                track = "ordinary_unknown_open_deep_post"
                exception = "deep_structured_article_without_resolved_date"
                penalty = -7
            else:
                allowed = False
                reason = "freshness_unknown_after_extraction"
                track = "ordinary_unknown"
                exception = ""
                penalty = -10
        decision = FreshnessPolicyDecision(
            allowed,
            reason,
            track,
            None,
            exception,
            True,
            0,
            penalty,
            phase,
        )
    else:
        age = (now_bj.date() - parsed.date()).days
        ordinal = parsed.date().toordinal()
        if age < -2:
            decision = FreshnessPolicyDecision(
                False,
                "publication_date_in_future",
                "ordinary",
                age,
                "",
                False,
                ordinal,
                -10,
                phase,
            )
        elif age <= 3:
            decision = FreshnessPolicyDecision(
                True, "", "ordinary_72h", age, "", False, ordinal, 0, phase
            )
        elif age <= 7 and (native or depth) and structure:
            decision = FreshnessPolicyDecision(
                True,
                "",
                "deep_read_4_7d",
                age,
                "registered_source_or_depth_signal",
                False,
                ordinal,
                -1,
                phase,
            )
        elif age <= 7:
            decision = FreshnessPolicyDecision(
                False,
                "stale_4_7d_without_quality_signal",
                "ordinary",
                age,
                "",
                False,
                ordinal,
                -6,
                phase,
            )
        elif age <= 14 and depth and structure:
            decision = FreshnessPolicyDecision(
                True,
                "",
                "deep_read_8_14d",
                age,
                "explicit_depth_signal",
                False,
                ordinal,
                -2,
                phase,
            )
        elif age <= 14:
            decision = FreshnessPolicyDecision(
                False,
                "stale_8_14d_without_depth",
                "ordinary",
                age,
                "",
                False,
                ordinal,
                -8,
                phase,
            )
        else:
            decision = FreshnessPolicyDecision(
                False,
                "stale_article_over_14d",
                "ordinary",
                age,
                "",
                False,
                ordinal,
                -12,
                phase,
            )

    item.metadata.setdefault("freshness", {}).update(
        {
            "policy_version": FRESHNESS_POLICY_VERSION,
            "decision_phase": decision.phase,
            "decision_allowed": decision.allowed,
            "freshness_reject_reason": decision.reject_reason,
            "freshness_track": decision.track,
            "freshness_age_days": decision.age_days,
            "freshness_exception_reason": decision.exception_reason,
            "freshness_unknown": decision.unknown,
            "freshness_score_ordinal": decision.score_ordinal,
            "freshness_score_penalty": decision.score_penalty,
            "unknown_date_policy": (
                "defer_with_penalty" if decision.unknown and decision.allowed else "hard_reject"
            ),
        }
    )
    return decision


def is_special_document(item: DiscoveredURL) -> bool:
    return _special_document(item)


__all__ = [
    "FRESHNESS_POLICY_VERSION",
    "FreshnessPolicyDecision",
    "begin_freshness_clock",
    "current_freshness_time",
    "end_freshness_clock",
    "evaluate_freshness_policy",
    "is_special_document",
    "resolve_publication_evidence",
]
