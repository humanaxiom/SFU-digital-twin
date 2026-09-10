"""Standard-library HTTP adapter for the DT-013 artifact demonstration."""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

from .artifact import ArtifactRepository, ArtifactUnavailableError, RecordNotFoundError
from .assistant import LIMITATIONS_ID, respond
from .routing import RoutingService

MAX_BODY_BYTES = 4096
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,255}$")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class DemoHTTPServer(ThreadingHTTPServer):
    repository: ArtifactRepository
    routing_service: RoutingService | None


class DemoRequestHandler(BaseHTTPRequestHandler):
    @property
    def repository(self) -> ArtifactRepository:
        return cast(DemoHTTPServer, self.server).repository

    @property
    def routing_service(self) -> RoutingService | None:
        return cast(DemoHTTPServer, self.server).routing_service

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()

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
                scene = self.repository.scene(level_id)
                scene["limitations_id"] = LIMITATIONS_ID
                scene["provenance"] = [
                    self.repository.provenance(layer)
                    for layer in (
                        "level_26910",
                        "unit_26910",
                        "detail_26910",
                        "landmark_26910",
                    )
                ]
                self._json(200, scene)
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
        return self._record({name: values, "count": len(values)}, layer)

    @staticmethod
    def _is_get_route(path: str) -> bool:
        return path in STATIC_FILES or path in {
            "/demo/v1/health",
            "/demo/v1/facilities",
            "/demo/v1/levels",
            "/demo/v1/units",
        } or bool(
            re.fullmatch(r"/demo/v1/levels/[^/]+/scene", path)
            or re.fullmatch(r"/demo/v1/units/[^/]+", path)
        )

    def _static(self, path: str) -> None:
        name, content_type = STATIC_FILES[path]
        static_dir = Path(__file__).with_name("static")
        self._send_bytes(200, content_type, (static_dir / name).read_bytes())

    @staticmethod
    def _valid_route_payload(payload: Any) -> bool:
        if not isinstance(payload, dict) or set(payload) != {"origin", "destination", "profile"}:
            return False
        if payload["profile"] not in {"default", "elevator_only"}:
            return False
        for name in ("origin", "destination"):
            endpoint = payload[name]
            if not isinstance(endpoint, dict) or set(endpoint) != {"unit_id"}:
                return False
            identifier = endpoint["unit_id"]
            if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
                return False
        return True

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def create_server(
    host: str,
    port: int,
    artifact_path: str | Path,
    graph_path: str | Path | None = None,
    stats_path: str | Path | None = None,
) -> DemoHTTPServer:
    server = DemoHTTPServer((host, port), DemoRequestHandler)
    try:
        server.repository = ArtifactRepository(artifact_path)
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    arguments = parser.parse_args()
    server = create_server(
        arguments.host,
        arguments.port,
        arguments.artifact,
        arguments.graph,
        arguments.stats,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
