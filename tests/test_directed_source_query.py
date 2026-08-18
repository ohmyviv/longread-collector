from longread_collector.directed_source_query import directed_query_for_source


def source(*, language="en", parser_config_json="{}"):
    return {
        "source_id": "test",
        "language": language,
        "parser_config_json": parser_config_json,
    }


def test_default_english_query_is_unchanged() -> None:
    query, provenance = directed_query_for_source(source())

    assert query == "latest longform investigation analysis"
    assert provenance == "language_default"


def test_default_chinese_query_is_unchanged() -> None:
    query, provenance = directed_query_for_source(source(language="zh"))

    assert query == "最新 深度 调查 分析 长文"
    assert provenance == "language_default"


def test_source_can_override_directed_search_query() -> None:
    query, provenance = directed_query_for_source(
        source(
            parser_config_json='{"directed_search_query":"latest Reuters analysis feature business world technology"}'
        )
    )

    assert query == "latest Reuters analysis feature business world technology"
    assert provenance == "source_override"


def test_override_whitespace_is_normalized() -> None:
    query, provenance = directed_query_for_source(
        source(
            parser_config_json={
                "directed_search_query": "  latest   analysis\nfeature  "
            }
        )
    )

    assert query == "latest analysis feature"
    assert provenance == "source_override"


def test_blank_or_non_string_override_falls_back_to_default() -> None:
    for raw in (
        '{"directed_search_query":"   "}',
        '{"directed_search_query":["bad"]}',
    ):
        query, provenance = directed_query_for_source(
            source(parser_config_json=raw)
        )
        assert query == "latest longform investigation analysis"
        assert provenance == "language_default"


def test_malformed_parser_config_fails_safe_to_default() -> None:
    query, provenance = directed_query_for_source(
        source(parser_config_json="{not-json")
    )

    assert query == "latest longform investigation analysis"
    assert provenance == "language_default"


def test_unknown_language_uses_existing_english_default() -> None:
    query, provenance = directed_query_for_source(source(language="fr"))

    assert query == "latest longform investigation analysis"
    assert provenance == "language_default"
