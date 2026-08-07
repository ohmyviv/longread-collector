"""Low-regret deterministic Acquisition Gate for v0.6 PR-6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from ...normalization import canonicalize_url
from ..audit.events import make_stage_event
from ..contracts import (
    DiscoveryRecord,
    Evidence,
    FlowStatus,
    GateAction,
    GateDecision,
    StageEvent,
    StageEventType,
    StageName,
    TechnicalStatus,
)
from .context import GateContext

ACQUISITION_GATE_VERSION = "acquisition-gate-v0.6-pr6"
CONTRACT_SCHEMA_VERSION = "v06-contracts-v1"
_BJ = ZoneInfo("Asia/Shanghai")

_AUTH_PATH_RE = re.compile(
    r"/(?:login|log-in|signin|sign-in|auth|authenticate|captcha|account)(?:/|$)",
    re.I,
)
_SEARCH_INDEX_RE = re.compile(r"/(?:search)(?:/|$)", re.I)
_CATEGORY_ROOTS = frozenset({"tag", "tags", "category", "categories", "topic", "topics"})
_JOB_PATH_RE = re.compile(r"/(?:jobs?|careers?|vacancies)(?:/|$)", re.I)
_MAGAZINE_PATH_RE = re.compile(r"/magazine/\d+(?:\.s?html?)?$", re.I)
_MAGAZINE_TITLE_RE = re.compile(
    r"^\s*20\d{2}\s*年?\s*(?:第\s*)?\d+\s*期(?:\s*[-|｜].*)?$",
    re.I,
)
_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|news|story|stories|feature|features|analysis|"
    r"investigation|detail|content|opinion|essay|report)/|\.s?html?$",
    re.I,
)
_AMBIGUOUS_ROOT_RE = re.compile(
    r"^/(?:events?|programs?|courses?|projects?|about|research)/?$",
    re.I,
)
_GENERIC_TITLE_RE = re.compile(
    r"^(?:events?|programs?|courses?|projects?|about|research|新闻|活动|项目|课程|研究)$",
    re.I,
)
_SEMANTIC_AMBIGUITY_RE = re.compile(
    r"\b(?:podcast|webinar|conference|workshop|summit|program|course|press release|"
    r"newsletter|roundup)\b|(?:播客|研讨会|峰会|论坛|大会|培训|课程|发布会|简报|预告)",
    re.I,
)
_SPECIAL_TITLE_RE = re.compile(
    r"\b(?:research report|working paper|white paper|guidance document|official report|"
    r"systematic review|regulatory guidance|journal article)\b|"
    r"(?:研究报告|工作论文|白皮书|学术论文|系统综述|监管指引|指导意见|指导文件|"
    r"管理办法|实施办法|条例|规定)",
    re.I,
)
_SPECIAL_PATH_RE = re.compile(
    r"\.pdf$|/(?:doi|journals?|papers?|working-paper|white-paper|guidance|"
    r"official-report|publications?)(?:/|$)",
    re.I,
)
_ACADEMIC_DOMAIN_RE = re.compile(
    r"(?:^|\.)(?:doi\.org|ncbi\.nlm\.nih\.gov|academic\.oup\.com|"
    r"sciencedirect\.com|tandfonline\.com|onlinelibrary\.wiley\.com|"
    r"link\.springer\.com|jstor\.org|iopscience\.iop\.org)$",
    re.I,
)


@dataclass(frozen=True, slots=True)
class AcquisitionGateRun:
    decision: GateDecision
    event: StageEvent


def _canonical(url: str) -> str:
    try:
        return canonicalize_url(url)
    except Exception:
        return str(url or "").strip()


def _normalise_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_BJ)
    return value.astimezone(_BJ)


def _parse_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_BJ)
    return parsed.astimezone(_BJ)


def _date_evidence(record: DiscoveryRecord) -> list[tuple[datetime, float, Evidence]]:
    result: list[tuple[datetime, float, Evidence]] = []
    for evidence in record.evidence:
        if evidence.field != "published_at_hint":
            continue
        parsed = _parse_date(evidence.value)
        if parsed is None:
            continue
        result.append((parsed, float(evidence.confidence or 0.0), evidence))
    return result


def _special_document_hint(record: DiscoveryRecord) -> bool:
    parts = urlsplit(record.url)
    domain = parts.netloc.lower().removeprefix("www.")
    path = (parts.path or "/").lower()
    sample = f"{record.title_hint} {record.description_hint}"
    metadata_hint = str(record.raw_metadata.get("asset_class_hint", "")).lower()
    if metadata_hint in {"primary_document", "academic_paper", "institutional_report"}:
        return True
    if _SPECIAL_PATH_RE.search(path) or _ACADEMIC_DOMAIN_RE.search(domain):
        return True
    if _SPECIAL_TITLE_RE.search(sample):
        return True
    if domain.endswith((".gov", ".gov.cn")) and re.search(
        r"(?:办法|条例|规定|指导|指引|白皮书|报告)|"
        r"\b(?:guidance|regulation|official report)\b",
        sample,
        re.I,
    ):
        return True
    return False


def _invalid_url(record: DiscoveryRecord) -> bool:
    parts = urlsplit(record.url)
    return parts.scheme.lower() not in {"http", "https"} or not parts.netloc


def _explicit_category_index(path: str) -> bool:
    """Reject only shallow, explicit taxonomy routes, never deep content below them."""
    segments = [segment for segment in (path or "/").split("/") if segment]
    if not segments or segments[0].lower() not in _CATEGORY_ROOTS:
        return False
    if len(segments) > 2:
        return False
    return not bool(_ARTICLE_PATH_RE.search(path))


def _generic_ambiguous_root(record: DiscoveryRecord) -> bool:
    path = urlsplit(record.url).path or "/"
    title = str(record.title_hint or "").strip()
    return bool(_AMBIGUOUS_ROOT_RE.fullmatch(path)) and (
        not title or bool(_GENERIC_TITLE_RE.fullmatch(title))
    )


def _best_confidence(dates: Iterable[tuple[datetime, float, Evidence]]) -> float:
    return max((confidence for _, confidence, _ in dates), default=0.0)


def _priority_features(
    record: DiscoveryRecord,
    *,
    dates: list[tuple[datetime, float, Evidence]],
    special: bool,
) -> dict[str, float]:
    path = urlsplit(record.url).path or "/"
    registered = str(record.raw_metadata.get("purpose", "")) == "native_source_scan"
    sample = f"{record.title_hint} {record.description_hint}"
    return {
        "registered_source": 1.0 if registered else 0.0,
        "article_path_signal": 1.0 if _ARTICLE_PATH_RE.search(path) else 0.0,
        "special_document_hint": 1.0 if special else 0.0,
        "publication_confidence": _best_confidence(dates),
        "discovery_rank_signal": 1.0 / max(1.0, float(record.rank or 1)),
        "semantic_ambiguity": 1.0 if _SEMANTIC_AMBIGUITY_RE.search(sample) else 0.0,
    }


def _gate_evidence(
    record: DiscoveryRecord,
    *,
    reason_code: str,
    value: object,
    confidence: float,
) -> Evidence:
    return Evidence(
        evidence_id=f"{record.item_id}-gate-{reason_code}",
        evidence_type="acquisition_gate_decision",
        source_stage=StageName.ACQUISITION_GATE,
        field=reason_code,
        value=value,
        confidence=confidence,
    )


def _flow(action: GateAction) -> FlowStatus:
    if action is GateAction.ACQUIRE:
        return FlowStatus.PASS
    if action is GateAction.DEFER:
        return FlowStatus.DEFER
    return FlowStatus.REJECT


class AcquisitionGateService:
    """Apply a narrow allowlist of deterministic, low-regret pre-body gates."""

    stage_version = ACQUISITION_GATE_VERSION

    def decide(
        self,
        record: DiscoveryRecord,
        context: GateContext,
        *,
        parent_event_id: str = "",
        created_at_bj: str = "",
    ) -> AcquisitionGateRun:
        dates = _date_evidence(record)
        special = _special_document_hint(record)
        priority = _priority_features(record, dates=dates, special=special)
        parts = urlsplit(record.url)
        path = parts.path or "/"
        canonical = _canonical(record.canonical_url_hint or record.url)
        known_duplicates = {_canonical(value) for value in context.known_duplicate_urls}

        action = GateAction.ACQUIRE
        reason = "acquire_for_evidence"
        confidence = 0.80
        evidence_value: object = record.url

        if _invalid_url(record):
            action, reason, confidence = GateAction.HARD_REJECT, "invalid_web_url", 1.0
        elif canonical and canonical in known_duplicates:
            action, reason, confidence = GateAction.HARD_REJECT, "exact_known_duplicate_url", 1.0
            evidence_value = canonical
        elif path in {"", "/"} and not parts.query:
            action, reason, confidence = GateAction.HARD_REJECT, "homepage_root", 0.99
        elif _AUTH_PATH_RE.search(path):
            action, reason, confidence = GateAction.HARD_REJECT, "authentication_or_captcha_route", 0.99
        elif _SEARCH_INDEX_RE.search(path):
            action, reason, confidence = GateAction.HARD_REJECT, "search_index_route", 0.99
        elif _explicit_category_index(path):
            action, reason, confidence = GateAction.HARD_REJECT, "category_tag_topic_index_route", 0.98
        elif _JOB_PATH_RE.search(path):
            action, reason, confidence = GateAction.HARD_REJECT, "job_or_career_route", 0.99
        elif _MAGAZINE_PATH_RE.search(path) and _MAGAZINE_TITLE_RE.search(record.title_hint):
            action, reason, confidence = GateAction.HARD_REJECT, "magazine_issue_landing", 0.99
        elif _generic_ambiguous_root(record):
            action, reason, confidence = GateAction.DEFER, "ambiguous_non_article_route", 0.80
        else:
            # Any materially conflicting credible dates block a destructive stale
            # conclusion. A later acquisition/canonical stage must resolve them.
            credible_dates = [entry for entry in dates if entry[1] >= 0.60]
            if len(credible_dates) >= 2:
                dates_only = sorted(entry[0].date() for entry in credible_dates)
                if (dates_only[-1] - dates_only[0]).days > 2:
                    action = GateAction.DEFER
                    reason = "publication_date_conflict"
                    confidence = max(entry[1] for entry in credible_dates)
                    evidence_value = tuple(value.isoformat() for value in dates_only)

            high_conf = [entry for entry in dates if entry[1] >= 0.92]
            if action is GateAction.ACQUIRE and high_conf:
                best = max(high_conf, key=lambda entry: (entry[1], entry[0]))
                now = _normalise_now(context.now_bj)
                age_days = (now.date() - best[0].date()).days
                evidence_value = {
                    "published_at": best[0].isoformat(),
                    "age_days": age_days,
                    "confidence": best[1],
                }
                if age_days < -2:
                    action = GateAction.DEFER
                    reason = "authoritative_future_publication_date"
                    confidence = best[1]
                elif age_days > context.ordinary_max_age_days and not special:
                    action = GateAction.HARD_REJECT
                    reason = "authoritative_stale_ordinary_article"
                    confidence = best[1]

        evidence = (
            _gate_evidence(
                record,
                reason_code=reason,
                value=evidence_value,
                confidence=confidence,
            ),
        )
        decision = GateDecision(
            schema_version=CONTRACT_SCHEMA_VERSION,
            stage_version=self.stage_version,
            run_id=record.run_id,
            item_id=record.item_id,
            action=action,
            reason_code=reason,
            confidence=confidence,
            estimated_acquisition_cost=0.8 if priority["registered_source"] else 1.0,
            priority_features=priority,
            evidence=evidence,
        )
        event = make_stage_event(
            run_id=record.run_id,
            item_id=record.item_id,
            stage=StageName.ACQUISITION_GATE,
            event_type=StageEventType.GATE_RESULT,
            stage_version=self.stage_version,
            technical_status=TechnicalStatus.SUCCESS,
            flow_status=_flow(action),
            reason_code=reason,
            created_at_bj=created_at_bj or _normalise_now(context.now_bj).isoformat(),
            parent_event_id=parent_event_id,
            attributes={
                "gate_action": action.value,
                "confidence": confidence,
                "estimated_acquisition_cost": decision.estimated_acquisition_cost,
                "priority_features": priority,
            },
            evidence=evidence,
        )
        return AcquisitionGateRun(decision=decision, event=event)


__all__ = [
    "ACQUISITION_GATE_VERSION",
    "AcquisitionGateRun",
    "AcquisitionGateService",
]
