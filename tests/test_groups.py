from pathlib import Path

import yaml


def test_four_groups_cover_14_queries() -> None:
    path = Path(__file__).parents[1] / "config" / "queries.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    queries = data["queries"]
    expected = {"intl_early": 4, "pre_report": 4, "zh_midday": 3, "zh_evening": 3}
    actual = {group: sum(q.get("group_id") == group for q in queries) for group in expected}
    assert actual == expected
    assert len(queries) == 14
