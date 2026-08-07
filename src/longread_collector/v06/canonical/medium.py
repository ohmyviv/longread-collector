"""Page-surface and main-content-medium resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    ContentMedium,
    DiscoveryRecord,
    Evidence,
    PageSurface,
)
from .evidence import (
    body_prose_chars,
    different_host,
    external_link,
    heading_count,
    make_evidence,
    video_count,
)

MEDIUM_VERSION = "canonical-medium-v0.6-pr2"


@dataclass(frozen=True, slots=True)
class MediumResolution:
    page_surface: PageSurface
    medium: ContentMedium
    transcript_hint: bool
    primary_document_hint: bool
    evidence: tuple[Evidence, ...]
    confidence: float


def resolve_medium(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    resolved_title: str,
    asset_hint: AssetClass | None = None,
) -> MediumResolution:
    metadata = record.raw_metadata
    body = bundle.body_markdown or bundle.body_text
    prose = bundle.prose_length or body_prose_chars(metadata, bundle.content_length)
    headings = heading_count(metadata)
    videos = bundle.video_count or video_count(metadata)
    target = external_link(metadata)
    external_stub = bool(target and different_host(record.url, target) and prose < 500)

    transcript_score, transcript_signals = _television_transcript_score(
        resolved_title,
        body,
        videos,
    )
    transcript_hint = transcript_score >= 3

    primary_hint = _primary_document_hint(resolved_title, body, asset_hint)

    if external_stub:
        surface = PageSurface.EXTERNAL_LINK_STUB
        medium = ContentMedium.UNKNOWN
        confidence = 0.97
        reason = "external_target_with_negligible_local_prose"
    elif primary_hint:
        surface = PageSurface.DOCUMENT_PAGE
        medium = ContentMedium.PRIMARY_DOCUMENT
        confidence = 0.94
        reason = "official_document_structure"
    elif transcript_hint:
        surface = PageSurface.ARTICLE_PAGE
        medium = ContentMedium.TELEVISION_TRANSCRIPT
        confidence = min(0.98, 0.72 + transcript_score * 0.06)
        reason = "broadcast_transcript_signals"
    elif prose >= 1500:
        surface = PageSurface.ARTICLE_PAGE
        medium = ContentMedium.WRITTEN_ARTICLE
        confidence = 0.93 if (headings >= 2 or prose >= 3000) else 0.84
        reason = "substantive_continuous_written_prose"
    elif videos > 0 and prose < 800:
        surface = PageSurface.ARTICLE_PAGE
        medium = ContentMedium.VIDEO_PAGE
        confidence = 0.84
        reason = "video_with_insufficient_written_prose"
    else:
        surface = PageSurface.UNKNOWN
        medium = ContentMedium.UNKNOWN
        confidence = 0.50
        reason = "insufficient_medium_evidence"

    evidence: list[Evidence] = [
        make_evidence(
            record.item_id,
            "body_prose_chars",
            "main_content_medium",
            prose,
            confidence=0.98,
            extractor=MEDIUM_VERSION,
        ),
        make_evidence(
            record.item_id,
            "embedded_video_count",
            "main_content_medium",
            videos,
            confidence=0.98,
            extractor=MEDIUM_VERSION,
        ),
        make_evidence(
            record.item_id,
            "medium_resolution",
            "main_content_medium",
            medium.value,
            confidence=confidence,
            excerpt=reason,
            extractor=MEDIUM_VERSION,
        ),
    ]
    for signal in transcript_signals:
        evidence.append(
            make_evidence(
                record.item_id,
                "broadcast_transcript_signal",
                "main_content_medium",
                signal,
                confidence=0.90,
                extractor=MEDIUM_VERSION,
            )
        )
    if external_stub:
        evidence.append(
            make_evidence(
                record.item_id,
                "external_link_stub",
                "page_surface",
                target,
                confidence=0.97,
                extractor=MEDIUM_VERSION,
            )
        )
    return MediumResolution(
        page_surface=surface,
        medium=medium,
        transcript_hint=transcript_hint,
        primary_document_hint=primary_hint,
        evidence=tuple(evidence),
        confidence=confidence,
    )


def _television_transcript_score(
    title: str,
    body: str,
    videos: int,
) -> tuple[int, tuple[str, ...]]:
    sample = body[:16000]
    signals: list[str] = []
    if re.search(r"(?:央视网|央視網|电视台|電視台|广播电视|廣播電視).*?(?:消息|訊息)", sample):
        signals.append("broadcast_outlet_message")
    if re.search(r"[（(](?:焦点访谈|焦點訪談|新闻联播|新聞聯播|今日说法|今日說法|经济半小时|經濟半小時)[）)]", sample):
        signals.append("named_program_parenthetical")
    if re.search(r"(?:时长|時長)\s*\d{1,2}:\d{2}|视频播放器|視頻播放器|播放视频|播放視頻", sample):
        signals.append("player_duration_or_controls")
    if re.search(r"^(?:#\s*)?(?:焦点访谈|焦點訪談|新闻联播|新聞聯播|今日说法|今日說法)[｜|：:]", title):
        signals.append("program_title_prefix")
    if videos > 0:
        signals.append("embedded_video")
    return len(signals), tuple(signals)


def _primary_document_hint(
    title: str,
    body: str,
    asset_hint: AssetClass | None,
) -> bool:
    if asset_hint is AssetClass.PRIMARY_DOCUMENT:
        return True
    title_markers = (
        "通知",
        "公告",
        "办法",
        "規定",
        "规定",
        "意见",
        "意見",
        "条例",
        "條例",
        "规划",
        "規劃",
        "决定",
        "決定",
        "批复",
        "批復",
        "工作会议",
        "工作會議",
    )
    official_structure = bool(
        re.search(
            r"(?:会议强调|會議強調|会议指出|會議指出|现印发给你们|現印發給你們|请认真按照执行|請認真按照執行)",
            body[:8000],
        )
    )
    return any(marker in title for marker in title_markers) and (
        official_structure
        or bool(re.search(r"[〔\[]20\d{2}[〕\]]\s*\d+\s*号", body[:5000]))
    )


__all__ = ["MEDIUM_VERSION", "MediumResolution", "resolve_medium"]
