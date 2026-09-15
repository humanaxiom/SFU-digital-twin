"""DT-023 campus overview contract tests."""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[3]
GPKG = ROOT / "build" / "wayfinding.gpkg"


def request(base: str, path: str, method: str = "GET") -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(base + path, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@contextmanager
def server():
    from wayfinding.demo.server import create_server

    instance = create_server("127.0.0.1", 0, GPKG)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = instance.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_campus_overview_is_deterministic_and_has_exact_pilot_geometry():
    from wayfinding.demo.artifact import ArtifactRepository

    repository = ArtifactRepository(GPKG)
    first = repository.campus_overview()
    second = repository.campus_overview()
    assert first == second
    assert first["version"] == "campus-overview-v1"
    assert first["crs"] == "EPSG:26910"
    assert first["scope"] == "three-building-pilot"
    assert first["campus_inventory_complete"] is False
    assert [item["code"] for item in first["facilities"]] == ["AQ", "ECC", "SH"]
    assert all(item["geometry_status"] == "available" for item in first["facilities"])
    assert all(item["verified_building_destination"] is False for item in first["facilities"])
    assert all(item["outdoor_routing"] == "unavailable" for item in first["facilities"])
    assert first["provenance"] == repository.provenance("facility_26910")
    assert hashlib.sha256(GPKG.read_bytes()).hexdigest() == first["provenance"]["artifact_sha256"]

    ogr = pytest.importorskip("osgeo.ogr")
    dataset = ogr.Open(str(GPKG), 0)
    expected = {
        feature.GetField("facility_id"): json.loads(feature.GetGeometryRef().ExportToJson())
        for feature in dataset.GetLayerByName("facility_26910")
    }
    dataset = None
    for item in first["facilities"]:
        assert item["geometry"] == expected[item["facility_id"]]
        assert item["levels"] == repository.levels(item["facility_id"])
        assert item["coverage"] == ("partial_indoor" if item["levels"] else "overview_only")


def test_campus_overview_http_get_and_method_guard():
    with server() as base:
        status, body = request(base, "/demo/v1/campus")
        assert status == 200
        assert body["version"] == "campus-overview-v1"
        assert body["limitations"]
        status, error = request(base, "/demo/v1/campus", "POST")
    assert status == 405
    assert error["limitations_id"] == "phase1-artifact-only"


def test_campus_overview_null_geometry_is_retained_and_excluded_from_bounds():
    from wayfinding.demo.artifact import ArtifactRepository

    pytest.importorskip("osgeo.ogr")
    # Repository mutation is intentionally avoided; this contract is exercised by
    # the implementation's geometry helper with null source records.
    repository = ArtifactRepository(GPKG)
    assert repository._campus_geometry_bounds(None) is None
    assert repository._campus_geometry_bounds({"type": "Point", "coordinates": [1, 2]}) is None
    assert repository._campus_geometry_bounds(
        {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 3], [0, 0]]]}
    ) == [0.0, 0.0, 2.0, 3.0]


def test_malformed_rings_nonfinite_values_and_self_intersections_are_unavailable(monkeypatch):
    from wayfinding.demo.artifact import ArtifactRepository

    class Geometry:
        def __init__(self, value):
            self.value = value

        def ExportToJson(self):  # noqa: N802
            return json.dumps(self.value, allow_nan=True)

    class Feature:
        def __init__(self, facility_id, code, name, geometry):
            self.fields = {"facility_id": facility_id, "code": code, "name": name}
            self.geometry = Geometry(geometry) if geometry is not None else None

        def GetField(self, name):  # noqa: N802
            return self.fields[name]

        def GetGeometryRef(self):  # noqa: N802
            return self.geometry

    class Layer:
        def __iter__(self):
            return iter(features)

    class Dataset:
        def GetLayerByName(self, name):  # noqa: N802
            assert name == "facility_26910"
            return Layer()

    valid = {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 3], [0, 0]]]}
    open_ring = {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 3], [0, 3]]]}
    nonfinite = {"type": "Polygon", "coordinates": [[[0, 0], [float("nan"), 0], [3, 3], [0, 0]]]}
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [3, 3], [0, 3], [3, 0], [0, 0]]]}
    features = [
        Feature("valid", "V", "Valid", valid),
        Feature("open", "O", "Open", open_ring),
        Feature("nan", "N", "Nonfinite", nonfinite),
        Feature("bowtie", "B", "Bowtie", bowtie),
        Feature("missing", "M", "Missing", None),
    ]
    repository = ArtifactRepository(GPKG)
    monkeypatch.setattr(repository, "_dataset", lambda: Dataset())
    monkeypatch.setattr(repository, "levels", lambda facility_id=None: [])
    result = repository.campus_overview()
    assert result["bounds"] == [0.0, 0.0, 3.0, 3.0]
    by_id = {item["facility_id"]: item for item in result["facilities"]}
    assert by_id["valid"]["geometry_status"] == "available"
    assert by_id["valid"]["bounds"] == [0.0, 0.0, 3.0, 3.0]
    for facility_id in ("open", "nan", "bowtie", "missing"):
        assert by_id[facility_id]["geometry_status"] == "unavailable"
        assert by_id[facility_id]["bounds"] is None
        assert by_id[facility_id]["geometry"] is None
        assert by_id[facility_id]["coverage"] == "overview_only"
    assert by_id["missing"]["geometry"] is None
