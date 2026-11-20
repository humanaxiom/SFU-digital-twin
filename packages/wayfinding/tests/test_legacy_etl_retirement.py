"""Ensure retired operator commands leave preexisting artifact bytes alone."""

import re
import subprocess
from pathlib import Path

import pytest

from wayfinding.etl import run

COMMANDS = ("extract", "normalise", "graph-raw", "graph-transitions", "graph-contract")
REBUILD_GUIDANCE = "make etl RUN_ID=<unused-id>"


@pytest.mark.parametrize("command", COMMANDS)
def test_legacy_cli_fails_before_touching_build(command, monkeypatch, tmp_path, capsys):
    build = tmp_path / "build"
    build.mkdir()
    accepted = {
        "wayfinding.gpkg": b"accepted GeoPackage",
        "graph_contracted.pkl": b"accepted graph",
        "graph_contracted_stats.json": b"accepted stats",
    }
    for name, contents in accepted.items():
        (build / name).write_bytes(contents)

    # Redirect the historical CLI's absolute paths before running it.
    def disposable_path(path):
        if path.startswith("/workspace/"):
            return tmp_path / Path(path).relative_to("/workspace")
        return tmp_path / Path(path).name

    monkeypatch.setattr(run, "Path", disposable_path, raising=False)

    status = run.main(command)
    assert {path.name: path.read_bytes() for path in build.iterdir()} == accepted
    assert status != 0
    error = capsys.readouterr().err
    assert command in error
    assert REBUILD_GUIDANCE in error


@pytest.mark.parametrize("command", COMMANDS)
def test_legacy_make_recipe_refuses_without_running_a_stage(command):
    makefile = Path("/workspace/Makefile").read_text(encoding="utf-8")
    target = f"etl-{command}"
    rule = re.search(rf"(?m)^(?:[\w-]+ )*{target}(?: [\w-]+)*:[ \t]*\n((?:\t.*\n)+)", makefile)
    assert rule is not None, f"{target} must provide migration guidance"
    recipe = rule[1]
    assert "docker" not in recipe
    assert "python" not in recipe
    command_line = recipe.strip().removeprefix("@").replace("$@", target)
    refused = subprocess.run(
        ["sh", "-c", command_line], capture_output=True, text=True, check=False
    )
    assert refused.returncode == 1
    assert target in refused.stderr
    assert REBUILD_GUIDANCE in refused.stderr
