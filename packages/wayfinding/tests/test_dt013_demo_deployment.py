"""RED structural tests for the DT-013 Compose and launcher boundary."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
MAKEFILE_PATH = WORKSPACE_ROOT / "Makefile"
LAUNCHERS = (
    WORKSPACE_ROOT / "tools" / "launch-stack.sh",
    WORKSPACE_ROOT / "tools" / "launch-stack.ps1",
)
ARTIFACT_TARGET = "/data/wayfinding.gpkg"


def _demo_service() -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    assert "demo" in services, "infra/docker-compose.yml must define a demo service"
    return services["demo"]


def _volume_entries(service: dict[str, Any]) -> list[Any]:
    volumes = service.get("volumes", [])
    if isinstance(volumes, dict):
        return [
            {"source": source, **(value if isinstance(value, dict) else {})}
            for source, value in volumes.items()
        ]
    return volumes


def _mounts(service: dict[str, Any], target: str) -> list[Any]:
    matches = []
    for entry in _volume_entries(service):
        if isinstance(entry, str) and re.search(rf":{re.escape(target)}(?::(?:ro|rw))?$", entry):
            matches.append(entry)
        elif isinstance(entry, dict) and entry.get("target") == target:
            matches.append(entry)
    return matches


def _is_read_only(entry: Any) -> bool:
    if isinstance(entry, str):
        return entry.endswith(":ro")
    return entry.get("read_only") is True or entry.get("mode") == "ro"


def test_demo_compose_mounts_only_the_artifact_read_only():
    demo = _demo_service()
    artifact_mounts = _mounts(demo, ARTIFACT_TARGET)

    assert len(artifact_mounts) == 1
    assert _is_read_only(artifact_mounts[0])
    rendered_volumes = yaml.safe_dump(_volume_entries(demo)).lower()
    assert "indoorwayfinding.gdb" not in rendered_volumes
    assert ".gdb" not in rendered_volumes
    assert "docker.sock" not in rendered_volumes
    assert not re.search(r"/workspace/build(?::|$)", rendered_volumes), (
        "demo must not inherit the read-write build-directory mount"
    )
    workspace_mounts = _mounts(demo, "/workspace")
    assert len(workspace_mounts) == 1
    assert _is_read_only(workspace_mounts[0])


def test_demo_compose_publishes_only_launcher_selected_loopback_port():
    demo = _demo_service()
    ports = demo.get("ports", [])
    rendered_ports = yaml.safe_dump(ports)

    assert len(ports) == 1
    assert "127.0.0.1" in rendered_ports
    assert "DTWIN_DEMO_HOST_PORT" in rendered_ports
    assert re.search(r"(?:8080|8000)", rendered_ports)
    assert "0.0.0.0" not in rendered_ports


def test_demo_compose_runs_checked_in_module_without_runtime_install():
    demo = _demo_service()
    command = yaml.safe_dump(demo.get("command", "")).lower()
    healthcheck = yaml.safe_dump(demo.get("healthcheck", {})).lower()

    assert "wayfinding.demo" in command
    assert "/data/wayfinding.gpkg" in command
    assert "/demo/v1/health" in healthcheck
    assert not re.search(r"\b(?:pip|pip3|uv|apt|apt-get)\b", command)


def test_both_launchers_reserve_and_report_the_demo_port():
    for launcher_path in LAUNCHERS:
        content = launcher_path.read_text(encoding="utf-8")
        assert "DTWIN_DEMO_HOST_PORT" in content, (
            f"{launcher_path.name} must select and report the demo port"
        )
        assert re.search(r"DTWIN_DEMO_HOST_PORT[^\n]*(?:7|selectedBase \+ 7)", content), (
            f"{launcher_path.name} must reserve offset 7 for the demo"
        )


def test_normal_test_gate_remains_container_only_and_collects_dt013():
    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    match = re.search(r"(?m)^test:[^\n]*\n(?P<recipe>(?:\t[^\n]*(?:\n|$))+)", makefile)

    assert match, "Makefile must define a test target"
    recipe = match.group("recipe")
    assert re.search(r"docker\s+compose\b.*\brun\s+--rm\s+artifact\b", recipe)
    assert "pytest packages/wayfinding/tests" in recipe
    assert not re.search(r"\b(?:pip|pip3|uv|apt|apt-get)\b", recipe)
