from longread_collector.native_discovery import parse_section_html


def source(parser_config_json="{}"):
    return {
        "source_id": "caixin",
        "source_name": "财新网",
        "language": "zh",
        "homepage_url": "https://www.caixin.com/",
        "parser_config_json": parser_config_json,
    }


def html(*links):
    return "<html><body>" + "".join(
        f'<a href="{url}">{title}</a>' for url, title in links
    ) + "</body></html>"


def test_default_section_scan_remains_exact_host_only() -> None:
    body = html(
        ("https://www.caixin.com/2026-08-18/100.html", "财新首页同域文章标题"),
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
    )

    items = parse_section_html(
        body,
        source=source(),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert [item.url for item in items] == [
        "https://www.caixin.com/2026-08-18/100.html"
    ]


def test_opt_in_accepts_true_subdomains_of_source_host() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
        ("https://china.caixin.com/2026-08-18/102.html", "财新政经子域文章标题"),
        ("https://international.caixin.com/2026-08-18/103.html", "财新世界子域文章标题"),
        ("https://weekly.caixin.com/2026-08-18/104.html", "财新周刊子域文章标题"),
    )

    items = parse_section_html(
        body,
        source=source('{"section_allow_subdomains":true}'),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert [item.url for item in items] == [
        "https://finance.caixin.com/2026-08-18/101.html",
        "https://china.caixin.com/2026-08-18/102.html",
        "https://international.caixin.com/2026-08-18/103.html",
        "https://weekly.caixin.com/2026-08-18/104.html",
    ]
    assert all(item.discovery_method == "section_scan" for item in items)
    assert all(item.query_or_source == "source:caixin" for item in items)


def test_opt_in_does_not_accept_suffix_lookalike_or_parent_trick() -> None:
    body = html(
        ("https://evilcaixin.com/2026-08-18/201.html", "伪造相似域名文章标题"),
        ("https://caixin.com.evil.example/2026-08-18/202.html", "恶意父域文章标题"),
        ("https://not-caixin.com/2026-08-18/203.html", "其他外部域名文章标题"),
    )

    items = parse_section_html(
        body,
        source=source('{"section_allow_subdomains":true}'),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert items == []


def test_false_or_malformed_opt_in_preserves_exact_host_boundary() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
    )

    for config in (
        '{"section_allow_subdomains":false}',
        "{not-json",
    ):
        items = parse_section_html(
            body,
            source=source(config),
            endpoint="https://www.caixin.com/",
            limit=10,
        )
        assert items == []


def test_relative_same_host_links_are_unchanged() -> None:
    body = html(
        ("/2026-08-18/301.html", "财新相对路径文章标题"),
    )

    items = parse_section_html(
        body,
        source=source('{"section_allow_subdomains":true}'),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert len(items) == 1
    assert items[0].url == "https://www.caixin.com/2026-08-18/301.html"
