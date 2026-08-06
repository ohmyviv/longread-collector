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
