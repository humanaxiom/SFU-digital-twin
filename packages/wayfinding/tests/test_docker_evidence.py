"""Container-only contracts for takeover evidence capture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = WORKSPACE_ROOT / "tools" / "capture_takeover_evidence.py"
WRAPPER_PATH = WORKSPACE_ROOT / "tools" / "capture-takeover-evidence.ps1"


def _capture_module():
    spec = importlib.util.spec_from_file_location("capture_takeover_evidence", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capture_hashes_files_and_artifacts_inside_workspace(tmp_path):
    capture = _capture_module()
    build = tmp_path / "build"
    build.mkdir()
    (tmp_path / "changed.txt").write_bytes(b"changed")
    (build / "wayfinding.gpkg").write_bytes(b"gpkg")
    (build / "graph_contracted.pkl").write_bytes(b"graph")
    (build / "graph_contracted_stats.json").write_bytes(b"stats")
    output = build / "takeover-state.json"

    capture.write_manifest(
        head="abc123",
        statuses=[" M changed.txt", "?? new.txt"],
        paths=["changed.txt", "new.txt"],
        workspace=tmp_path,
        output=output,
    )

    state = json.loads(output.read_text(encoding="utf-8"))
    assert state["head"] == "abc123"
    assert state["status"] == [" M changed.txt", "?? new.txt"]
    assert state["files"] == [
        {"path": "changed.txt", "sha256": hashlib.sha256(b"changed").hexdigest()},
        {"path": "new.txt", "sha256": None},
    ]
    assert state["artifacts"] == [
        {"name": name, "sha256": hashlib.sha256(content).hexdigest()}
        for name, content in (
            ("wayfinding.gpkg", b"gpkg"),
            ("graph_contracted.pkl", b"graph"),
            ("graph_contracted_stats.json", b"stats"),
        )
    ]
    manifest = json.dumps(state["files"], ensure_ascii=False, separators=(",", ":"))
    assert state["dirty_manifest_sha256"] == hashlib.sha256(manifest.encode()).hexdigest()
    assert output.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("path", ["../outside.txt", "/tmp/outside.txt", r"C:\\outside.txt"])
def test_capture_rejects_paths_outside_workspace(tmp_path, path):
    capture = _capture_module()
    with pytest.raises(ValueError, match="workspace"):
        capture.validate_workspace_path(path, tmp_path)


def test_capture_rejects_symlink_escape(tmp_path):
    capture = _capture_module()
    outside = tmp_path.parent / "evidence-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="workspace"):
        capture.validate_workspace_path("link.txt", tmp_path)


def test_capture_rejects_output_symlink_escape(tmp_path):
    capture = _capture_module()
    build = tmp_path / "build"
    build.mkdir()
    for name in capture.ARTIFACT_NAMES:
        (build / name).write_bytes(name.encode("ascii"))
    outside = tmp_path.parent / f"{tmp_path.name}-output.json"
    (build / "takeover-state.json").symlink_to(outside)
    with pytest.raises(ValueError, match="Output escapes workspace"):
        capture.write_manifest(
            head="abc123",
            statuses=[],
            paths=[],
            workspace=tmp_path,
            output=build / "takeover-state.json",
        )


def test_cli_accepts_leading_dash_path_as_data(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    for name in ("wayfinding.gpkg", "graph_contracted.pkl", "graph_contracted_stats.json"):
        (build / name).write_bytes(name.encode("ascii"))
    (tmp_path / "-leading.txt").write_bytes(b"leading")
    output = build / "takeover-state.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--head=abc123",
            "--status=?? -leading.txt",
            "--path=-leading.txt",
            f"--workspace={tmp_path}",
            f"--output={output}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    state = json.loads(output.read_text(encoding="utf-8"))
    assert state["files"][0]["path"] == "-leading.txt"


def test_powershell_entrypoint_forwards_git_values_to_docker():
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    lowered = wrapper.lower()
    assert "[switch]$localimage" in lowered
    assert "docker compose" in lowered
    assert "capture_takeover_evidence.py" in lowered
    assert "--head=" in lowered
    assert "--status=" in lowered
    assert "--path=" in lowered
    assert "get-filehash" not in lowered
    assert "convertto-json" not in lowered
    assert "set-content" not in lowered
