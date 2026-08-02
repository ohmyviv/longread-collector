from __future__ import annotations

from longread_collector.models import DiscoveredURL
from longread_collector.page_gate_policy_v056 import evaluate_page_gate_policy
from longread_collector.prefilter_v056c import filter_discovered


def item(url: str, title: str, description: str = "") -> DiscoveredURL:
    return DiscoveredURL(
        url=url,
        title=title,
        description=description,
        published_at="2026-08-01",
        discovery_method="firecrawl_search",
    )


def test_press_release_path_is_cross_domain_gate() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.unep.org/news-and-stories/press-release/new-report-infrastructure-climate",
            "New report reveals how infrastructure defines our climate",
        )
    )
    assert decision.reject_reason == "press_release"
    assert decision.page_type == "press_release"


def test_commerce_buying_guide_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.wired.com/gallery/best-organic-mattresses/",
            "Best Organic Mattresses (2026)",
            "We tested the best mattresses and may earn a commission.",
        )
    )
    assert decision.reject_reason == "commerce_or_buying_guide"


def test_essay_farm_is_rejected_without_broad_education_block() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://domyessay.com/blog/history-essay-topics",
            "280+ History Essay Topics",
        )
    )
    assert decision.reject_reason == "seo_essay_farm"


def test_institution_profile_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.tsinghua.edu.cn/centers/public-economics",
            "公共经济、金融与治理研究中心",
        )
    )
    assert decision.reject_reason == "institution_profile"


def test_resource_database_index_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://libguides.example.edu/public-policy/databases",
            "Journal articles – databases",
        )
    )
    assert decision.reject_reason == "database_or_resource_index"


def test_public_notice_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://caijing.com.cn/2026/07/notice.html",
            "关于推荐参评第36届中国新闻奖作品的公示",
        )
    )
    assert decision.reject_reason == "award_or_public_notice"


def test_podcast_page_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.theguardian.com/environment/audio/2026/aug/01/rewilding-podcast",
            "Can a pioneering project show that rewilding really works? – podcast",
        )
    )
    assert decision.reject_reason == "podcast_page"


def test_course_or_program_page_is_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.sarahlawrence.edu/undergraduate/areas-of-study/public-policy/",
            "Public Policy - Sarah Lawrence College",
        )
    )
    assert decision.reject_reason == "course_or_program_page"


def test_category_page_with_generic_title_is_rejected() -> None:
    decision = evaluate_page_gate_policy(item("https://www.cnfin.com/hg/", "宏观经济"))
    assert decision.reject_reason == "category_or_channel_page"


def test_academic_paper_is_not_rejected_by_education_domain() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://academic.oup.com/journal/article/42/1/100/123456",
            "Climate-smart infrastructure in the United States",
        )
    )
    assert decision.rejected is False


def test_government_guidance_pdf_is_not_rejected() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://privacy.gov.example/guidance/artificial-intelligence-and-privacy.pdf",
            "Artificial Intelligence and Privacy – Issues and Challenges",
        )
    )
    assert decision.rejected is False


def test_think_tank_report_is_not_mistaken_for_project_landing() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://www.oecd.org/reports/digital-government-journey-2026.html",
            "How artificial intelligence is accelerating the digital government journey",
            "A full analytical chapter with evidence and policy recommendations.",
        )
    )
    assert decision.rejected is False


def test_reported_article_mentioning_conference_is_not_event_gate() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://news.example.com/2026/08/01/investigation.html",
            "How the climate conference reshaped local politics",
            "A reported investigation based on interviews; no registration or event agenda.",
        )
    )
    assert decision.rejected is False


def test_article_path_guards_program_word_false_positive() -> None:
    decision = evaluate_page_gate_policy(
        item(
            "https://news.example.com/articles/2026/08/01/degree-program-investigation.html",
            "Investigation finds failures in a university degree program",
        )
    )
    assert decision.rejected is False
    assert decision.evidence == "article_path_guard"


def test_prefilter_removes_non_articles_before_capacity_selection() -> None:
    bad = [
        item(
            "https://www.unep.org/press-release/report.html",
            "New report reveals infrastructure risks",
        ),
        item(
            "https://domyessay.com/blog/essay-topics",
            "280+ History Essay Topics",
        ),
        item(
            "https://www.wired.com/gallery/best-organic-mattresses/",
            "Best Organic Mattresses (2026)",
        ),
    ]
    good = item(
        "https://reporting.example.org/articles/2026/08/01/water-investigation.html",
        "Investigation reveals failures in the water market",
        "A long reported feature based on interviews and public records.",
    )
    accepted, rejected = filter_discovered([*bad, good], max_urls=4)
    assert [entry.url for entry in accepted] == [good.url]
    assert {entry["reason"] for entry in rejected} == {
        "press_release",
        "seo_essay_farm",
        "commerce_or_buying_guide",
    }
    for rejected_item in bad:
        assert rejected_item.metadata["selection"]["selection_status"] == "page_gate_reject"
        assert rejected_item.metadata["page_gate"]["page_type"] != "article_or_document"
