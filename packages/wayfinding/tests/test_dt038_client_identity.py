"""DT-038 loaded script identity HTTP contracts."""

import hashlib
import json
import threading
from http.client import HTTPConnection
from types import SimpleNamespace

import pytest

from wayfinding.demo import server as module


@pytest.fixture
def client_server(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "app.js").write_bytes(b'"use strict";\nconst sample = 1; // trailing comment')
    (static / "index.html").write_bytes(b"<!doctype html><title>Original</title>")
    (static / "styles.css").write_bytes(b"body { color: black; }")
    monkeypatch.setattr(module, "__file__", str(tmp_path / "server.py"))
    service = module.DemoHTTPServer(("127.0.0.1", 0), module.DemoRequestHandler)
    service.repository = SimpleNamespace(artifact_sha256="unchanged-artifact")
    service.routing_service = None
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield service, static
    finally:
        service.shutdown()
        service.server_close()
        thread.join(5)


def fetch(fixture, path, method="GET", headers=None):
    service, _ = fixture
    connection = HTTPConnection("127.0.0.1", service.server_port, timeout=5)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_identity_and_stamp_describe_exact_same_raw_bytes(client_server, monkeypatch):
    _, static = client_server
    raw = (static / "app.js").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    status, headers, body = fetch(client_server, "/demo/v1/client")
    assert status == 200
    assert json.loads(body) == {"protocol": 1, "script_sha256": digest}
    assert headers["Cache-Control"] == "no-store"
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    reads = []
    original = type(static).read_bytes

    def read_bytes(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(type(static), "read_bytes", read_bytes)
    status, headers, served = fetch(client_server, "/app.js")
    assert status == 200
    assert served == raw + f'\n;setLoadedClientRevision("{digest}");\n'.encode()
    assert served.startswith(b'"use strict";')
    assert reads == [static / "app.js"], "Hash and response must share one raw read"
    assert int(headers["Content-Length"]) == len(served)
    assert headers["Content-Type"] == "text/javascript; charset=utf-8"


def test_identity_changes_without_server_restart(client_server):
    _, static = client_server
    before = json.loads(fetch(client_server, "/demo/v1/client")[2])
    raw = b'"use strict";\nconst changed = 2;'
    (static / "app.js").write_bytes(raw)
    after = json.loads(fetch(client_server, "/demo/v1/client")[2])
    assert after["script_sha256"] == hashlib.sha256(raw).hexdigest()
    assert before != after
    assert after["script_sha256"].encode() in fetch(client_server, "/app.js")[2]


def test_health_and_other_static_files_remain_unchanged(client_server):
    _, static = client_server
    status, _, body = fetch(client_server, "/demo/v1/health")
    assert status == 200
    assert json.loads(body) == {
        "status": "ok", "artifact_sha256": "unchanged-artifact",
        "required_layers_valid": True, "limitations_id": module.LIMITATIONS_ID,
        "capabilities": {"routing": False, "nearest": False, "live_status": False, "llm": False},
    }
    for path, name in (("/", "index.html"), ("/index.html", "index.html"),
                       ("/styles.css", "styles.css")):
        status, headers, body = fetch(client_server, path)
        assert status == 200
        assert body == (static / name).read_bytes()
        assert headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(("method", "path", "expected"), [
    ("GET", "/demo/v1/client?v=1", 404),
    ("GET", "/app.js?v=1", 404),
    ("POST", "/demo/v1/client", 405),
    ("PUT", "/demo/v1/client", 405),
    ("DELETE", "/demo/v1/client", 405),
])
def test_query_and_method_contracts(client_server, method, path, expected):
    assert fetch(client_server, path, method)[0] == expected


def test_identity_preserves_host_and_read_admission(client_server, monkeypatch):
    assert fetch(client_server, "/demo/v1/client", headers={"Host": "evil.example"})[0] == 400
    monkeypatch.setattr(module, "READ_REQUESTS_PER_WINDOW", 1)
    assert fetch(client_server, "/demo/v1/client")[0] == 200
    status, headers, _ = fetch(client_server, "/demo/v1/client")
    assert status == 429
    assert headers["Retry-After"] == str(int(module.RATE_WINDOW_SECONDS))
