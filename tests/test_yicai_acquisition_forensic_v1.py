from __future__ import annotations

from longread_collector.yicai_acquisition_forensic_v1 import (
    HARD_HTTP_CAP,
    JINA_MIN_INTERVAL_SECONDS,
    SEED,
    SURFACES,
    THEORETICAL_HTTP_CAP,
    classify_signals,
    manifest_sha256,
    select_manifest,
    www_variant,
)


def _row(surface: str, url: str, title: str = "x") -> dict[str, str]:
    return {
        "source_id": "yicai",
        "sampling_role": "primary_plausible",
        "first_surface": surface,
        "url_canonical": url,
        "title": title,
    }


def _frozen_rows() -> list[dict[str, str]]:
    return [
        _row("yicai_auto", "https://yicai.com/news/103335887.html"),
        _row("yicai_finance", "https://yicai.com/news/103339305.html"),
        _row("yicai_finance", "https://yicai.com/news/103339122.html"),
        _row("yicai_finance", "https://yicai.com/news/103334700.html"),
        _row("yicai_finance", "https://yicai.com/news/103337361.html"),
        _row("yicai_finance", "https://yicai.com/news/103337023.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103336633.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103334779.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103335587.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103336593.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103339108.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103337512.html"),
        _row("yicai_kechuang", "https://yicai.com/news/103336301.html"),
        _row("yicai_news_breadth", "https://yicai.com/news/103337397.html"),
        _row("yicai_news_breadth", "https://yicai.com/news/103337349.html"),
    ]


def test_contract_bounds_are_frozen() -> None:
    assert SEED == "yicai-acquisition-forensic-v1-20260830"
    assert SURFACES == ("yicai_auto", "yicai_finance", "yicai_kechuang", "yicai_news_breadth")
    assert THEORETICAL_HTTP_CAP == 20
    assert HARD_HTTP_CAP == 25
    assert JINA_MIN_INTERVAL_SECONDS >= 3.1


def test_exact_deterministic_manifest() -> None:
    manifest = select_manifest(_frozen_rows())
    assert [(item.first_surface, item.canonical_url) for item in manifest] == [
        ("yicai_auto", "https://yicai.com/news/103335887.html"),
        ("yicai_finance", "https://yicai.com/news/103337023.html"),
        ("yicai_kechuang", "https://yicai.com/news/103335587.html"),
        ("yicai_news_breadth", "https://yicai.com/news/103337397.html"),
    ]
    assert len(manifest_sha256(manifest)) == 64


def test_www_variant_changes_only_host() -> None:
    assert www_variant("https://yicai.com/news/123.html") == "https://www.yicai.com/news/123.html"


def test_signal_classification() -> None:
    rows = []
    for _ in range(4):
        rows.append({"probes": {
            "direct_canonical": {"status": "error"},
            "direct_www": {"status": "response", "http_status": 200},
            "jina_canonical": {"status": "response", "http_status": 422},
            "jina_www": {"status": "response", "http_status": 200},
            "firecrawl": {"status": "response", "http_status": 500},
        }})
    signals = classify_signals(rows)
    assert "HOST_IDENTITY_EXPLAINS_DIRECT_FAILURE" in signals
    assert "JINA_HOST_NORMALIZATION_SIGNAL" in signals
    assert "FIRECRAWL_PROVIDER_INSTABILITY_SIGNAL" in signals
