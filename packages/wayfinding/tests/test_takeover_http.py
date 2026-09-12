"""Behavioral regressions for the inherited LAN HTTP boundary."""

import http.client
import json
import socket
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from wayfinding.demo import server as module


@contextmanager
def running_server():
    server = module.DemoHTTPServer(("127.0.0.1", 0), module.DemoRequestHandler)
    server.routing_service = None
    server.repository = SimpleNamespace(artifact_sha256="fixture")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("profile", [[], {}, None, True, 7, "unknown"])
def test_malformed_profile_returns_json_400(profile):
    with running_server() as server:
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            connection.request(
                "POST", "/demo/v1/route",
                json.dumps({"origin": {"unit_id": "A"},
                            "destination": {"unit_id": "B"}, "profile": profile}),
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            assert response.status == 400
            assert json.loads(response.read())["code"] == "invalid_request"
        finally:
            connection.close()


def test_admission_rejects_excess_connections_without_waiting():
    with running_server() as server:
        for _ in range(module.MAX_CONCURRENT_REQUESTS):
            assert server.request_semaphore.acquire(blocking=False)
        try:
            with socket.create_connection(server.server_address, timeout=1) as client:
                assert client.recv(1) == b""
        finally:
            for _ in range(module.MAX_CONCURRENT_REQUESTS):
                server.request_semaphore.release()


def test_idle_connection_has_read_deadline(monkeypatch):
    monkeypatch.setattr(module, "REQUEST_TIMEOUT_SECONDS", 0.05, raising=False)
    with running_server() as server:
        with socket.create_connection(server.server_address, timeout=1) as client:
            assert client.recv(1) == b""


def test_completed_request_releases_admission_slot(monkeypatch):
    monkeypatch.setattr(module, "MAX_CONCURRENT_REQUESTS", 1)
    with running_server() as server:
        for _ in range(2):
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                assert response.status == 200
                response.read()
            finally:
                connection.close()
            assert server.request_semaphore.acquire(timeout=1)
            server.request_semaphore.release()


def test_rate_denial_retains_security_headers_and_access_log(monkeypatch, capsys):
    monkeypatch.setattr(module, "READ_REQUESTS_PER_WINDOW", 0)
    with running_server() as server:
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            assert response.status == 429
            assert response.getheader("Retry-After") == "60"
            assert response.getheader("Cache-Control") == "no-store"
            assert response.getheader("X-Content-Type-Options") == "nosniff"
            assert response.getheader("X-Frame-Options") == "DENY"
            assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
            response.read()
        finally:
            connection.close()
    assert "route=/ status=429" in capsys.readouterr().out


@pytest.mark.parametrize("path", [
    "/not-an-api/ROOM_SECRET?question=PRIVATE",
    "/demo/v1/units/ROOM_SECRET/extra",
    "/demo/v1/levels/ROOM_SECRET/scene/extra",
    "/%0aROOM_SECRET",
])
def test_unknown_paths_are_not_disclosed_in_access_logs(path, capsys):
    with running_server() as server:
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        finally:
            connection.close()
    output = capsys.readouterr().out
    assert "ROOM_SECRET" not in output
    assert "PRIVATE" not in output
    assert "route=<unmatched> status=404" in output


def test_unexpected_handler_error_does_not_log_traceback_or_values(monkeypatch, capsys):
    def broken_static(_handler, _path):
        raise RuntimeError("ROOM_SECRET /private/artifact/path")

    monkeypatch.setattr(module.DemoRequestHandler, "_static", broken_static)
    with running_server() as server:
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            connection.request("GET", "/")
            with pytest.raises(http.client.RemoteDisconnected):
                connection.getresponse()
        finally:
            connection.close()
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "Traceback" not in output
    assert "ROOM_SECRET" not in output
    assert "/private/artifact/path" not in output
    assert "HTTP request terminated; exception details suppressed." in output
