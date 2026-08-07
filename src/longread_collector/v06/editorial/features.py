"""Feature extraction for the v0.6 PR-3 Editorial Judge.

The feature layer observes editorial signals.  It does not emit candidate states
or apply portfolio policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from ..contracts import AcquisitionBundle, CanonicalArticle, RunContext


FEATURE_VERSION = "editorial-features-v0.6-pr3"


_REPORTING_RE = re.compile(
    r"(?:记者|記者|采访|採訪|专访|專訪|调查|調查|走访|走訪|实地|實地|受访|受訪|"
    r"现场|現場|告诉记者|告訴記者|向[^。！？\n]{0,24}表示|"
    r"接受[^。！？\n]{0,16}(?:采访|採訪))"
)
_ATTRIBUTION_RE = re.compile(
    r"(?:根据|根據|据[^，。；：\n]{1,24}(?:统计|統計|数据|數據|报告|報告|称|稱|"
    r"表示|指出)|数据显示|數據顯示|报告显示|報告顯示|表示|指出|认为|認為|称|稱|"
    r"告诉|告訴)"
)
_ANALYSIS_RE = re.compile(
    r"(?:为什么|為什麼|为何|為何|如何|意味着|意味著|原因|机制|機制|影响|影響|"
    r"背景|逻辑|邏輯|风险|風險|趋势|趨勢|结构|結構|政策|制度|治理|法律|战略|戰略)"
)
_ARGUMENT_RE = re.compile(
    r"(?:因此|然而|但是|但|换言之|換言之|这意味着|這意味著|关键在于|關鍵在於|"
    r"问题在于|問題在於|由此|事实上|事實上|值得注意|一方面|另一方面|"
    r"归根结底|歸根結底)"
)
_PROMOTION_RE = re.compile(
    r"(?:重磅|盛大|精彩|亮相|启幕|啟幕|欢迎|歡迎|报名|報名|诚邀|誠邀|优惠|優惠|"
    r"新品|首发|首發|推介|展销|展銷|打造|赋能|賦能|助力|成果展示|丰硕成果|"
    r"豐碩成果|圆满|圓滿|再创新高|再創新高|精品|盛宴)"
)
_EVENT_RE = re.compile(
    r"(?:将于|將於|举办|舉辦|开幕|開幕|启幕|啟幕|开班|開班|培训班|培訓班|"
    r"活动|活動|论坛|論壇|峰会|峰會|展会|展會|书展|書展|发布会|發布會|"
    r"启动仪式|啟動儀式|闭幕|閉幕|结业|結業|主宾省|主賓省)"
)
_TRANSCRIPT_RE = re.compile(
    r"(?:央视网消息|央視網消息|焦点访谈|焦點訪談|主持人|解说|解說|画面|畫面|"
    r"同期声|同期聲|节目|節目|时长|時長|视频|視頻)"
)
_GENERIC_RHETORIC_RE = re.compile(
    r"(?:深入学习贯彻|深入學習貫徹|重要讲话精神|重要講話精神|坚持以|堅持以|"
    r"新时代|新時代|高质量发展|高質量發展|凝聚共识|凝聚共識|奋力谱写|"
    r"奮力譜寫|理论武装|理論武裝|大思政课|大思政課|红色文化|紅色文化|"
    r"伟大复兴|偉大復興)"
)
_BOOK_REVIEW_RE = re.compile(
    r"(?:书评|書評|读《|讀《|评《|評《|新书|新書|著作|作者在书中|作者在書中)"
)
_MARKET_TEMPLATE_RE = re.compile(
    r"(?:主力资金|主力資金|净流入|淨流入|净流出|淨流出|偏离值|偏離值|"
    r"估值处于|估值處於|基金持仓|基金持倉|换手率|換手率|股价异动|股價異動|"
    r"涨停|漲停)"
)
_NUMBER_RE = re.compile(
    r"(?<!\w)\d+(?:\.\d+)?\s*(?:%|％|万|萬|亿|億|人|项|項|家|年|月|日|"
    r"小时|小時|公里|元|美元|亿元|億元)?"
)
_LINK_RE = re.compile(r"https?://|\[[^\]]+\]\([^)]+\)")
_QUOTE_RE = re.compile(r"[“「『][^”」』\n]{4,160}[”」』]|(?:^|\n)>\s*")


@dataclass(frozen=True, slots=True)
class EditorialFeatures:
    prose_chars: int
    content_chars: int
    template_chars: int
    paragraph_count: int
    heading_count: int
    quote_count: int
    numeric_fact_count: int
    link_count: int
    attribution_count: int
    reporting_signal_count: int
    analysis_signal_count: int
    argument_signal_count: int
    promotion_signal_count: int
    event_signal_count: int
    transcript_signal_count: int
    generic_rhetoric_count: int
    book_review_signal_count: int
    market_template_signal_count: int
    template_ratio: float
    freshness_age_days: int | None
    title_has_event_signal: bool
    title_has_promotion_signal: bool


def extract_editorial_features(
    context: RunContext,
    article: CanonicalArticle,
    bundle: AcquisitionBundle,
) -> EditorialFeatures:
    body = bundle.body_markdown or bundle.body_text or ""
    title = article.resolved_title or bundle.raw_title or ""
    full_text = f"{title}\n{body}"

    paragraphs = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    headings = [
        line
        for line in body.splitlines()
        if line.lstrip().startswith("#")
    ]

    prose_chars = max(0, int(bundle.prose_length or 0))
    if not prose_chars:
        prose_chars = len(re.sub(r"\s+", "", body))

    content_chars = max(0, int(bundle.content_length or 0))
    if not content_chars:
        content_chars = len(body)

    template_chars = max(0, int(bundle.template_length or 0))
    denominator = prose_chars + template_chars
    template_ratio = template_chars / denominator if denominator else 0.0

    return EditorialFeatures(
        prose_chars=prose_chars,
        content_chars=content_chars,
        template_chars=template_chars,
        paragraph_count=len(paragraphs),
        heading_count=len(headings),
        quote_count=_count(_QUOTE_RE, body),
        numeric_fact_count=_count(_NUMBER_RE, body),
        link_count=_count(_LINK_RE, body),
        attribution_count=_count(_ATTRIBUTION_RE, body),
        reporting_signal_count=_count(_REPORTING_RE, full_text),
        analysis_signal_count=_count(_ANALYSIS_RE, full_text),
        argument_signal_count=_count(_ARGUMENT_RE, body),
        promotion_signal_count=_count(_PROMOTION_RE, full_text),
        event_signal_count=_count(_EVENT_RE, full_text),
        transcript_signal_count=_count(_TRANSCRIPT_RE, full_text),
        generic_rhetoric_count=_count(_GENERIC_RHETORIC_RE, full_text),
        book_review_signal_count=_count(_BOOK_REVIEW_RE, full_text),
        market_template_signal_count=_count(_MARKET_TEMPLATE_RE, full_text),
        template_ratio=template_ratio,
        freshness_age_days=_age_days(context, article.published_at),
        title_has_event_signal=bool(_EVENT_RE.search(title)),
        title_has_promotion_signal=bool(_PROMOTION_RE.search(title)),
    )


def _count(pattern: re.Pattern[str], value: str) -> int:
    return len(pattern.findall(value))


def _age_days(context: RunContext, published_at: str) -> int | None:
    published = _parse_datetime(published_at)
    run_time = _parse_datetime(context.started_at_bj or context.scheduled_at_bj)
    if published is None or run_time is None:
        return None
    return max(0, (run_time.date() - published.date()).days)


def _parse_datetime(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            continue
    return None


__all__ = ["EditorialFeatures", "FEATURE_VERSION", "extract_editorial_features"]
