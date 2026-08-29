from __future__ import annotations

import pytest

from longread_collector.zh_route_shadow_s2b_track_v2 import (
    FIRECRAWL_PRIMARY_RESERVATION,
    FIRECRAWL_TOTAL_CAP,
    NetworkCounter,
    NetworkSafetyCapExceeded,
    decide_canary_status,
    extract_direct_html,
    validate_manifest,
)


def test_direct_html_prefers_article_blocks_and_extracts_metadata() -> None:
    html = """
    <html><head>
      <title>Fallback title</title>
      <meta property="og:title" content="Article title">
      <meta name="author" content="Reporter Name">
      <meta property="article:published_time" content="2026-08-29T10:00:00+08:00">
    </head><body>
      <nav><p>This navigation paragraph is deliberately long and should never be retained.</p></nav>
      <article>
        <h1>Article title</h1>
        <p>第一段正文足够长，用于确认解析器优先保留 article 中的正文内容，而不是页面导航或页脚内容。这里继续补充文字以形成稳定的正文块。</p>
        <p>第二段正文继续提供分析、数据和背景，并且保持为独立段落，验证段落之间会被保留下来以供后续可读正文质量判断。</p>
        <p>第三段正文再次补充足够内容，确保 article 区域超过最小选择阈值。为了测试稳定性，这里重复增加一些结构化叙述和上下文信息。</p>
        <p>第四段正文进一步扩展文章主体，加入事实、机制、行业背景和分析框架，使 article 区域的字符数稳定超过六百字符阈值。</p>
        <p>第五段正文继续扩展，用于避免测试依赖中文字符数边界差异。正文应该被选中，而导航内容必须完全排除。</p>
        <p>第六段正文用于补足长度，并保持文章语义连续。解析器不需要理解语义，但应该正确识别 article 结构中的块级文本。</p>
        <p>第七段正文继续补足长度，验证 HTMLParser 在正常嵌套标签下不会丢失正文。这里还有更多背景、证据和分析描述。</p>
        <p>第八段正文完成测试文章主体。最终结果应该包含这些 article 段落，并且不包含导航区域中的文字。</p>
      </article>
      <footer><p>This footer paragraph is also deliberately long and should be excluded.</p></footer>
    </body></html>
    """
    parsed = extract_direct_html(html, "manifest title")
    assert parsed["title"] == "Article title"
    assert parsed["author"] == "Reporter Name"
    assert parsed["published_at"] == "2026-08-29T10:00:00+08:00"
    assert "第一段正文" in parsed["content"]
    assert "navigation paragraph" not in parsed["content"]
    assert "footer paragraph" not in parsed["content"]


def test_canary_status_ready() -> None:
    rows = [
        {"success": True, "http_status": 200},
        {"success": True, "http_status": 200},
        {"success": False, "http_status": 500},
    ]
    assert decide_canary_status(rows) == "READY"


def test_canary_status_provider_not_ready_on_systemic_402() -> None:
    rows = [
        {"success": False, "http_status": 402},
        {"success": False, "http_status": 402},
        {"success": True, "http_status": 200},
    ]
    assert decide_canary_status(rows) == "PROVIDER_NOT_READY"


def test_canary_status_indeterminate_when_not_enough_success_or_provider_failures() -> None:
    rows = [
        {"success": True, "http_status": 200},
        {"success": False, "http_status": 500},
        {"success": False, "http_status": 500},
    ]
    assert decide_canary_status(rows) == "INDETERMINATE"


def test_paid_fallback_reservations_are_source_bounded_and_total_20() -> None:
    assert FIRECRAWL_PRIMARY_RESERVATION == {"jiemian-depth": 10, "yicai": 10}
    assert sum(FIRECRAWL_PRIMARY_RESERVATION.values()) == FIRECRAWL_TOTAL_CAP == 20


def test_network_counter_fails_before_request_above_cap() -> None:
    counter = NetworkCounter(cap=2)
    counter._before_request()
    counter._before_request()
    with pytest.raises(NetworkSafetyCapExceeded):
        counter._before_request()
    assert counter.total == 2


def test_manifest_validation_fails_closed_on_identity_drift() -> None:
    with pytest.raises(ValueError, match="manifest hash identity mismatch"):
        validate_manifest({"schema_version": "zh-route-shadow-s2b-manifest-v1", "manifest_sha256": "wrong", "items": []})
