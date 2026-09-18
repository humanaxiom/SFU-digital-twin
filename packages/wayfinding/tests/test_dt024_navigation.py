"""Actual-client DT-024 navigation regression cases, executed only in Docker."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", [
    "floors", "open", "retry", "scenes", "rooms", "clear_room",
    "assistant_floor", "assistant_latest", "replacement_pending_step", "route",
    "retained_room_loading", "retained_landmark_loading", "clear_scene_error",
    "initial_route_pending",
])
def test_navigation_reliability(case):
    node = shutil.which("node") or str(Path.home() / ".cache/pyright-python/nodeenv/bin/node")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [node, "tests/client/dt024_navigation.cjs", case], cwd=root,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
