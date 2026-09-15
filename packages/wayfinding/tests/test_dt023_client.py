"""Campus client state tests run against the actual JavaScript inside Docker."""

import shutil
import subprocess
from pathlib import Path


def test_campus_context_state():
    node = shutil.which("node") or str(Path.home() / ".cache/pyright-python/nodeenv/bin/node")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [node, "tests/client/dt023_campus.cjs"], cwd=root,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
