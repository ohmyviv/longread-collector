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


def test_explicit_allowlist_accepts_only_named_first_party_subdomains() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
        ("https://china.caixin.com/2026-08-18/102.html", "财新政经子域文章标题"),
        ("https://international.caixin.com/2026-08-18/103.html", "财新世界子域文章标题"),
        ("https://weekly.caixin.com/2026-08-18/104.html", "财新周刊子域文章标题"),
        ("https://blog.caixin.com/2026-08-18/105.html", "财新博客未授权子域标题"),
    )
    config = (
        '{"section_allowed_subdomains":['
        '"finance.caixin.com","china.caixin.com",'
        '"international.caixin.com","weekly.caixin.com"]}'
    )

    items = parse_section_html(
        body,
        source=source(config),
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


def test_pipe_delimited_allowlist_is_supported_for_config_ergonomics() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
        ("https://china.caixin.com/2026-08-18/102.html", "财新政经子域文章标题"),
        ("https://blog.caixin.com/2026-08-18/105.html", "财新博客未授权子域标题"),
    )

    items = parse_section_html(
        body,
        source=source(
            '{"section_allowed_subdomains":"finance.caixin.com|china.caixin.com"}'
        ),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert [item.url for item in items] == [
        "https://finance.caixin.com/2026-08-18/101.html",
        "https://china.caixin.com/2026-08-18/102.html",
    ]


def test_allowlist_cannot_escape_the_registered_first_party_domain() -> None:
    body = html(
        ("https://evilcaixin.com/2026-08-18/201.html", "伪造相似域名文章标题"),
        ("https://caixin.com.evil.example/2026-08-18/202.html", "恶意父域文章标题"),
        ("https://evil.example/2026-08-18/203.html", "显式配置外部域名文章标题"),
    )
    config = (
        '{"section_allowed_subdomains":['
        '"evilcaixin.com","caixin.com.evil.example","evil.example"]}'
    )

    items = parse_section_html(
        body,
        source=source(config),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert items == []


def test_unlisted_first_party_subdomain_remains_blocked() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
        ("https://blog.caixin.com/2026-08-18/105.html", "财新博客未授权子域标题"),
    )

    items = parse_section_html(
        body,
        source=source(
            '{"section_allowed_subdomains":["finance.caixin.com"]}'
        ),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert [item.url for item in items] == [
        "https://finance.caixin.com/2026-08-18/101.html"
    ]


def test_malformed_allowlist_preserves_exact_host_boundary() -> None:
    body = html(
        ("https://finance.caixin.com/2026-08-18/101.html", "财新金融子域文章标题"),
    )

    for config in (
        '{"section_allowed_subdomains":true}',
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
        source=source(
            '{"section_allowed_subdomains":["finance.caixin.com"]}'
        ),
        endpoint="https://www.caixin.com/",
        limit=10,
    )

    assert len(items) == 1
    assert items[0].url == "https://www.caixin.com/2026-08-18/301.html"
