"""Structural editorial-genre resolution.

Genre describes the content asset; it does not decide whether the daily editor
should select or reject it.
"""

from __future__ import annotations

import re

from ..contracts import (
    AcquisitionBundle,
    AssetClass,
    ContentMedium,
    DiscoveryRecord,
    EditorialGenre,
    Evidence,
)
from .evidence import heading_count, make_evidence

GENRE_VERSION = "canonical-genre-v0.6-pr2"


def resolve_genre(
    record: DiscoveryRecord,
    bundle: AcquisitionBundle,
    *,
    title: str,
    medium: ContentMedium,
    asset_class: AssetClass,
) -> tuple[EditorialGenre, float, tuple[Evidence, ...]]:
    body = bundle.body_markdown or bundle.body_text
    if asset_class is AssetClass.PRIMARY_DOCUMENT:
        genre, confidence, reason = EditorialGenre.POLICY_DOCUMENT, 0.94, "primary_document"
    elif medium is ContentMedium.TELEVISION_TRANSCRIPT:
        genre, confidence, reason = EditorialGenre.REPORTED_FEATURE, 0.82, "broadcast_program_transcript"
    elif re.search(r"(?:专访|專訪|访谈|訪談|采访|採訪|对话|對話)", title):
        genre, confidence, reason = EditorialGenre.INTERVIEW, 0.96, "interview_title"
    elif re.search(r"(?:评论|評論|社论|社論|观察|觀察|述评|述評)", title):
        genre, confidence, reason = EditorialGenre.COMMENTARY, 0.90, "commentary_title"
    elif _analysis_shape(title, body, record.raw_metadata):
        genre, confidence, reason = EditorialGenre.ANALYSIS, 0.84, "analysis_structure"
    elif medium in {ContentMedium.WRITTEN_ARTICLE, ContentMedium.TELEVISION_TRANSCRIPT}:
        genre, confidence, reason = EditorialGenre.REPORTED_FEATURE, 0.78, "substantive_narrative"
    else:
        genre, confidence, reason = EditorialGenre.UNKNOWN, 0.45, "insufficient_genre_evidence"

    evidence = (
        make_evidence(
            record.item_id,
            "editorial_genre",
            "editorial_genre",
            genre.value,
            confidence=confidence,
            excerpt=reason,
            extractor=GENRE_VERSION,
        ),
    )
    return genre, confidence, evidence


def _analysis_shape(title: str, body: str, metadata) -> bool:
    conceptual_title = bool(
        re.search(
            r"(?:政策|制度|治理|法律|法案|战略|戰略|格局|结构|結構|转型|轉型|为何|為何|为什么|為什麼|解读|解讀|解析)",
            title,
        )
    )
    sections = heading_count(metadata)
    conceptual_body = len(
        re.findall(
            r"(?:政策|制度|治理|法律|国家|國家|结构|結構|机制|機制|历史|歷史)",
            body[:16000],
        )
    ) >= 8
    return conceptual_title and sections >= 4 and conceptual_body


__all__ = ["GENRE_VERSION", "resolve_genre"]
