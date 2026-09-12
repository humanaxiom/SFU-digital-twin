"""RED deployment and trusted-LAN boundary contracts for DT-015."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
MAKEFILE_PATH = WORKSPACE_ROOT / "Makefile"
SERVER_PATH = WORKSPACE_ROOT / "packages/wayfinding/src/wayfinding/demo/server.py"
README_PATH = WORKSPACE_ROOT / "README.md"
LAUNCHERS = {
    "posix": WORKSPACE_ROOT / "tools/launch-stack.sh",
    "powershell": WORKSPACE_ROOT / "tools/launch-stack.ps1",
}


def _demo() -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return compose["services"]["demo"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dt015_demo_publishes_selected_port_on_all_interfaces():
    demo = _demo()
    rendered_ports = yaml.safe_dump(demo.get("ports", []))
    rendered_command = yaml.safe_dump(demo.get("command", []))
    server = _text(SERVER_PATH)

    assert len(demo.get("ports", [])) == 1
    assert "${DTWIN_DEMO_BIND_ADDRESS:-0.0.0.0}" in rendered_ports
    assert "${DTWIN_DEMO_HOST_PORT:-18007}" in rendered_ports
    assert re.search(r"(?:8080|8000)", rendered_ports)
    assert re.search(r"(?:--host\s*\n?\s*-?\s*0\.0\.0\.0|--host.*0\.0\.0\.0)", rendered_command)
    assert re.search(r'add_argument\(["\']--host["\'],\s*default=["\']0\.0\.0\.0["\']', server)
    assert "DTWIN_DEMO_BIND_ADDRESS" not in rendered_command
    assert "127.0.0.1" not in rendered_ports


def test_dt015_launchers_report_machine_name_url_and_lan_warning():
    posix = _text(LAUNCHERS["posix"])
    powershell = _text(LAUNCHERS["powershell"])

    assert re.search(r"(?m)^\s*(?:MACHINE_NAME|machine_name)=\$?\(hostname\)", posix)
    assert "[Environment]::MachineName" in powershell
    for name, launcher in LAUNCHERS.items():
        content = _text(launcher)
        assert "DTWIN_DEMO_BIND_ADDRESS" in content, f"{name} launcher must report the bind address"
        machine_url = re.search(
            r"http://[^\n]*(?:MACHINE_NAME|machine_name|MachineName)"
            r"[^\n]*DTWIN_DEMO_HOST_PORT|http://[^\n]*machine",
            content,
            re.I,
        )
        assert machine_url, (
            f"{name} launcher must print the machine-name LAN URL"
        )
        warning = content.lower()
        assert all(term in warning for term in ("trusted lan", "no authentication", "no tls"))
        assert "stop" in warning
        assert "firewall" in warning
        assert not re.search(r"\b(?:curl|wget|nslookup|dig|ifconfig|ipconfig)\b", content, re.I)
        assert re.search(r"dry.?run", content, re.I)

    readme = _text(README_PATH).lower()
    assert all(term in readme for term in ("trusted lan", "no authentication", "no tls"))
    assert "stop" in readme
    assert "firewall" in readme


def test_dt015_lan_security_contract():
    demo = _demo()
    server = _text(SERVER_PATH)
    rendered_demo = yaml.safe_dump(demo).lower()

    assert "dtwin_demo_allowed_host" in rendered_demo
    assert "DTWIN_DEMO_ALLOWED_HOST" in server
    assert re.search(r"host.*(?:allow|valid)|(?:allow|valid).*host", server, re.I | re.S)
    assert "Retry-After" in server
    assert re.search(r"(?:semaphore|concurren|max_concurrent)", server, re.I)
    assert re.search(r"(?:rate.?limit|requests_per|rate_window)", server, re.I)
    assert "Cache-Control" in server
    assert "no-store" in server
    assert "Access-Control-Allow-Origin" not in server
    assert all(
        header in server
        for header in (
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "X-Frame-Options",
        )
    )
    assert re.search(r"logging:\s*\n\s*driver:\s*[\"']?json-file", rendered_demo)
    assert "max-size" in rendered_demo
    assert "max-file" in rendered_demo
    assert not re.search(r"(?:/var/log|\.log:|transcript)", rendered_demo)
    assert all(term not in rendered_demo for term in (".gdb", "docker.sock", ":rw"))


def test_dt015_focused_gate_is_container_only_and_selects_dt015_tests():
    makefile = _text(MAKEFILE_PATH)
    match = re.search(r"(?m)^dt015:[^\n]*\n(?P<recipe>(?:\t[^\n]*(?:\n|$))+)", makefile)

    assert match, "Makefile must define the focused dt015 gate"
    recipe = match.group("recipe")
    assert re.search(r"docker\s+compose\b.*\brun\s+--rm\s+artifact\b", recipe)
    assert "PYTHONPATH=/workspace/packages/wayfinding/src" in recipe
    assert "pytest" in recipe
    assert "--no-cov" in recipe
    assert all(
        test_file in recipe
        for test_file in (
            "test_dt015_demo_deployment.py",
            "test_dt015_static_client.py",
            "test_dt015_evidence.py",
        )
    )
    assert not re.search(r"\b(?:python|pip|pip3|uv|apt|apt-get)\b", recipe.split("pytest", 1)[0])
