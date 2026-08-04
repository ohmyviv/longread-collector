"""Semantic identity gate for source-chase results in v0.5.6j.

A source-domain match is necessary evidence, but it is never sufficient. The
chased article must also match the seed title/topic. Failed matches are kept as
explicit audit evidence and cannot enter the formal candidate pool.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

from .models import ExtractedArticle

SOURCE_CHASE_IDENTITY_VERSION = "source-chase-identity-v0.5.6j"


@dataclass(slots=True)
class SourceChaseIdentityResult:
    matched: bool
    score: float
    title_similarity: float
    token_overlap: float
    domain_match: bool
    date_distance_days: int | None
    result: str
    evidence: list[str]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["version"] = SOURCE_CHASE_IDENTITY_VERSION
        return payload


def _normalize(value: str) -> str:
    text = str(value or "").lower().replace("’", "'")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    return text


def _grams(value: str) -> set[str]:
    text = _normalize(value)
    if len(text) < 2:
        return {text} if text else set()
    return {text[index : index + 2] for index in range(len(text) - 1)}


def _title_similarity(left: str, right: str) -> tuple[float, float]:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return 0.0, 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    a_grams = _grams(a)
    b_grams = _grams(b)
    intersection = a_grams & b_grams
    union = a_grams | b_grams
    jaccard = len(intersection) / len(union) if union else 0.0
    containment = len(intersection) / max(1, min(len(a_grams), len(b_grams)))
    return round(max(sequence, jaccard, containment), 4), round(containment, 4)


def _parse_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("年", "-").replace("月", "-").replace("日", "")
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        pass
    match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", normalized)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def evaluate_source_chase_identity(
    *,
    parent: ExtractedArticle,
    chased: ExtractedArticle,
    included_domains: set[str] | list[str] | tuple[str, ...],
) -> SourceChaseIdentityResult:
    domains = {str(item or "").lower().removeprefix("www.") for item in included_domains}
    chased_domain = str(chased.domain or "").lower().removeprefix("www.")
    domain_match = not domains or any(
        chased_domain == domain or chased_domain.endswith(f".{domain}")
        for domain in domains
        if domain
    )
    title_score, token_overlap = _title_similarity(parent.title, chased.title)

    parent_date = _parse_date(parent.published_at)
    chased_date = _parse_date(chased.published_at)
    date_distance: int | None = None
    date_ok = True
    if parent_date and chased_date:
        if parent_date.tzinfo is not None:
            parent_date = parent_date.replace(tzinfo=None)
        if chased_date.tzinfo is not None:
            chased_date = chased_date.replace(tzinfo=None)
        date_distance = abs((parent_date.date() - chased_date.date()).days)
        date_ok = date_distance <= 14

    disposition_ok = chased.candidate_disposition in {
        "formal_candidate",
        "special_candidate",
    }
    exact_containment = False
    parent_normalized = _normalize(parent.title)
    chased_normalized = _normalize(chased.title)
    if min(len(parent_normalized), len(chased_normalized)) >= 10:
        exact_containment = (
            parent_normalized in chased_normalized or chased_normalized in parent_normalized
        )

    semantic_match = (
        title_score >= 0.62
        or exact_containment
        or (title_score >= 0.42 and token_overlap >= 0.48 and domain_match)
    )
    matched = bool(disposition_ok and domain_match and date_ok and semantic_match)

    score = (
        0.70 * title_score
        + 0.20 * token_overlap
        + (0.08 if domain_match else 0.0)
        + (0.02 if date_ok else 0.0)
    )
    evidence = [
        f"seed_title={parent.title}",
        f"chased_title={chased.title}",
        f"chased_domain={chased_domain}",
        f"allowed_domains={sorted(domains)}",
        f"disposition={chased.candidate_disposition}",
    ]
    if date_distance is not None:
        evidence.append(f"date_distance_days={date_distance}")

    if matched:
        result = "match"
    elif not disposition_ok:
        result = "chased_candidate_not_eligible"
    elif not domain_match:
        result = "publisher_domain_mismatch"
    elif not date_ok:
        result = "publication_date_mismatch"
    else:
        result = "semantic_title_mismatch"

    return SourceChaseIdentityResult(
        matched=matched,
        score=round(score, 4),
        title_similarity=title_score,
        token_overlap=token_overlap,
        domain_match=domain_match,
        date_distance_days=date_distance,
        result=result,
        evidence=evidence,
    )


def reject_source_chase_mismatch(
    article: ExtractedArticle,
    identity: SourceChaseIdentityResult,
) -> None:
    article.page_role = "discovery_lead"
    article.page_type = "source_chase_result"
    article.content_type = "source_chase_mismatch"
    article.candidate_disposition = "reject"
    article.special_candidate_type = ""
    article.source_action = "none"
    article.classification_confidence = "high"
    article.classification_reason = "source_chase_identity_mismatch_v056j"
    article.reject_reason = "source_chase_identity_mismatch_v056j"
    article.eligible_for_editor = False
    article.metadata["source_chase_identity"] = identity.as_dict()


__all__ = [
    "SOURCE_CHASE_IDENTITY_VERSION",
    "SourceChaseIdentityResult",
    "evaluate_source_chase_identity",
    "reject_source_chase_mismatch",
]
