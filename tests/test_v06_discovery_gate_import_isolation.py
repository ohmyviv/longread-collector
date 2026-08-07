import subprocess
import sys


def test_importing_v06_discovery_and_gates_does_not_load_pipeline_modules():
    code = """
import sys
import longread_collector.v06.discovery
import longread_collector.v06.gates
legacy_pipeline = sorted(
    name for name in sys.modules
    if name.startswith("longread_collector.pipeline")
    or name.startswith("longread_collector.prefilter")
    or name.startswith("longread_collector.page_gate_policy")
)
assert legacy_pipeline == [], legacy_pipeline
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
