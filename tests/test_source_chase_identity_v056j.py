from longread_collector.models import ExtractedArticle
from longread_collector.source_chase_identity_v056j import (
    evaluate_source_chase_identity,
    reject_source_chase_mismatch,
)


def _article(
    article_id: str,
    title: str,
    domain: str,
    *,
    disposition: str,
    published_at: str = "2026-08-03",
) -> ExtractedArticle:
    return ExtractedArticle(
        article_id=article_id,
        url=f"https://{domain}/article",
        url_canonical=f"https://{domain}/article",
        domain=domain,
        title=title,
        published_at=published_at,
        candidate_disposition=disposition,
        classification_version="test",
        extraction_status="success",
        verification_level="B",
        content_markdown="正文" * 1000,
        content_chars=2000,
        eligible_for_editor=disposition == "formal_candidate",
    )


def test_domain_match_alone_cannot_resolve_unrelated_article() -> None:
    parent = _article(
        "seed",
        "美国经济“不可能三角”矛盾交织冲击世界",
        "cn.chinadaily.com.cn",
        disposition="original_source_required",
    )
    chased = _article(
        "wrong",
        "瑙鲁正式更改国名",
        "xinhuanet.com",
        disposition="formal_candidate",
    )
    result = evaluate_source_chase_identity(
        parent=parent,
        chased=chased,
        included_domains={"xinhuanet.com"},
    )
    assert result.domain_match is True
    assert result.matched is False
    assert result.result == "semantic_title_mismatch"


def test_matching_original_title_is_resolved() -> None:
    parent = _article(
        "seed",
        "美国经济“不可能三角”矛盾交织冲击世界",
        "cn.chinadaily.com.cn",
        disposition="original_source_required",
    )
    chased = _article(
        "match",
        "新闻分析丨美国经济“不可能三角”矛盾交织冲击世界",
        "xinhuanet.com",
        disposition="formal_candidate",
    )
    result = evaluate_source_chase_identity(
        parent=parent,
        chased=chased,
        included_domains={"xinhuanet.com"},
    )
    assert result.matched is True
    assert result.title_similarity >= 0.62


def test_mismatched_chase_result_is_removed_from_candidate_pool() -> None:
    parent = _article(
        "seed",
        "美国经济“不可能三角”矛盾交织冲击世界",
        "cn.chinadaily.com.cn",
        disposition="original_source_required",
    )
    chased = _article(
        "wrong",
        "瑙鲁正式更改国名",
        "xinhuanet.com",
        disposition="formal_candidate",
    )
    identity = evaluate_source_chase_identity(
        parent=parent,
        chased=chased,
        included_domains={"xinhuanet.com"},
    )
    reject_source_chase_mismatch(chased, identity)
    assert chased.candidate_disposition == "reject"
    assert chased.eligible_for_editor is False
    assert chased.classification_reason == "source_chase_identity_mismatch_v056j"
    assert chased.metadata["source_chase_identity"]["result"] == "semantic_title_mismatch"
