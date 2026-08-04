from longread_collector.classification_v056j import classify_candidate_v056j
from longread_collector.content_identity_v056j import evaluate_content_identity


def _classify(title: str, markdown: str):
    return classify_candidate_v056j(
        url="https://example.org/2026/08/04/article.html",
        title=title,
        description="",
        markdown=markdown,
        published_at="2026-08-04",
        verification_level="B",
        content_chars=len(markdown),
    )


def test_client_template_title_is_recovered_from_body_h1() -> None:
    markdown = """# 一组数据读懂我国经济发展向新向优向好背后的底气

我国充电基础设施总数达到2305.7万个。

![Image 1](https://example.org/1.png)
"""
    identity = evaluate_content_identity(
        title="更多资讯请下载央视新闻客户端",
        markdown=markdown,
        external_link="https://content-static.cctvnews.cctv.com/item/1",
    )
    assert identity.resolved_title.startswith("一组数据读懂")
    assert identity.gate_result == "title_recovered_from_body_heading"
    assert identity.external_target_domain == "content-static.cctvnews.cctv.com"


def test_cctv_visual_data_card_is_rejected() -> None:
    markdown = """# 一组数据读懂我国经济发展向新向优向好背后的底气

我国充电基础设施总数达到2305.7万个。
全国规模以上工业企业利润增长18.7%。

![Image 1](https://example.org/1.png)
![Image 2](https://example.org/2.png)
![Image 3](https://example.org/3.png)
![Image 4](https://example.org/4.png)

# 热门推荐
其他内容
"""
    result = _classify("更多资讯请下载央视新闻客户端", markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == "visual_data_card_v056j"


def test_cctv_video_program_is_rejected() -> None:
    markdown = """# 新闻1+1丨中央政治局会议，如何部署下半年？

[Video 1](https://example.org/program.m3u8)

24:19

△视频丨《新闻1+1》完整版
当前非Wi-Fi网络，继续播放将产生流量费用。
建议打开央视新闻观看。

中国财政科学研究院宏观经济中心主任表示，政策取向保持不变。
"""
    result = _classify("更多资讯请下载央视新闻客户端", markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == "video_program_page_v056j"


def test_conference_roundtable_recap_is_rejected() -> None:
    markdown = """# AI浪潮下的传播新格局：变什么，守什么？

7月31日下午，由某报业集团主办的外滩新媒体学术交流开启总编圆桌环节。
圆桌邀请四位嘉宾，主持人提出第一个问题。
甲表示技术带来了变化。乙指出价值导向不能变。丙认为记者抵达现场仍不可替代。
丁介绍了所在媒体的实践，主持人随后提问数据与内容的关系。
""" + "会议嘉宾围绕行业转型继续交流。" * 80
    result = _classify("AI浪潮下的传播新格局：变什么，守什么？", markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == "conference_roundtable_recap_v056j"


def test_site_chrome_does_not_turn_short_wire_into_longform() -> None:
    navigation = "\n".join(["首页", "国际", "财经", "文化", "地方频道"] * 100)
    markdown = f"""{navigation}

# 瑙鲁正式更改国名

新华社悉尼8月3日电，瑙鲁政府宣布恢复传统名称Naoero。
联合国已收到通知，中文名维持不变。
该国陆地面积21.1平方公里，人口约1.3万人。

阅读下一篇：
{navigation}
"""
    identity = evaluate_content_identity(title="瑙鲁正式更改国名-新华网", markdown=markdown)
    assert identity.body_prose_chars < 900
    result = _classify("瑙鲁正式更改国名-新华网", markdown)
    assert result.candidate_disposition == "reject"
    assert result.reason == "short_news_brief_v056j"


def test_reported_longform_remains_a_candidate() -> None:
    markdown = "# 城市更新如何改变普通人的生活？\n\n" + (
        "记者采访了居民、规划师与社区工作者，并核对政策文件和公开数据。" * 180
    )
    result = _classify("城市更新如何改变普通人的生活？一项持续三年的调查", markdown)
    assert result.candidate_disposition == "formal_candidate"
