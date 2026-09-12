"""Exercise the real client state transitions in the Docker Node runtime."""

import shutil
import subprocess
from pathlib import Path


def test_guidance_client_state():
    node = shutil.which("node") or str(Path.home() / ".cache/pyright-python/nodeenv/bin/node")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [node, "tests/gate/test_guidance_state.cjs"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
