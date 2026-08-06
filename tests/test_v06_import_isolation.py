import subprocess
import sys


def test_importing_v06_does_not_import_legacy_pipeline_modules() -> None:
    code = """
import sys
import longread_collector.v06
legacy = sorted(
    name for name in sys.modules
    if name.startswith("longread_collector.pipeline")
    or name.startswith("longread_collector.classification_v056")
    or name == "longread_collector.models"
    or name.startswith("longread_collector.v06.legacy")
)
assert legacy == [], legacy
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_explicit_legacy_adapter_import_loads_only_compatibility_dependencies() -> None:
    code = """
import sys
from longread_collector.v06.legacy import LegacyV056mAdapter
assert LegacyV056mAdapter is not None
assert "longread_collector.models" in sys.modules
assert not any(name.startswith("longread_collector.pipeline") for name in sys.modules)
assert not any(name.startswith("longread_collector.classification_v056") for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
