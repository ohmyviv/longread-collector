from longread_collector.normalization import canonicalize_url, stable_id


def test_canonicalize_url_removes_tracking_and_fragment():
    value = canonicalize_url("https://www.Example.com/a/?utm_source=x&b=2#section")
    assert value == "https://example.com/a?b=2"


def test_stable_id_is_deterministic():
    assert stable_id("https://example.com/a") == stable_id("https://example.com/a")
