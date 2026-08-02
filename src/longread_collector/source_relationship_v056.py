"""Auditable source-relationship evidence for v0.5.6 PR-D."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

SOURCE_RELATIONSHIP_VERSION = "source-relationship-evidence-v0.5.6d"

_REUTERS_AUTHOR_RE = re.compile(
    r"^(?:by\s+)?(?:reuters|reuters staff|reuters reporters?)$", re.I
)
_AP_AUTHOR_RE = re.compile(
    r"^(?:by\s+)?(?:the\s+)?associated press$|^(?:by\s+)?ap(?:\s+news)?$", re.I
)
_REUTERS_DATELINE_RE = re.compile(
    r"^(?:[A-Z][A-Z .'-]{2,40},?\s+(?:[A-Z][a-z]+\s+\d{1,2},?\s+20\d{2}\s+)?"
    r"\(Reuters\)\s*[-–—]|(?:By\s+[^\n]{2,100}\n){0,1}[^\n]{0,160}\bReuters\b)",
    re.I | re.M,
)
_AP_DATELINE_RE = re.compile(
    r"^(?:[A-Z][A-Z .'-]{2,40}\s*\(AP\)\s*[-–—]|"
    r"(?:By\s+)?(?:The\s+)?Associated Press\b)",
    re.I | re.M,
)
_REUTERS_COPYRIGHT_RE = re.compile(r"(?:©|copyright)\s*(?:20\d{2}\s*)?Reuters\b", re.I)
_AP_COPYRIGHT_RE = re.compile(
    r"(?:©|copyright)\s*(?:20\d{2}\s*)?(?:The\s+)?Associated Press\b", re.I
)
_REUTERS_ORIGINAL_RE = re.compile(
    r"(?:originally|first)\s+(?:published|reported)\s+(?:by|in|on)\s+Reuters\b|"
    r"this\s+(?:article|story)\s+was\s+(?:originally\s+)?published\s+by\s+Reuters\b",
    re.I,
)
_AP_ORIGINAL_RE = re.compile(
    r"(?:originally|first)\s+(?:published|reported)\s+(?:by|in|on)\s+"
    r"(?:The\s+)?Associated Press\b|this\s+(?:article|story)\s+was\s+"
    r"(?:originally\s+)?published\s+by\s+(?:The\s+)?Associated Press\b",
    re.I,
)
_NEGATIVE_CONTEXT_RE = re.compile(
    r"(?:designed|design|funded|supported|commissioned|partnered|produced)\s+by\s+"
    r"(?:the\s+)?Thomson Reuters Foundation|"
    r"Thomson Reuters Foundation\s+(?:as|was|is|provided|supported|designed)|"
    r"(?:references?|bibliography|works cited).{0,300}\bReuters\b",
    re.I | re.S,
)


@dataclass(frozen=True, slots=True)
class WireEvidence:
    service: str
    strong: bool
    evidence_type: str
    evidence_excerpt: str
    direct_publisher: bool
    negative_context: bool


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _excerpt(value: str, match: re.Match[str] | None, limit: int = 220) -> str:
    if match is None:
        return ""
    start = max(0, match.start() - 40)
    end = min(len(value), match.end() + 80)
    return re.sub(r"\s+", " ", value[start:end]).strip()[:limit]


def detect_wire_evidence(
    *,
    url: str,
    author: str = "",
    markdown: str = "",
    description: str = "",
) -> WireEvidence:
    domain = _domain(url)
    author_clean = re.sub(r"\s+", " ", author or "").strip()
    lead = "\n".join((description or "", markdown or ""))[:3000]
    sample = "\n".join((author_clean, lead))
    negative = bool(_NEGATIVE_CONTEXT_RE.search(sample))

    if domain == "reuters.com" or domain.endswith(".reuters.com"):
        return WireEvidence("Reuters", True, "direct_publisher_domain", domain, True, negative)
    if domain == "apnews.com" or domain.endswith(".apnews.com"):
        return WireEvidence("AP", True, "direct_publisher_domain", domain, True, negative)

    checks: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
        ("Reuters", "structured_author", _REUTERS_AUTHOR_RE, author_clean),
        ("AP", "structured_author", _AP_AUTHOR_RE, author_clean),
        ("Reuters", "wire_dateline", _REUTERS_DATELINE_RE, lead),
        ("AP", "wire_dateline", _AP_DATELINE_RE, lead),
        ("Reuters", "copyright_notice", _REUTERS_COPYRIGHT_RE, lead),
        ("AP", "copyright_notice", _AP_COPYRIGHT_RE, lead),
        ("Reuters", "explicit_original_statement", _REUTERS_ORIGINAL_RE, lead),
        ("AP", "explicit_original_statement", _AP_ORIGINAL_RE, lead),
    )
    for service, evidence_type, pattern, value in checks:
        match = pattern.search(value)
        if match is None:
            continue
        # A real author/dateline/copyright statement remains strong even if the
        # body later mentions the foundation; generic string matches never enter
        # this function as strong evidence.
        return WireEvidence(
            service,
            True,
            evidence_type,
            _excerpt(value, match),
            False,
            negative,
        )

    mentioned = "Reuters" if re.search(r"\breuters\b", sample, re.I) else (
        "AP" if re.search(r"\b(?:associated press|ap news)\b", sample, re.I) else ""
    )
    return WireEvidence(
        mentioned,
        False,
        "negative_context_only" if negative and mentioned else "no_strong_wire_evidence",
        "",
        False,
        negative,
    )


def evidence_dict(evidence: WireEvidence) -> dict[str, object]:
    return {"version": SOURCE_RELATIONSHIP_VERSION, **asdict(evidence)}


__all__ = [
    "SOURCE_RELATIONSHIP_VERSION",
    "WireEvidence",
    "detect_wire_evidence",
    "evidence_dict",
]
