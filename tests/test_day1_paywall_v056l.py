from __future__ import annotations

from longread_collector.classification_v056l import classify_candidate_v056l


def _template_tail() -> str:
    return "\n\n".join(
        f"Recommended article {index}. According to editors, this unrelated story "
        "contains analysis, reporting, research and a named author."
        for index in range(80)
    )


def test_in_content_paywall_is_not_rescued_by_template_length() -> None:
    markdown = (
        "# The Man Who Was Kidnapped Twice\n\n"
        "Thousands of people have been held for ransom.\n\n"
        "By Alexis Okeowo\n\nAugust 3, 2026\n\n"
        "Your window is closing.\n\n"
        "Don’t lose these views. Get full access for 50¢ per week.\n\n"
        "Already a subscriber? Sign In\n\n"
        "Unlock this story. PAYWALL_IN_CONTENT_BARRIER\n\n"
        + _template_tail()
    )
    result = classify_candidate_v056l(
        url="https://www.newyorker.com/magazine/2026/08/10/the-man-who-was-kidnapped-twice",
        title="The Man Who Was Kidnapped Twice",
        markdown=markdown,
        published_at="2026-08-03",
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.page_type == "article"
    assert result.content_type == "paywalled_excerpt"


def test_poem_page_uses_poetry_page_type_before_paywall_gate() -> None:
    markdown = (
        "[Poems](https://www.newyorker.com/magazine/poems)\n\n"
        "# wasps\n\nBy Jan Wagner\n\nAugust 3, 2026\n\n"
        "Your window is closing. Unlock this story."
    )
    result = classify_candidate_v056l(
        url="https://www.newyorker.com/magazine/2026/08/10/wasps-jan-wagner-poem",
        title="wasps",
        markdown=markdown,
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.page_type == "poetry"
    assert result.content_type == "poem"
