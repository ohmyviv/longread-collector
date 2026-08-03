import pytest

from longread_collector.classification_v056i import classify_candidate_v056i

LONG_BODY = "独立报道包含采访、数据、背景和分析。" * 700


def _classify(title: str, markdown: str = LONG_BODY):
    return classify_candidate_v056i(
        url="https://example.org/2026/08/03/article.html",
        title=title,
        description="",
        markdown=markdown,
        published_at="2026-08-03",
        verification_level="B",
        content_chars=len(markdown),
    )


@pytest.mark.parametrize(
    ("title", "markdown", "reason"),
    [
        (
            "长篇叙事史诗《麦芒》作者王德清推出传统文化题材六大力作 丹青叙古今 词韵展华章",
            "王德清坚持扎根生活、潜心耕耘，持续拓宽文学表达边界，作品兼具思想深度与情感温度。" * 120,
            "promotional_author_or_book_launch_v056i",
        ),
        (
            "今年以来全国共新开国际航空货运航线超100条",
            "有关部门发布最新数据，介绍航线数量。" * 200,
            "single_statistic_news_brief_v056i",
        ),
        (
            "两部门联合发布橙色地质灾害气象风险预警",
            "有关部门提醒公众注意防范风险。" * 200,
            "operational_public_alert_v056i",
        ),
    ],
)
def test_real_zh_evening_false_accepts_are_rejected(
    title: str,
    markdown: str,
    reason: str,
) -> None:
    result = _classify(title, markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == reason


@pytest.mark.parametrize(
    "title",
    [
        "兼具知识性与思想性的文学阅读之旅——评长篇小说《高仿》",
        "ChinaJoy 2026观察：消费电子产业链的逆周期窗口",
        "田轩：金融如何赋能新质生产力培育？",
        "今年以来航空货运航线增长为何加速？产业链调查",
        "地质灾害预警制度为何失灵？一场持续三年的调查",
    ],
)
def test_reported_analysis_guards_remain_candidates(title: str) -> None:
    result = _classify(title)
    assert result.candidate_disposition == "formal_candidate"
