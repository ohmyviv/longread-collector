from __future__ import annotations

from longread_collector.classification_v056m import classify_candidate_v056m
from longread_collector.content_identity_v056j import evaluate_content_identity
from longread_collector.direct_html_v056m import parse_direct_html_v056m


def test_focused_investigative_followup_is_formal() -> None:
    title = "暗访医保套现乱象后续：多地已展开专项核查"
    markdown = f"""# {title}

报道刊发后，广州、贵阳两地医保部门迅速响应，联合当地市场监管、公安等部门展开调查。

新京报讯（记者齐少乾）此前调查报道曝光多地存在医保套现灰色产业链。记者暗访发现，有机构通过串换项目、亲情账户和虚假结算等方式套取医保基金，相关线索涉及多个经营主体。

广州：将与市场监管、公安等部门协同跟进

针对报道中反映的线索，广州市医疗保障局相关负责人向记者表示，已紧急召开研讨会议，并抵达现场附近展开排查，后续将与市场监管、公安等部门协同调查。

贵阳：已抽调十余人进行专项核查

贵阳市医疗保障局抽调十余人组成专项核查队伍，联合市场监督管理部门，对报道涉及的机构开展调查。工作人员表示，核查结束后将依法公布处理结果。

记者同时致电另一地医疗保障部门核实和采访，工作人员表示已将问题上报有关部门。截至发稿，相关调查仍在继续。
"""
    result = classify_candidate_v056m(
        url="https://example.com/investigation-followup",
        title=title,
        markdown=markdown,
        published_at="2026-07-30 20:23",
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "formal_candidate"
    assert result.content_type == "reported_investigative_followup"
    assert result.source_relationship == "original"
    assert result.reason == "focused_investigative_followup_v056m"


def test_generic_short_department_response_remains_rejected() -> None:
    title = "有关部门回应网络传言"
    markdown = f"""# {title}

某部门工作人员表示，已关注网上相关信息，将按照程序核实情况。

有关负责人介绍，目前暂无更多可以发布的内容，后续如有进展将及时通报。
"""
    result = classify_candidate_v056m(
        url="https://example.com/brief-response",
        title=title,
        markdown=markdown,
        published_at="2026-08-06",
        verification_level="B",
        content_chars=len(markdown),
    )
    assert result.candidate_disposition == "reject"
    assert result.reason != "focused_investigative_followup_v056m"


def test_semantic_html_injects_title_before_later_live_heading() -> None:
    title = "专访研究者：一项重要调查的完整经过"
    body = "".join(
        f"<p>第{i}段。记者采访多位研究者，数据显示该事件涉及长期变化、监管回应和不同解释，需要结合证据进行分析。</p>"
        for i in range(18)
    )
    html = (
        f'<meta property="og:title" content="{title}">'
        f"<main>{body}<h2>我要评论</h2><h2>相关推荐</h2><h1>直播</h1></main>"
    )
    data = parse_direct_html_v056m(html, url="https://example.com/article")
    markdown = str(data["markdown"])
    identity = evaluate_content_identity(title=title, markdown=markdown)
    assert markdown.startswith(f"# {title}\n\n")
    assert identity.title_similarity == 1.0
    assert identity.body_prose_chars > 1200
