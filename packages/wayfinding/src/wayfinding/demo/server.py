"""Standard-library HTTP adapter for the DT-013 artifact demonstration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import Future
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

from .artifact import ArtifactRepository, ArtifactUnavailableError, RecordNotFoundError
from .assistant import LIMITATIONS_ID, respond
from .routing import RoutingService

MAX_BODY_BYTES = 4096
MAX_CONCURRENT_REQUESTS = 16
REQUEST_TIMEOUT_SECONDS = 5.0
RATE_WINDOW_SECONDS = 60.0
READ_REQUESTS_PER_WINDOW = 120
POST_REQUESTS_PER_WINDOW = 30
MAX_RATE_CLIENTS = 256
MAX_SCENE_CACHE_ENTRIES = 16
MAX_SCENE_CACHE_BYTES = 32 * 1024 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class DemoHTTPServer(ThreadingHTTPServer):
    repository: ArtifactRepository
    routing_service: RoutingService | None

    def __init__(self, *args: Any, allowed_host: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        configured_host = allowed_host or os.environ.get("DTWIN_DEMO_ALLOWED_HOST", "localhost")
        if not HOSTNAME.fullmatch(configured_host):
            self.server_close()
            raise ValueError("DTWIN_DEMO_ALLOWED_HOST must be a DNS-compatible host name.")
        self.allowed_hosts = {"localhost", "127.0.0.1", "::1", configured_host.lower()}
        self.request_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        self.rate_lock = threading.Lock()
        self.rate_clients: OrderedDict[str, dict[str, deque[float]]] = OrderedDict()
        self.scene_cache_lock = threading.Lock()
        self.scene_cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self.scene_cache_bytes = 0
        self.scene_pending: dict[tuple[str, str], Future[bytes]] = {}

    def process_request(self, request: Any, client_address: Any) -> None:
        # Admit before ThreadingMixIn creates a worker; never queue unlimited threads.
        if not self.request_semaphore.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            request.settimeout(REQUEST_TIMEOUT_SECONDS)
            super().process_request(request, client_address)
        except Exception:
            self.request_semaphore.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_semaphore.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        # socketserver's default dumps exception values and filesystem paths.
        # Keep unexpected failures observable without disclosing request/artifact data.
        print("HTTP request terminated; exception details suppressed.", flush=True)

    def rate_limit_allows(self, client: str, category: str) -> bool:
        now = time.monotonic()
        limit = POST_REQUESTS_PER_WINDOW if category == "post" else READ_REQUESTS_PER_WINDOW
        with self.rate_lock:
            buckets = self.rate_clients.setdefault(
                client, {"read": deque(), "post": deque()}
            )
            self.rate_clients.move_to_end(client)
            bucket = buckets[category]
            while bucket and now - bucket[0] >= RATE_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            while len(self.rate_clients) > MAX_RATE_CLIENTS:
                self.rate_clients.popitem(last=False)
            return True

    def scene_response(self, level_id: str) -> bytes:
        """Reuse complete immutable responses without sharing OGR handles."""
        repository = self.repository
        key = (repository.artifact_sha256, level_id)
        owner = False
        with self.scene_cache_lock:
            cached = self.scene_cache.get(key)
            if cached is not None:
                self.scene_cache.move_to_end(key)
                return cached
            pending = self.scene_pending.get(key)
            if pending is None:
                pending = Future()
                self.scene_pending[key] = pending
                owner = True
        if not owner:
            return pending.result()
        try:
            scene = repository.scene(level_id)
            scene["limitations_id"] = LIMITATIONS_ID
            scene["provenance"] = [
                repository.provenance(layer)
                for layer in (
                    "level_26910", "unit_26910", "detail_26910", "landmark_26910"
                )
            ]
            body = json.dumps(scene, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        except BaseException as exc:
            # Wake all matching waiters and allow the next request to retry.
            with self.scene_cache_lock:
                self.scene_pending.pop(key, None)
                pending.set_exception(exc)
            raise
        with self.scene_cache_lock:
            if MAX_SCENE_CACHE_ENTRIES > 0 and len(body) <= MAX_SCENE_CACHE_BYTES:
                while self.scene_cache and (
                    len(self.scene_cache) >= MAX_SCENE_CACHE_ENTRIES
                    or self.scene_cache_bytes + len(body) > MAX_SCENE_CACHE_BYTES
                ):
                    _, evicted = self.scene_cache.popitem(last=False)
                    self.scene_cache_bytes -= len(evicted)
                self.scene_cache[key] = body
                self.scene_cache_bytes += len(body)
            self.scene_pending.pop(key, None)
            pending.set_result(body)
        return body

    def warm_scene_cache(self) -> int:
        """Best-effort CLI startup work; failed floors stay retryable."""
        try:
            levels = self.repository.levels()[:max(0, MAX_SCENE_CACHE_ENTRIES)]
        except Exception:
            print(
                "Floor response prewarm unavailable; foreground requests remain enabled.",
                flush=True,
            )
            return 0
        prepared = 0
        for level in levels:
            try:
                self.scene_response(level["level_id"])
                prepared += 1
            except Exception:
                print(
                    "Floor response prewarm unavailable; foreground requests remain enabled.",
                    flush=True,
                )
        return prepared


class DemoRequestHandler(BaseHTTPRequestHandler):
    request_started_at: float

    @property
    def repository(self) -> ArtifactRepository:
        return cast(DemoHTTPServer, self.server).repository

    @property
    def routing_service(self) -> RoutingService | None:
        return cast(DemoHTTPServer, self.server).routing_service

    def handle_one_request(self) -> None:
        self.request_started_at = time.monotonic()
        super().handle_one_request()

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if not self._valid_host_header(self.headers.get("Host")):
            self._error(400, "Invalid Host header.")
            return False
        category = "post" if self.command == "POST" else "read"
        client = self.client_address[0]
        if not cast(DemoHTTPServer, self.server).rate_limit_allows(client, category):
            self._headers(429, "application/json", 0, retry_after=int(RATE_WINDOW_SECONDS))
            return False
        return True

    def _valid_host_header(self, value: str | None) -> bool:
        if not value or any(character in value for character in " /\\\t\r\n"):
            return False
        host = value
        if value.startswith("["):
            match = re.fullmatch(r"\[([^]]+)](?::\d{1,5})?", value)
            if not match:
                return False
            host = match.group(1)
        elif value.count(":") == 1:
            host, port = value.rsplit(":", 1)
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                return False
        elif ":" in value:
            return False
        return host.lower().rstrip(".") in cast(DemoHTTPServer, self.server).allowed_hosts

    def _headers(
        self, status: int, content_type: str, length: int, *, retry_after: int | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self._log_access(status)

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self._headers(status, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", body)

    def _error(self, status: int, message: str) -> None:
        self._json(
            status,
            {
                "error": message,
                "artifact_sha256": self.repository.artifact_sha256,
                "limitations_id": LIMITATIONS_ID,
            },
        )

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        if code == 501:
            self._error(405, "Method not allowed.")
            return
        self._error(code, message or explain or "Request failed.")

    def do_GET(self) -> None:  # noqa: N802
        target = urlsplit(self.path)
        path = unquote(target.path)
        if ".." in path.split("/") or "\\" in path or "\x00" in path:
            self._error(404, "Not found.")
            return
        try:
            if path in STATIC_FILES and not target.query:
                self._static(path)
                return
            if path == "/demo/v1/client" and not target.query:
                raw = Path(__file__).with_name("static").joinpath("app.js").read_bytes()
                self._json(200, {"protocol": 1, "script_sha256": hashlib.sha256(raw).hexdigest()})
                return
            if path == "/demo/v1/route-options":
                self._get_route_options(target.query)
                return
            if path == "/demo/v1/health" and not target.query:
                self._json(
                    200,
                    {
                        "status": "ok",
                        "artifact_sha256": self.repository.artifact_sha256,
                        "required_layers_valid": True,
                        "limitations_id": LIMITATIONS_ID,
                        "capabilities": {
                            "routing": self.routing_service is not None,
                            "nearest": False,
                            "live_status": False,
                            "llm": False,
                        },
                        **(
                            {"provenance": dict(self.routing_service.provenance)}
                            if self.routing_service is not None
                            else {}
                        ),
                    },
                )
                return
            if path == "/demo/v1/facilities" and not target.query:
                self._json(
                    200,
                    self._collection(
                        "facilities", self.repository.facilities(), "facility_26910"
                    ),
                )
                return
            if path == "/demo/v1/campus" and not target.query:
                self._json(200, self.repository.campus_overview())
                return
            if path == "/demo/v1/levels":
                query = parse_qs(target.query, keep_blank_values=True)
                if set(query) - {"facility_id"} or len(query.get("facility_id", [])) > 1:
                    self._error(400, "Invalid query parameters.")
                    return
                facility_id = query.get("facility_id", [None])[0]
                if facility_id is not None and not IDENTIFIER.fullmatch(facility_id):
                    self._error(400, "Invalid facility identifier.")
                    return
                self._json(
                    200,
                    self._collection(
                        "levels", self.repository.levels(facility_id), "level_26910"
                    ),
                )
                return
            if path == "/demo/v1/units" and not target.query:
                self._json(
                    200,
                    self._collection("units", self.repository.units(), "unit_26910"),
                )
                return
            scene_match = re.fullmatch(r"/demo/v1/levels/([^/]+)/scene", path)
            if scene_match and not target.query:
                level_id = scene_match.group(1)
                if not IDENTIFIER.fullmatch(level_id):
                    self._error(400, "Invalid level identifier.")
                    return
                body = cast(DemoHTTPServer, self.server).scene_response(level_id)
                self._send_bytes(200, "application/json; charset=utf-8", body)
                return
            unit_match = re.fullmatch(r"/demo/v1/units/([^/]+)", path)
            if unit_match and not target.query:
                unit_id = unit_match.group(1)
                if not IDENTIFIER.fullmatch(unit_id):
                    self._error(400, "Invalid unit identifier.")
                    return
                self._json(200, self._record(self.repository.unit(unit_id), "unit_26910"))
                return
            if path == "/demo/v1/assistant":
                self._error(405, "Method not allowed.")
                return
            if path == "/demo/v1/route":
                self._error(405, "Method not allowed.")
                return
            self._error(404, "Not found.")
        except RecordNotFoundError:
            self._error(404, "Record not found.")
        except ArtifactUnavailableError:
            self._error(503, "Artifact unavailable.")

    def do_POST(self) -> None:  # noqa: N802
        target = urlsplit(self.path)
        if target.path not in {"/demo/v1/assistant", "/demo/v1/route"} or target.query:
            if self._is_get_route(target.path):
                self._error(405, "Method not allowed.")
            else:
                self._error(404, "Not found.")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(400, "Invalid request body.")
            return
        if content_length > MAX_BODY_BYTES:
            self._error(413, "Request body is too large.")
            return
        if content_length <= 0 or self.headers.get_content_type() != "application/json":
            self._error(400, "A JSON request body is required.")
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._error(400, "Malformed JSON request body.")
            return
        if target.path == "/demo/v1/route":
            if not self._valid_route_payload(payload) or self.routing_service is None:
                response = {
                    "status": 400,
                    "code": "invalid_request",
                    "profile": payload.get("profile", "") if isinstance(payload, dict) else "",
                    "allowed_modes": [],
                    "warnings": [],
                    "provenance": (
                        dict(self.routing_service.provenance)
                        if self.routing_service is not None
                        else {}
                    ),
                }
                self._json(400, response)
                return
            response = self.routing_service.route(
                payload["origin"]["unit_id"],
                payload["destination"]["unit_id"],
                payload["profile"],
            )
            self._json(response["status"], response)
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
            self._error(400, "Message must be a string.")
            return
        message = payload["message"]
        facility_id = payload.get("facility_id")
        level_id = payload.get("level_id")
        if not message.strip() or len(message) > 500:
            self._error(400, "Message must contain between 1 and 500 characters.")
            return
        invalid_context = any(
            value is not None
            and (not isinstance(value, str) or not IDENTIFIER.fullmatch(value))
            for value in (facility_id, level_id)
        )
        if invalid_context:
            self._error(400, "Invalid map context.")
            return
        response = respond(
            self.repository,
            message,
            facility_id,
            level_id,
            routing_service=self.routing_service,
        )
        if "status" in response:
            self._json(response["status"], response)
            return
        response["artifact_sha256"] = self.repository.artifact_sha256
        evidence_layers = dict.fromkeys(
            item["layer"] for item in response.get("evidence", [])
        )
        response["provenance"] = [
            self.repository.provenance(layer) for layer in evidence_layers
        ]
        self._json(200, response)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_PUT(self) -> None:  # noqa: N802
        self._error(405, "Method not allowed.")

    def do_DELETE(self) -> None:  # noqa: N802
        self._error(405, "Method not allowed.")

    def do_PATCH(self) -> None:  # noqa: N802
        self._error(405, "Method not allowed.")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._error(405, "Method not allowed.")

    def _record(self, payload: dict[str, Any], layer: str) -> dict[str, Any]:
        result = dict(payload)
        result.setdefault("limitations_id", LIMITATIONS_ID)
        result.setdefault("provenance", self.repository.provenance(layer))
        return result

    def _collection(
        self,
        name: str,
        values: list[dict[str, Any]],
        layer: str,
    ) -> dict[str, Any]:
        response = self._record({name: values, "count": len(values)}, layer)
        if name == "facilities" and self.repository.overview_footprint is not None:
            response["provenance"] = self.repository.campus_provenance()
        return response

    def _get_route_options(self, query_string: str) -> None:
        routing = self.routing_service
        try:
            query = parse_qs(
                query_string, keep_blank_values=True, strict_parsing=True, max_num_fields=4
            )
        except ValueError:
            query = {}
        valid = (
            set(query) == {"origin_unit_id", "profile"}
            and all(len(values) == 1 for values in query.values())
            and bool(IDENTIFIER.fullmatch(query["origin_unit_id"][0]))
            and bool(query["profile"][0])
        )
        if not valid or routing is None:
            status = 400 if not valid else 503
            self._json(status, {
                "version": "route-options-v1",
                "status": status,
                "code": "invalid_request" if not valid else "routing_unavailable",
                "provenance": dict(routing.provenance) if routing is not None else {},
                "warnings": [],
            })
            return
        response = routing.route_options(query["origin_unit_id"][0], query["profile"][0])
        self._json(response["status"], response)

    @staticmethod
    def _is_get_route(path: str) -> bool:
        return path in STATIC_FILES or path in {
            "/demo/v1/health",
            "/demo/v1/client",
            "/demo/v1/campus",
            "/demo/v1/facilities",
            "/demo/v1/levels",
            "/demo/v1/units",
            "/demo/v1/route-options",
        } or bool(
            re.fullmatch(r"/demo/v1/levels/[^/]+/scene", path)
            or re.fullmatch(r"/demo/v1/units/[^/]+", path)
        )

    def _static(self, path: str) -> None:
        name, content_type = STATIC_FILES[path]
        static_dir = Path(__file__).with_name("static")
        body = (static_dir / name).read_bytes()
        if path == "/app.js":
            revision = hashlib.sha256(body).hexdigest()
            body += f'\n;setLoadedClientRevision("{revision}");\n'.encode("ascii")
        self._send_bytes(200, content_type, body)

    @staticmethod
    def _valid_route_payload(payload: Any) -> bool:
        if not isinstance(payload, dict) or set(payload) != {"origin", "destination", "profile"}:
            return False
        if not isinstance(payload["profile"], str) or payload["profile"] not in {
            "default", "elevator_only"
        }:
            return False
        for name in ("origin", "destination"):
            endpoint = payload[name]
            if not isinstance(endpoint, dict) or set(endpoint) != {"unit_id"}:
                return False
            identifier = endpoint["unit_id"]
            if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
                return False
        return True

    def _log_access(self, status: int) -> None:
        try:
            path = urlsplit(getattr(self, "path", "")).path
        except ValueError:
            path = ""
        if re.fullmatch(r"/demo/v1/levels/[^/]+/scene", path):
            path = "/demo/v1/levels/{level_id}/scene"
        elif re.fullmatch(r"/demo/v1/units/[^/]+", path):
            path = "/demo/v1/units/{unit_id}"
        elif path not in STATIC_FILES and path not in {
            "/demo/v1/health", "/demo/v1/campus", "/demo/v1/facilities", "/demo/v1/levels",
            "/demo/v1/units", "/demo/v1/route", "/demo/v1/assistant",
            "/demo/v1/route-options",
        }:
            path = "<unmatched>"
        method = self.command if self.command in {
            "GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT",
        } else "<other>"
        duration_ms = (time.monotonic() - self.request_started_at) * 1000
        timestamp = datetime.now(UTC).isoformat(timespec="milliseconds")
        print(
            f"{timestamp} client={self.client_address[0]} method={method} "
            f"route={path} status={status} duration_ms={duration_ms:.1f}",
            flush=True,
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def create_server(
    host: str,
    port: int,
    artifact_path: str | Path,
    graph_path: str | Path | None = None,
    stats_path: str | Path | None = None,
    allowed_host: str | None = None,
    overview_footprint_path: str | Path | None = None,
) -> DemoHTTPServer:
    server = DemoHTTPServer((host, port), DemoRequestHandler, allowed_host=allowed_host)
    try:
        server.repository = ArtifactRepository(
            artifact_path, overview_footprint_path=overview_footprint_path
        )
        server.routing_service = (
            RoutingService.from_artifacts(artifact_path, graph_path, stats_path)
            if graph_path is not None and stats_path is not None
            else None
        )
    except Exception:
        server.server_close()
        raise
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the artifact-backed local demo.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--overview-footprint", type=Path)
    arguments = parser.parse_args()
    server = create_server(
        arguments.host,
        arguments.port,
        arguments.artifact,
        arguments.graph,
        arguments.stats,
        overview_footprint_path=arguments.overview_footprint,
    )
    try:
        started = time.monotonic()
        prepared = server.warm_scene_cache()
        print(
            f"Prepared {prepared} floor responses in {time.monotonic() - started:.3f}s.",
            flush=True,
        )
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
