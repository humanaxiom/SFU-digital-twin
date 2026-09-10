"""RED deployment contracts for DT-014's three read-only runtime artifacts."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
COMPOSE_PATH = WORKSPACE_ROOT / "infra/docker-compose.yml"
MAKEFILE_PATH = WORKSPACE_ROOT / "Makefile"
TARGETS = {
    "/data/wayfinding.gpkg": "wayfinding.gpkg",
    "/data/graph_contracted.pkl": "graph_contracted.pkl",
    "/data/graph_contracted_stats.json": "graph_contracted_stats.json",
}


def _demo() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"]["demo"]


def _mounts() -> list[Any]:
    volumes = _demo().get("volumes", [])
    return volumes if isinstance(volumes, list) else list(volumes.values())


def _target(entry: Any) -> str | None:
    if isinstance(entry, str):
        parts = entry.rsplit(":", 2)
        return parts[-2] if parts[-1] in {"ro", "rw"} else parts[-1]
    return entry.get("target")


def _read_only(entry: Any) -> bool:
    if isinstance(entry, str):
        return entry.endswith(":ro")
    return entry.get("read_only") is True or entry.get("mode") == "ro"


def test_demo_mounts_each_approved_route_artifact_exactly_once_and_read_only():
    mounts = _mounts()

    for target, source_name in TARGETS.items():
        matching = [entry for entry in mounts if _target(entry) == target]
        assert len(matching) == 1, f"demo must mount {source_name} exactly once at {target}"
        assert _read_only(matching[0]), f"demo mount for {source_name} must be read-only"
        assert source_name in yaml.safe_dump(matching[0])


def test_demo_mounts_no_source_geodatabase_or_writable_build_directory():
    rendered = yaml.safe_dump(_mounts()).lower()

    assert ".gdb" not in rendered
    assert "docker.sock" not in rendered
    assert not re.search(r"(?:/workspace/build|/data)(?::rw|[^\n]*read_only:\s*false)", rendered)


def test_demo_command_passes_all_artifacts_without_runtime_install_or_network_dependency():
    command = yaml.safe_dump(_demo().get("command", "")).lower()

    assert "wayfinding.demo.server" in command
    assert all(target.lower() in command for target in TARGETS)
    assert not re.search(r"\b(?:pip|pip3|uv|apt|apt-get|curl|wget)\b", command)


def test_dt014_focused_gate_is_container_only_and_selects_only_new_tests():
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    match = re.search(r"(?m)^dt014:[^\n]*\n(?P<recipe>(?:\t[^\n]*(?:\n|$))+)", makefile)

    assert match, "Makefile must define the focused dt014 gate"
    recipe = match.group("recipe")
    assert re.search(r"docker\s+compose\b.*\brun\s+--rm\s+artifact\b", recipe)
    assert "PYTHONPATH=/workspace/packages/wayfinding/src" in recipe
    assert "pytest" in recipe
    assert "test_dt014_" in recipe
    assert not re.search(r"\b(?:python|pip|pip3|uv|apt|apt-get)\b", recipe.split("pytest", 1)[0])
