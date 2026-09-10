"""RED contract tests for the DT-013 artifact-backed demo service."""

import hashlib
import importlib
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
GPKG_PATH = WORKSPACE_ROOT / "build" / "wayfinding.gpkg"
LEVEL_VERTICAL_ORDER = {
    "SFU_BURNABY_QUAD_1000": -2,
    "SFU_BURNABY_QUAD_2000": -1,
    "SFU_BURNABY_QUAD_3000": 0,
    "SFU_BURNABY_QUAD_4000": 1,
    "SFU_BURNABY_QUAD_5000": 2,
    "SFU_BURNABY_QUAD_6000": 3,
    "SFU_BURNABY_STRAND_100": -1,
    "SFU_BURNABY_STRAND_1000": 0,
    "SFU_BURNABY_STRAND_2000": 1,
    "SFU_BURNABY_STRAND_3000": 2,
    "SFU_BURNABY_ECC_3000": 0,
}
LIMITATION_ID = "phase1-artifact-only"
NOT_VERIFIED = {"door_width", "path_width", "slope", "powered_doors", "surface"}


def _require_module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as error:
        pytest.fail(f"DT-013 module {name} is not implemented: {error}")


def _repository() -> Any:
    assert GPKG_PATH.is_file(), "Run the containerized ETL to create build/wayfinding.gpkg"
    module = _require_module("wayfinding.demo.artifact")
    assert hasattr(module, "ArtifactRepository"), (
        "wayfinding.demo.artifact must define ArtifactRepository"
    )
    return module.ArtifactRepository(GPKG_PATH)


def _first_real_room() -> dict[str, Any]:
    ogr = pytest.importorskip("osgeo.ogr")
    dataset = ogr.Open(str(GPKG_PATH), 0)
    assert dataset is not None, "OGR could not open the approved GeoPackage read-only"
    layer = dataset.GetLayerByName("unit_26910")
    assert layer is not None, "Approved artifact is missing unit_26910"

    rooms = []
    for feature in layer:
        room_id = feature.GetField("room_id")
        if room_id:
            rooms.append(
                {
                    "unit_id": feature.GetField("unit_id"),
                    "room_id": room_id,
                    "level_id": feature.GetField("level_id"),
                    "use_type": feature.GetField("use_type"),
                    "category": feature.GetField("category"),
                }
            )
    dataset = None
    assert rooms, "Approved artifact contains no room identifiers"
    return min(rooms, key=lambda room: (room["room_id"], room["unit_id"]))


def _request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@contextmanager
def _running_server():
    module = _require_module("wayfinding.demo.server")
    assert hasattr(module, "create_server"), "demo.server must define create_server"
    server = module.create_server("127.0.0.1", 0, GPKG_PATH)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_health_reports_exact_artifact_hash_and_honest_limitations():
    expected_hash = hashlib.sha256(GPKG_PATH.read_bytes()).hexdigest()

    with _running_server() as base_url:
        with urllib.request.urlopen(f"{base_url}/demo/v1/health") as response:
            body = json.load(response)
            headers = response.headers

    assert body["status"] == "ok"
    assert body["artifact_sha256"] == expected_hash
    assert body["required_layers_valid"] is True
    assert body["limitations_id"] == LIMITATION_ID
    assert body["capabilities"] == {
        "routing": False,
        "nearest": False,
        "live_status": False,
        "llm": False,
    }
    assert headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers.get("Access-Control-Allow-Origin") is None


def test_real_artifact_facilities_levels_and_vertical_order_are_exact():
    repository = _repository()

    facilities = repository.facilities()
    levels = repository.levels()

    assert len(facilities) == 3
    assert {item["facility_id"] for item in facilities} == {
        "SFU_BURNABY_QUAD",
        "SFU_BURNABY_STRAND",
        "SFU_BURNABY_ECC",
    }
    assert len(levels) == 11
    assert {item["level_id"]: item["vertical_order"] for item in levels} == (
        LEVEL_VERTICAL_ORDER
    )
    assert levels == sorted(
        levels,
        key=lambda item: (
            item["vertical_order"],
            item["facility_id"],
            item["short_name"],
        ),
    )


def test_real_artifact_public_counts_are_exact():
    repository = _repository()

    assert len(repository.units()) == 1017
    assert len(repository.landmarks()) == 40


def test_artifact_startup_contract_declares_required_fields():
    module = _require_module("wayfinding.demo.artifact")

    assert module.REQUIRED_FIELDS == {
        "facility_26910": {"facility_id", "code", "name"},
        "level_26910": {"level_id", "facility_id", "short_name", "vertical_order"},
        "unit_26910": {
            "unit_id", "room_id", "level_id", "use_type", "category", "accessible",
            "verified_by", "verified_date",
        },
        "detail_26910": {"detail_id", "use_type", "level_id"},
        "landmark_26910": {"landmark_id", "category", "level_id"},
    }


def test_artifact_startup_rejects_a_layer_missing_a_required_field(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    module = _require_module("wayfinding.demo.artifact")
    layers = []
    for layer_name, required_fields in module.REQUIRED_FIELDS.items():
        fields = sorted(required_fields)
        if layer_name == "unit_26910":
            fields.remove("verified_date")
        definition = Mock()
        definition.GetFieldCount.return_value = len(fields)
        definition.GetFieldDefn.side_effect = [
            Mock(GetName=Mock(return_value=field_name)) for field_name in fields
        ]
        layer = Mock()
        layer.GetName.return_value = layer_name
        layer.GetLayerDefn.return_value = definition
        layers.append(layer)
    dataset = Mock()
    dataset.GetLayerCount.return_value = len(layers)
    dataset.GetLayerByIndex.side_effect = lambda index: layers[index]
    monkeypatch.setattr(module.ogr, "Open", Mock(return_value=dataset))
    artifact_path = tmp_path / "incomplete.gpkg"
    artifact_path.write_bytes(b"incomplete schema fixture")

    with pytest.raises(module.ArtifactUnavailableError, match="schema is incomplete"):
        module.ArtifactRepository(artifact_path)


def test_real_level_scene_is_nonempty_exactly_filtered_and_allowlisted():
    repository = _repository()
    level_id = "SFU_BURNABY_QUAD_2000"

    scene = repository.scene(level_id)

    assert scene["level"]["level_id"] == level_id
    assert scene["crs"] == "EPSG:26910"
    assert scene["level"]["geometry"]
    assert scene["units"], "AQ 2000 must render real searchable room geometry"
    assert scene["details"], "AQ 2000 must render real architectural linework"
    for collection in ("units", "details", "landmarks"):
        assert all(item["level_id"] == level_id for item in scene[collection])

    assert set(scene["level"]) == {
        "level_id", "facility_id", "short_name", "vertical_order", "geometry"
    }
    assert all(
        set(unit) <= {
            "unit_id", "room_id", "level_id", "use_type", "category", "accessible",
            "verified_by", "verified_date", "geometry",
        }
        for unit in scene["units"]
    )
    assert all(
        set(detail) <= {"detail_id", "use_type", "level_id", "geometry"}
        for detail in scene["details"]
    )
    assert all(
        set(landmark) <= {"landmark_id", "category", "level_id", "geometry"}
        for landmark in scene["landmarks"]
    )


def test_scene_http_provenance_names_every_contributing_layer():
    with _running_server() as base_url:
        with urllib.request.urlopen(
            f"{base_url}/demo/v1/levels/SFU_BURNABY_QUAD_2000/scene"
        ) as response:
            body = json.load(response)

    assert {item["layer"] for item in body["provenance"]} == {
        "level_26910", "unit_26910", "detail_26910", "landmark_26910"
    }


@pytest.mark.parametrize(
    ("path", "method", "body", "expected_status"),
    [
        ("/demo/v1/assistant", "GET", None, 405),
        ("/demo/v1/health", "POST", b"{}", 405),
        ("/demo/v1/health", "TRACE", None, 405),
        ("/demo/v1/assistant", "POST", b"{", 400),
        ("/demo/v1/assistant", "POST", b"x" * 4097, 413),
        ("/../README.md", "GET", None, 404),
        ("/v1/health", "GET", None, 404),
    ],
)
def test_http_contract_rejects_invalid_methods_bodies_and_paths(
    path: str,
    method: str,
    body: bytes | None,
    expected_status: int,
):
    with _running_server() as base_url:
        status, response = _request_json(
            base_url,
            path,
            method=method,
            body=body,
        )

    assert status == expected_status
    assert response["artifact_sha256"] == hashlib.sha256(GPKG_PATH.read_bytes()).hexdigest()
    assert response["limitations_id"] == LIMITATION_ID


def test_exact_real_room_lookup_and_assistant_search_are_deterministic():
    repository = _repository()
    assistant_module = _require_module("wayfinding.demo.assistant")
    expected = _first_real_room()

    unit = repository.unit(expected["unit_id"])
    first = assistant_module.respond(repository, expected["room_id"])
    second = assistant_module.respond(repository, f"  {expected['room_id'].lower()}  ")

    for field, value in expected.items():
        assert unit[field] == value
    assert first == second
    assert first["kind"] == "room_match"
    assert first["entities"] == [
        {
            "type": "unit",
            "unit_id": expected["unit_id"],
            "room_id": expected["room_id"],
            "level_id": expected["level_id"],
        }
    ]
    assert first["evidence"]
    assert all(item["artifact_sha256"] for item in first["evidence"])
    assert all(item["layer"] == "unit_26910" for item in first["evidence"])


@pytest.mark.parametrize(
    ("message", "expected_kind", "expected_layer"),
    [
        ("List facilities", "facility_list", "facility_26910"),
        ("List floors", "level_list", "level_26910"),
        ("List landmarks", "landmark_list", "landmark_26910"),
        ("office", "choices", "unit_26910"),
    ],
)
def test_assistant_supported_intents_are_bounded_and_cite_real_layers(
    message: str,
    expected_kind: str,
    expected_layer: str,
):
    response = _require_module("wayfinding.demo.assistant").respond(_repository(), message)

    assert response["kind"] == expected_kind
    assert 0 < len(response["entities"]) <= 40
    assert response["evidence"]
    assert {item["layer"] for item in response["evidence"]} == {expected_layer}


def test_assistant_treats_markup_as_literal_text_and_http_reports_real_evidence():
    repository = _repository()
    assistant = _require_module("wayfinding.demo.assistant")

    unknown = assistant.respond(repository, "<script>alert(1)</script>")
    assert unknown["kind"] == "unknown"
    assert unknown["entities"] == []
    with _running_server() as base_url:
        status, response = _request_json(
            base_url,
            "/demo/v1/assistant",
            method="POST",
            body=json.dumps({"message": "AQ1002"}).encode(),
        )

    assert status == 200
    assert response["artifact_sha256"] == repository.artifact_sha256
    assert {item["layer"] for item in response["provenance"]} == {"unit_26910"}


@pytest.mark.parametrize(
    ("message", "required_text", "mobility"),
    [
        ("Route me to AQ 3003", "Routing is not available in this demo", False),
        ("What is the nearest washroom?", "Nearest-place search is not available", False),
        (
            "Find me a wheelchair accessible path to an elevator",
            "Routing is not available in this demo",
            True,
        ),
    ],
)
def test_assistant_refuses_unimplemented_navigation_without_route_claims(
    message: str,
    required_text: str,
    mobility: bool,
):
    repository = _repository()
    assistant_module = _require_module("wayfinding.demo.assistant")

    response = assistant_module.respond(repository, message)

    assert response["kind"] == "refusal"
    assert required_text in response["text"]
    assert response["limitations_id"] == LIMITATION_ID
    for forbidden in ("route", "geometry", "distance", "travel_time", "steps"):
        assert forbidden not in response
    assert response.get("generated_by") not in {"llm", "ai", "model"}
    if mobility:
        assert "no path can be certified" in response["text"].lower()
        assert set(response["not_verified"]) == NOT_VERIFIED
        assert "elevator-only routing is not implemented" in response["text"].lower()
