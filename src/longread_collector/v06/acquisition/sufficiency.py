"""Sufficiency-aware stopping for v0.6 PR-5 Acquisition Service."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

from ..contracts import DiscoveryRecord, Evidence, StageName
from .types import ExtractorPayload


SUFFICIENCY_VERSION = "acquisition-sufficiency-v0.6-pr5"

_MARKDOWN_RE = re.compile(r"[#>*_`\[\]()!|~\\-]+")
_SPACE_RE = re.compile(r"\s+")
_DECISION_CUE_RE = re.compile(
    r"(?:培训班|培訓班|开班|開班|结业|結業|活动预告|活動預告|书展|書展|"
    r"报名|報名|焦点访谈|焦點訪談|央视网消息|央視網消息|主持人|节目|節目|"
    r"资金流向|資金流向|股价|股價|涨停|漲停|跌停|新品|首发|首發|发布会|發布會)"
)
_LINK_RE = re.compile(r"https?://[^\s)\]>]+", re.I)


@dataclass(frozen=True, slots=True)
class SufficiencyDecision:
    canonicalization: bool
    editorial_judgment: bool
    source_chase: bool
    should_stop: bool
    reason_code: str
    prose_chars: int
    paragraph_count: int
    decision_cue_count: int
    evidence: tuple[Evidence, ...] = ()


def _prose_chars(text: str) -> int:
    cleaned = _MARKDOWN_RE.sub(" ", str(text or ""))
    return len(_SPACE_RE.sub("", cleaned))


def _paragraph_count(text: str) -> int:
    return sum(
        1
        for part in re.split(r"\n\s*\n|(?<=[。！？.!?])\s*\n", str(text or ""))
        if len(_SPACE_RE.sub("", _MARKDOWN_RE.sub(" ", part))) >= 35
    )


def _host(url: str) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")


def _external_links(record: DiscoveryRecord, payload: ExtractorPayload) -> tuple[str, ...]:
    origin = _host(record.url)
    links = list(payload.canonical_links) + list(payload.outbound_links)
    links.extend(_LINK_RE.findall(payload.body[:8000]))
    unique: list[str] = []
    for link in links:
        value = str(link or "").strip().rstrip(".,;，。；")
        if not value.startswith(("http://", "https://")):
            continue
        target = _host(value)
        if target and origin and target != origin and value not in unique:
            unique.append(value)
    return tuple(unique)


def assess_sufficiency(
    record: DiscoveryRecord,
    payload: ExtractorPayload,
) -> SufficiencyDecision:
    """Decide whether more acquisition can materially change downstream judgment.

    This is intentionally not a candidate classifier.  It asks only whether the
    current evidence is sufficient to identify the content asset, make an
    editorial judgment, or chase a more authoritative source.
    """

    body = payload.body.strip()
    prose = _prose_chars(body)
    paragraphs = _paragraph_count(body)
    title = (payload.title or record.title_hint or "").strip()
    date_or_author = bool(payload.published_at or payload.author)
    decision_cues = len(_DECISION_CUE_RE.findall(f"{title}\n{body[:12000]}"))
    external = _external_links(record, payload)

    canonicalization = bool(
        (title and prose >= 350)
        or (prose >= 700)
        or (title and date_or_author and prose >= 220)
        or external
    )

    # Ordinary prose becomes judgeable once there is enough continuous body.
    # Deterministic event/transcript/template cues can make a shorter body
    # sufficient because another scraper is unlikely to change its content type.
    editorial = bool(
        (prose >= 900 and paragraphs >= 2)
        or (prose >= 650 and paragraphs >= 2 and bool(title))
        or (prose >= 450 and decision_cues >= 2 and bool(title))
    )

    source_chase = bool(
        external
        and (
            prose < 700
            or payload.metadata.get("external_link_stub") is True
            or payload.metadata.get("source_chase_hint") is True
        )
    )

    should_stop = editorial or source_chase
    if editorial:
        reason = "sufficient_for_editorial_judgment"
    elif source_chase:
        reason = "sufficient_for_source_chase"
    elif canonicalization:
        reason = "canonical_only_more_body_needed"
    elif body:
        reason = "partial_body_more_evidence_needed"
    else:
        reason = "no_body_more_evidence_needed"

    evidence = (
        Evidence(
            evidence_id=f"{record.item_id}-{payload.extractor}-sufficiency",
            evidence_type="acquisition_sufficiency",
            source_stage=StageName.ACQUISITION,
            field="sufficiency",
            value={
                "canonicalization": canonicalization,
                "editorial_judgment": editorial,
                "source_chase": source_chase,
                "prose_chars": prose,
                "paragraph_count": paragraphs,
                "decision_cue_count": decision_cues,
                "external_link_count": len(external),
            },
            confidence=0.90 if should_stop else 0.75,
            excerpt=reason,
            extractor=SUFFICIENCY_VERSION,
        ),
    )

    return SufficiencyDecision(
        canonicalization=canonicalization,
        editorial_judgment=editorial,
        source_chase=source_chase,
        should_stop=should_stop,
        reason_code=reason,
        prose_chars=prose,
        paragraph_count=paragraphs,
        decision_cue_count=decision_cues,
        evidence=evidence,
    )


__all__ = ["SUFFICIENCY_VERSION", "SufficiencyDecision", "assess_sufficiency"]
