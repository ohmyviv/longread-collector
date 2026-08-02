"""Separated page-role, source-relationship and disposition policy for v0.5.6 PR-D."""

from __future__ import annotations

import re
from dataclasses import replace
from urllib.parse import urlsplit

from .classification import ClassificationResult, wire_cluster_id
from .classification_v055 import classify_candidate_v055 as _base_classify_candidate
from .source_relationship_v056 import detect_wire_evidence

CLASSIFICATION_VERSION = "collector-v0.5.6d"

_ACADEMIC_DOMAINS = (
    "academic.oup.com",
    "sciencedirect.com",
    "tandfonline.com",
    "onlinelibrary.wiley.com",
    "link.springer.com",
    "journals.sagepub.com",
    "cambridge.org",
    "jstor.org",
    "iopscience.iop.org",
    "frontiersin.org",
    "mdpi.com",
)
_HIGH_QUALITY_MEDIA = (
    "newyorker.com",
    "e360.yale.edu",
    "theatlantic.com",
    "propublica.org",
    "bellingcat.com",
    "quanta magazine.org",
    "quantamagazine.org",
    "restofworld.org",
    "statnews.com",
    "lawfaremedia.org",
    "404media.co",
    "noemamag.com",
)
_ARTICLE_PATH_RE = re.compile(
    r"/(?:article|articles|story|stories|feature|features|analysis|investigation|"
    r"long-read|longread|news|detail|content)/|\.s?html?$",
    re.I,
)
_ACADEMIC_MARKER_RE = re.compile(
    r"\b(?:doi\s*[:/]?|abstract|volume\s+\d+|journal article|systematic review|"
    r"methods?|results?|references?)\b|(?:摘要|关键词|研究方法|研究结果|参考文献)",
    re.I,
)
_PAPER_SUMMARY_RE = re.compile(
    r"\b(?:published in|appears in|journal|doi)\b.{0,180}\b(?:study|paper|article)\b|"
    r"\b(?:study|paper)\b.{0,180}\b(?:published in|journal|doi)\b|"
    r"(?:研究成果|论文).{0,80}(?:发表于|刊登于|期刊|DOI)|"
    r"(?:发表于|刊登于).{0,80}(?:研究|论文)",
    re.I | re.S,
)
_REPORT_RE = re.compile(
    r"\b(?:research report|policy report|official report|white paper|working paper)\b|"
    r"(?:研究报告|政策报告|官方报告|白皮书|工作论文)",
    re.I,
)
_CHAPTER_RE = re.compile(
    r"\b(?:chapter|report chapter)\b|(?:报告章节|第[一二三四五六七八九十\d]+章)",
    re.I,
)
_GUIDANCE_RE = re.compile(
    r"\b(?:guidance|guideline|regulatory framework|regulation|rulemaking|directive)\b|"
    r"(?:指导文件|监管指引|指南|条例|办法|规定|监管框架)",
    re.I,
)
_DATA_RELEASE_RE = re.compile(
    r"\b(?:official data release|survey results?|statistical release|census results?)\b|"
    r"(?:统计公报|调查公报|官方数据|数据发布|普查结果)",
    re.I,
)
_PRIMARY_DOC_RE = re.compile(
    r"\b(?:official statement|testimony|hearing statement|federal register|"
    r"government plan|action plan)\b|(?:政策文件|行动方案|立法说明|立场文件|官方声明)",
    re.I,
)
_RESEARCH_OR_EDU_DOMAIN_RE = re.compile(
    r"(?:^|\.)(?:edu|ac\.uk|edu\.cn)$|(?:university|institute|academy|research)",
    re.I,
)


def _domain(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def _path(url: str) -> str:
    return (urlsplit(url).path or "/").lower()


def _result(
    *,
    page_role: str,
    page_type: str,
    content_type: str,
    disposition: str,
    reason: str,
    special_candidate_type: str = "",
    source_relationship: str = "original",
    original_publisher: str = "",
    wire_service: str = "",
    source_action: str = "none",
    content_cluster_id: str = "",
    confidence: str = "high",
) -> ClassificationResult:
    return ClassificationResult(
        page_role=page_role,
        page_type=page_type,
        content_type=content_type,
        candidate_disposition=disposition,
        special_candidate_type=special_candidate_type,
        source_relationship=source_relationship,
        original_publisher=original_publisher,
        wire_service=wire_service,
        source_action=source_action,
        content_cluster_id=content_cluster_id,
        confidence=confidence,
        reason=reason,
    )


def _is_academic(url: str, sample: str) -> bool:
    domain = _domain(url)
    path = _path(url)
    if domain == "ncbi.nlm.nih.gov" and ("/articles/pmc" in path or "/pmc/" in path):
        return True
    if domain.endswith("nature.com") and "/articles/" in path:
        return True
    if any(domain == item or domain.endswith("." + item) for item in _ACADEMIC_DOMAINS):
        if domain.endswith("frontiersin.org") and "/articles/" not in path:
            return False
        return True
    return path.endswith(".pdf") and bool(_ACADEMIC_MARKER_RE.search(sample[:6000]))


def _special_document_result(url: str, title: str, sample: str) -> ClassificationResult | None:
    domain = _domain(url)
    path = _path(url)
    government = domain.endswith((".gov", ".gov.cn", ".gov.uk", ".europa.eu"))

    if _is_academic(url, sample):
        return _result(
            page_role="standalone_content",
            page_type="academic_paper",
            content_type="academic_paper",
            disposition="special_candidate",
            special_candidate_type="academic_paper",
            reason="academic_paper_special_v056",
        )
    if government and _DATA_RELEASE_RE.search(sample):
        return _result(
            page_role="standalone_content",
            page_type="official_data_release",
            content_type="primary_data",
            disposition="special_candidate",
            special_candidate_type="official_data_release",
            reason="official_data_release_special_v056",
        )
    if government and _GUIDANCE_RE.search(sample):
        return _result(
            page_role="standalone_content",
            page_type="regulatory_guidance",
            content_type="primary_document",
            disposition="special_candidate",
            special_candidate_type="regulatory_guidance",
            reason="regulatory_guidance_special_v056",
        )
    if government and (_PRIMARY_DOC_RE.search(sample) or path.endswith(".pdf")):
        return _result(
            page_role="standalone_content",
            page_type="government_primary_document",
            content_type="primary_document",
            disposition="special_candidate",
            special_candidate_type="government_primary_document",
            reason="government_primary_document_special_v056",
        )
    if domain.endswith(("nationalacademies.org", "nap.nationalacademies.org")) and (
        _CHAPTER_RE.search(sample) or "/read/" in path
    ):
        return _result(
            page_role="standalone_content",
            page_type="report_chapter",
            content_type="reference_or_report_chapter",
            disposition="special_candidate",
            special_candidate_type="report_chapter",
            reason="report_chapter_special_v056",
        )
    if domain.endswith("oecd.org") and (_CHAPTER_RE.search(sample) or "/reports/" in path):
        return _result(
            page_role="standalone_content",
            page_type="report_chapter",
            content_type="institutional_report_chapter",
            disposition="special_candidate",
            special_candidate_type="report_chapter",
            reason="report_chapter_special_v056",
        )
    report_structure = path.endswith(".pdf") or "/reports/" in path or _REPORT_RE.search(sample)
    if report_structure and not re.search(r"\bmarket\s+(?:size|forecast)\b", sample, re.I):
        return _result(
            page_role="standalone_content",
            page_type="institutional_research_report",
            content_type="research_report",
            disposition="special_candidate",
            special_candidate_type="institutional_research_report",
            reason="institutional_research_report_special_v056",
        )
    return None


def _paper_summary_result(url: str, sample: str) -> ClassificationResult | None:
    domain = _domain(url)
    path = _path(url)
    research_context = bool(_RESEARCH_OR_EDU_DOMAIN_RE.search(domain)) or bool(
        re.search(r"/(?:news|research|insights?)/", path, re.I)
    )
    if research_context and _PAPER_SUMMARY_RE.search(sample) and not _is_academic(url, sample):
        return _result(
            page_role="discovery_lead",
            page_type="academic_summary",
            content_type="academic_summary",
            disposition="original_source_required",
            special_candidate_type="academic_source_chase",
            source_relationship="secondary_summary",
            source_action="find_original_article",
            reason="academic_summary_requires_original_v056",
            confidence="medium",
        )
    return None


def _high_quality_original(
    *,
    url: str,
    title: str,
    content_chars: int,
    verification_level: str,
) -> bool:
    domain = _domain(url)
    path = _path(url)
    trusted = any(domain == item or domain.endswith("." + item) for item in _HIGH_QUALITY_MEDIA)
    article_structure = bool(_ARTICLE_PATH_RE.search(path)) or len(
        [part for part in path.split("/") if part]
    ) >= 3
    title_ok = len(title.strip()) >= 18 and not re.search(
        r"\b(?:newsletter|podcast|briefing)\b|(?:简报|播客)", title, re.I
    )
    return (
        trusted
        and article_structure
        and title_ok
        and content_chars >= 1800
        and verification_level in {"A", "B"}
    )


def _classify_without_wire_strings(**kwargs: object) -> ClassificationResult:
    sanitized = dict(kwargs)
    sanitized["author"] = re.sub(
        r"\b(?:Reuters|Associated Press|AP News)\b", "wire source mentioned", str(kwargs.get("author", "")), flags=re.I
    )
    sanitized["markdown"] = re.sub(
        r"\b(?:Reuters|Associated Press|AP News)\b", "wire source mentioned", str(kwargs.get("markdown", "")), flags=re.I
    )
    sanitized["description"] = re.sub(
        r"\b(?:Reuters|Associated Press|AP News)\b", "wire source mentioned", str(kwargs.get("description", "")), flags=re.I
    )
    return _base_classify_candidate(**sanitized)


def classify_candidate_v056(
    *,
    url: str,
    title: str,
    description: str = "",
    author: str = "",
    markdown: str = "",
    published_at: str = "",
    verification_level: str = "",
    content_chars: int = 0,
) -> ClassificationResult:
    sample = " ".join((title, description, author, markdown[:10000])).strip()

    special = _special_document_result(url, title, sample)
    if special is not None:
        return special

    paper_summary = _paper_summary_result(url, sample)
    if paper_summary is not None:
        return paper_summary

    wire = detect_wire_evidence(
        url=url,
        author=author,
        markdown=markdown,
        description=description,
    )
    if wire.strong and not wire.direct_publisher:
        publisher = "Reuters" if wire.service == "Reuters" else "Associated Press"
        service = "Reuters" if wire.service == "Reuters" else "AP"
        return _result(
            page_role="discovery_lead",
            page_type="article",
            content_type="syndicated_wire",
            disposition="original_source_required",
            source_relationship="wire_republish",
            original_publisher=publisher,
            wire_service=service,
            source_action="replace_with_original_source",
            content_cluster_id=wire_cluster_id(service, title),
            reason=f"{service.lower()}_strong_wire_{wire.evidence_type}_v056",
        )

    if wire.direct_publisher:
        if content_chars >= 1200 and verification_level in {"A", "B"}:
            return _result(
                page_role="standalone_content",
                page_type="article",
                content_type="reported_article",
                disposition="formal_candidate",
                source_relationship="original",
                original_publisher="Reuters" if wire.service == "Reuters" else "Associated Press",
                wire_service=wire.service,
                reason="direct_wire_original_article_v056",
            )

    kwargs = {
        "url": url,
        "title": title,
        "description": description,
        "author": author,
        "markdown": markdown,
        "published_at": published_at,
        "verification_level": verification_level,
        "content_chars": content_chars,
    }
    base = _base_classify_candidate(**kwargs)

    false_wire_chase = (
        base.candidate_disposition == "original_source_required"
        and base.original_publisher in {"Reuters", "Associated Press"}
        and not wire.strong
    )
    if false_wire_chase:
        base = _classify_without_wire_strings(**kwargs)
        if base.candidate_disposition == "original_source_required" and base.original_publisher in {
            "Reuters",
            "Associated Press",
        }:
            base = replace(
                base,
                page_role="standalone_content",
                page_type="article",
                content_type="reported_article",
                candidate_disposition="formal_candidate" if content_chars >= 1800 else "reject",
                source_relationship="original",
                original_publisher="",
                wire_service="",
                source_action="none",
                reason=(
                    "wire_mention_not_republish_v056"
                    if content_chars >= 1800
                    else "insufficient_editorial_evidence"
                ),
            )

    if base.candidate_disposition == "reject" and base.reason == "insufficient_editorial_evidence":
        if _high_quality_original(
            url=url,
            title=title,
            content_chars=content_chars,
            verification_level=verification_level,
        ):
            return replace(
                base,
                page_role="standalone_content",
                page_type="article",
                content_type="reported_longread",
                candidate_disposition="formal_candidate",
                source_relationship="original",
                source_action="none",
                confidence="high",
                reason="registered_high_quality_article_structure_v056",
            )

    return base


__all__ = ["CLASSIFICATION_VERSION", "classify_candidate_v056"]
