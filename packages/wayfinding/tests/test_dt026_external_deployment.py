from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "infra" / "docker-compose.candidate.yml"
PROXY = ROOT / "infra" / "wayfinding-external.nginx.conf"


def test_candidate_keeps_loopback_demo_and_adds_bounded_external_proxy() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    assert "${WAYFINDING_CANDIDATE_BIND_ADDRESS:-127.0.0.1}" in compose
    assert "external:" in compose
    assert "nginx@sha256:" in compose
    assert "${WAYFINDING_EXTERNAL_BIND_ADDRESS:-0.0.0.0}" in compose
    assert "${WAYFINDING_EXTERNAL_PORT:-8007}:8007" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "max-size: \"10m\"" in compose
    assert "max-file: \"3\"" in compose
    external = compose.split("  external:", 1)[1].split("  browser:", 1)[0]
    assert "host-bridge: {}" in external


def test_external_proxy_restricts_host_and_preserves_backend_host_boundary() -> None:
    proxy = PROXY.read_text(encoding="utf-8")
    assert "server_name sfuai.ca;" in proxy
    assert "server_name _;" in proxy
    assert "return 444;" in proxy
    assert "proxy_pass http://demo:8080;" in proxy
    assert "proxy_set_header Host demo;" in proxy
    assert "proxy_set_header X-Forwarded-For \"\";" in proxy
    assert "$uri" in proxy
    assert "$request_uri" not in proxy
