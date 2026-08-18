from datetime import datetime

from longread_collector.pipeline import build_directed_source_queries


def test_build_directed_query_uses_source_override_without_changing_contract() -> None:
    source = {
        "source_id": "reuters-special",
        "source_name": "Reuters Special Reports",
        "language": "en",
        "homepage_url": "https://www.reuters.com/investigates/",
        "parser_config_json": (
            '{"directed_search_query":"latest Reuters analysis feature business world technology"}'
        ),
    }

    queries = build_directed_source_queries(
        [source],
        group_id="intl_early",
        started=datetime(2026, 8, 17, 22, 52),
        max_sources=1,
        result_limit=4,
        freshness="qdr:d3",
    )

    assert len(queries) == 1
    query = queries[0]
    assert query["query_id"] == "source:reuters-special"
    assert query["query"] == "latest Reuters analysis feature business world technology"
    assert query["directed_query_provenance"] == "source_override"
    assert query["include_domains"] == ["reuters.com"]
    assert query["purpose"] == "directed_source_scan"
    assert query["limit"] == 4
    assert query["tbs"] == "qdr:d3"
    assert query["group_id"] == "intl_early"


def test_build_directed_query_without_override_preserves_legacy_default() -> None:
    source = {
        "source_id": "default-source",
        "source_name": "Default",
        "language": "en",
        "homepage_url": "https://example.com/",
        "parser_config_json": "{}",
    }

    query = build_directed_source_queries(
        [source],
        group_id="pre_report",
        started=datetime(2026, 8, 18, 4, 0),
        max_sources=1,
        result_limit=4,
        freshness="qdr:d3",
    )[0]

    assert query["query"] == "latest longform investigation analysis"
    assert query["directed_query_provenance"] == "language_default"
    assert query["include_domains"] == ["example.com"]
