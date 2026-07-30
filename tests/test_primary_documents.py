from __future__ import annotations

from longread_collector.classification import classify_candidate


def test_spaced_old_government_work_report_is_rejected_as_stale_document() -> None:
    result = classify_candidate(
        url="https://district.gov.cn/openness/Content/123.html",
        title="政 府 工 作 报 告-区人民政府",
        published_at="2022-01-05",
        markdown="公共服务、就业、医疗保险和社会保障体系。" * 300,
        verification_level="B",
        content_chars=12000,
    )
    assert result.page_type == "document"
    assert result.content_type == "primary_document"
    assert result.candidate_disposition == "reject"
    assert result.reason == "stale_primary_document"
