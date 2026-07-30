from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from longread_collector.classification import classify_candidate

FIXTURE = Path(__file__).parent / "fixtures" / "collector_ground_truth_20260729.csv"


def load_rows() -> list[dict[str, str]]:
    with FIXTURE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_ground_truth_fixture_is_complete_and_unique() -> None:
    rows = load_rows()
    assert len(rows) == 48
    assert [int(row["review_index"]) for row in rows] == list(range(1, 49))
    assert len({row["article_id"] for row in rows}) == 48


def test_ground_truth_disposition_distribution() -> None:
    counts = Counter(row["disposition"] for row in load_rows())
    assert counts == {
        "reject": 32,
        "original_source_required": 7,
        "special_candidate": 5,
        "formal_candidate": 4,
    }


def test_v03_baseline_is_recorded_without_redefining_editorial_quality() -> None:
    rows = load_rows()
    machine_eligible = [
        row for row in rows if row["machine_eligible_before"].lower() == "true"
    ]
    retained_value = {
        "formal_candidate",
        "special_candidate",
        "original_source_required",
    }
    useful = [row for row in machine_eligible if row["disposition"] in retained_value]
    assert len(machine_eligible) == 16
    assert len(useful) == 8


def test_ap_clean_energy_rows_share_one_wire_cluster() -> None:
    rows = {
        int(row["review_index"]): row
        for row in load_rows()
        if int(row["review_index"]) in {21, 46, 48}
    }
    assert set(rows) == {21, 46, 48}
    assert {row["wire_service"] for row in rows.values()} == {"AP"}
    fixture_clusters = {row["content_cluster_id"] for row in rows.values()}
    assert len(fixture_clusters) == 1
    assert "" not in fixture_clusters
    assert {row["duplicate_type"] for row in rows.values()} == {
        "cross_site_same_wire"
    }


def test_hard_non_content_never_becomes_formal_candidate() -> None:
    cases = [
        {
            "url": "https://jobs.example.com/job/123",
            "title": "Manager, Medical Writing Publications",
        },
        {
            "url": "https://example.com/login?returnUrl=/article/1",
            "title": "Sign in",
        },
        {
            "url": "https://example.com/",
            "title": "Example company homepage",
        },
        {
            "url": "https://example.com/tag/climate",
            "title": "Climate stories",
        },
        {
            "url": "https://agency.gov/wpforms/tmp/adult-tools.pdf",
            "title": "Best AI Porn Video Tools",
        },
    ]
    for case in cases:
        result = classify_candidate(**case)
        assert result.candidate_disposition == "reject"
        assert result.eligible_for_editor is False


def test_social_investigation_is_a_lead_not_a_candidate() -> None:
    result = classify_candidate(
        url="https://instagram.com/p/example",
        title="A new investigation",
        description=(
            "A new investigation from ProPublica and Drilled examines the "
            "infrastructure, land and storage behind the proposal."
        ),
    )
    assert result.page_role == "discovery_lead"
    assert result.candidate_disposition == "original_source_required"
    assert result.source_action == "find_original_article"
    assert result.eligible_for_editor is False


def test_secondary_reuters_story_triggers_source_chase() -> None:
    result = classify_candidate(
        url="https://secondary.example/reuters-editor-speech",
        title="Reuters editor warns AI threatens journalism's future",
        description="Reuters editor Alessandra Galloni said in a public lecture...",
    )
    assert result.candidate_disposition == "original_source_required"
    assert result.original_publisher == "Reuters"
    assert result.source_action == "replace_with_original_source"


def test_wire_republishes_cluster_before_domain_diversity_is_counted() -> None:
    titles = [
        "Trump administration admits it canceled clean energy grants based on politics | Fortune",
        "Trump administration admits grants for clean energy were canceled based on politics – VernonReporter",
        "Trump administration admits grants for clean energy were canceled based on politics",
    ]
    clusters = {
        classify_candidate(
            url=f"https://host-{index}.example/story",
            title=title,
            author="Associated Press",
        ).content_cluster_id
        for index, title in enumerate(titles)
    }
    assert len(clusters) == 1
    cluster = next(iter(clusters))
    assert cluster.startswith("wire-ap-")


def test_academic_and_primary_documents_use_special_pool() -> None:
    academic = classify_candidate(
        url="https://journals.sagepub.com/doi/10.1177/example",
        title="Putting Action in Climate Action Plans",
        verification_level="B",
        content_chars=10000,
    )
    manifesto = classify_candidate(
        url="https://assets.example.org/Green_Party_Manifesto_2026.pdf",
        title="Green Party Manifesto 2026",
        published_at="2026-07-26",
    )
    assert academic.candidate_disposition == "special_candidate"
    assert academic.special_candidate_type == "academic"
    assert manifesto.candidate_disposition == "special_candidate"
    assert manifesto.special_candidate_type == "primary_document"


def test_labeled_translation_can_remain_formal_with_relationship() -> None:
    result = classify_candidate(
        url="https://nawaat.org/example",
        title="Tunisia-EU: The Hidden Cost of Energy Concessions",
        markdown="English version. Translated by the Nawaat editorial team.",
        verification_level="A",
        content_chars=12000,
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.content_type == "translated_republish"
    assert result.source_relationship == "translated_republish"
    assert result.duplicate_type == "translated_version"
