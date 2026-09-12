"""Fixture-only checks for the containerized post-tool path diagnostic."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hooks/check_read_only_boundary.py"


def run_hook(payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=payload, text=True, capture_output=True, check=False
    )


@pytest.mark.parametrize("field", ["filePath", "path", "file_path"])
@pytest.mark.parametrize(
    "target",
    [
        r"C:\repos\sfudt\claude\dtwin-harness",
        "c:/REPOS/sfudt/claude/DTWIN-HARNESS/data/IndoorWayfinding.gdb/a.gdbtable",
        r"C:\repos\sfudt\claude\dtwin-harness\data\..\README.md",
        r"C:\repos\sfudt\dtwin-harness\README.md",
        "/data/IndoorWayfinding.gdb/a.gdbtable",
    ],
)
def test_protected_direct_paths_are_diagnosed(field: str, target: str) -> None:
    result = run_hook(json.dumps({"tool_input": {field: target}}))
    assert result.returncode == 2
    message = json.loads(result.stdout)["systemMessage"]
    assert "protected" in message
    assert "cannot prevent or undo" in message
    assert "shell commands" in message
    assert "symlink" in message
    assert "decision" not in json.loads(result.stdout)


@pytest.mark.parametrize(
    "target",
    [
        r"C:\repos\sfudt\claude\dtwin-harness-copy\README.md",
        r"C:\repos\sfudt\dtwin-harness-old\README.md",
        r"C:\repos\sfudt\ghcp\README.md",
        "/data/IndoorWayfinding.gdb-copy/a.gdbtable",
    ],
)
def test_similarly_prefixed_or_repository_path_is_not_protected(target: str) -> None:
    result = run_hook(json.dumps({"tool_input": {"path": target}}))
    assert result.returncode == 0
    assert result.stdout == ""


def test_relative_windows_path_uses_payload_cwd() -> None:
    result = run_hook(json.dumps({
        "cwd": r"C:\repos\sfudt\ghcp",
        "tool_input": {"file_path": r"..\claude\dtwin-harness\data\fixture.txt"},
    }))
    assert result.returncode == 2
    assert "protected" in json.loads(result.stdout)["systemMessage"]


def test_each_direct_path_is_checked() -> None:
    result = run_hook(json.dumps({"tool_input": {
        "path": r"C:\repos\sfudt\ghcp\README.md",
        "file_path": r"C:\repos\sfudt\claude\dtwin-harness\fixture.txt",
    }}))
    assert result.returncode == 2
    assert "protected" in json.loads(result.stdout)["systemMessage"]


@pytest.mark.parametrize(
    "payload",
    [
        "", "{", "null", "[]", "{}", '{"tool_input": []}',
        '{"tool_input": {"path": 42}}', '{"tool_input": {"path": ""}}',
        '{"tool_input": {"path": "relative.txt"}}',
        '{"tool_input": {"command": "touch some-file"}}',
    ],
)
def test_unassessable_payload_is_a_visible_error(payload: str) -> None:
    result = run_hook(payload)
    assert result.returncode == 1
    assert "not assessed" in json.loads(result.stdout)["systemMessage"]


def test_hook_and_legacy_launcher_delegate_to_artifact_container() -> None:
    config = json.loads((ROOT / ".github/hooks/enforce-read-only-source.json").read_text())
    command = config["hooks"]["PostToolUse"][0]["command"]
    assert command.startswith("docker compose ")
    expected = "run --rm --no-deps -T artifact python tools/hooks/check_read_only_boundary.py"
    assert expected in command
    wrapper = (ROOT / "tools/hooks/check-read-only-boundary.ps1").read_text()
    assert "docker compose" in wrapper
    assert "ConvertFrom-Json" not in wrapper
    assert "Resolve-Path" not in wrapper
    assert "exit $LASTEXITCODE" in wrapper
