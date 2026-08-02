from __future__ import annotations

from longread_collector.registry_matching_v056 import (
    match_registry,
    registrable_domain,
)


def test_registrable_domain_collapses_mobile_and_www_hosts() -> None:
    assert registrable_domain("https://m.bjnews.com.cn/detail/123.html") == "bjnews.com.cn"
    assert registrable_domain("https://www.bjnews.com.cn/") == "bjnews.com.cn"


def test_registry_match_uses_domain_when_source_labels_differ() -> None:
    final_row = {
        "final_source": "新京报",
        "final_url_canonical": "https://m.bjnews.com.cn/detail/123.html",
    }
    source_row = {
        "source_id": "bjnews-depth",
        "source_name": "新京报·深度",
        "homepage_url": "https://www.bjnews.com.cn/",
        "rss_url": "",
        "sitemap_url": "",
        "news_sitemap_url": "",
        "newsletter_url": "",
    }
    assert match_registry(final_row, [source_row]) is source_row
