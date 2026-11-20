"""Actual-client DT-024 navigation regression cases, executed only in Docker."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", [
    "edits_require_preview", "assistant_drafts_exact_ids",
    "assistant_requires_unambiguous_ids", "map_room_actions_preserve_inspection",
    "preview_commits_snapshot_after_draft_edits", "failed_replacement_preserves_committed_route",
    "latest_preview_wins", "clear_cancels_preview", "preview_checks_known_outcomes",
    "preview_uses_matching_options_after_draft_edit", "malformed_success_preserves_committed_route",
    "qualified_success_replaces_committed_route",
    "floors", "open", "retry", "scenes", "rooms", "clear_room",
    "assistant_floor", "assistant_latest", "replacement_pending_step", "route",
    "retained_room_loading", "retained_landmark_loading", "clear_scene_error",
    "initial_route_pending", "delayed_availability", "delayed_availability_failure",
    "availability_clear_reselect", "availability_latest_destination", "route_cancels_old_step",
    "unsupported_during_route", "unsupported_after_wait", "availability_newer_room",
    "room_accessibility_true", "room_accessibility_false", "room_accessibility_unknown",
])
def test_navigation_reliability(case):
    node = shutil.which("node") or str(Path.home() / ".cache/pyright-python/nodeenv/bin/node")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [node, "tests/client/dt024_navigation.cjs", case], cwd=root,
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS DT024 {case}" in result.stdout, result.stdout + result.stderr
