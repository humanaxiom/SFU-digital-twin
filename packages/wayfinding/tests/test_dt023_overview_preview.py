"""Opt-in RoomFinder footprint admission and default-pilot isolation."""

import hashlib
import json
import threading

import pytest
import rfc8785
from test_dt023_campus import GPKG, request

from wayfinding.demo.artifact import ArtifactRepository, ArtifactUnavailableError
from wayfinding.demo.server import create_server

SOURCE = "https://viewsfu-prd.its.sfu.ca/fsgis/rest/services/RoomFinder/RoomFinder2023_CampusMap/MapServer/0/query"


def envelope():
    from wayfinding.overview_footprint import screen

    native = {
        "geometryType": "esriGeometryPolygon",
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "features": [
            {
                "attributes": {
                    "OBJECTID": 9,
                    "Abbr": "ASB",
                    "bl_id": "038",
                    "Campus": "Burnaby",
                    "Name": "Applied Sciences Building",
                    "Building": "Applied Sciences Building",
                },
                "geometry": {
                    "rings": [
                        [
                            [-13683000, 6320000],
                            [-13683000, 6320010],
                            [-13682990, 6320010],
                            [-13682990, 6320000],
                            [-13683000, 6320000],
                        ]
                    ]
                },
            }
        ],
    }
    return screen(native, [9])


def seal(value):
    value.pop("screen_sha256", None)
    value["screen_sha256"] = hashlib.sha256(rfc8785.dumps(value)).hexdigest()
    return value


def write(tmp_path, value):
    path = tmp_path / "screen.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_preview_is_explicit_and_never_adds_indoor_coverage(tmp_path):
    pilot = ArtifactRepository(GPKG)
    baseline = pilot.campus_overview()
    evidence = envelope()
    repository = ArtifactRepository(GPKG, overview_footprint_path=write(tmp_path, evidence))
    campus = repository.campus_overview()
    assert campus["scope"] == "burnaby-overview-preview"
    asb = next(f for f in campus["facilities"] if f["code"] == "ASB")
    assert asb["facility_id"] == "ROOMFINDER_BURNABY_038"
    assert asb["coverage"] == "overview_only"
    assert asb["name"] == "Applied Sciences Building"
    assert campus["provenance"]["overview_footprints"] == [asb["provenance"]]
    assert asb["levels"] == asb["known_entrances"] == []
    assert asb["verified_building_destination"] is False
    assert asb["outdoor_routing"] == "unavailable"
    assert asb["provenance"]["source_url"] == SOURCE
    assert asb["provenance"]["screen_sha256"] == evidence["screen_sha256"]
    assert asb["geometry"] == evidence["footprint_26910"]["geometry"]
    assert len(repository.facilities()) == 4
    assert repository.levels(asb["facility_id"]) == []
    assert repository.levels() == pilot.levels()
    assert pilot.campus_overview() == baseline
    assert len(baseline["facilities"]) == 3


@pytest.mark.parametrize("mutation", ["digest", "scope", "identity", "crs", "bounds", "invalid"])
def test_preview_rejects_changed_or_unusable_envelopes(tmp_path, mutation):
    value = envelope()
    if mutation == "digest":
        value["screen_sha256"] = "0" * 64
    if mutation == "scope":
        value["review_scope"] = "routing"
    if mutation == "identity":
        value["native_response"]["features"][0]["attributes"]["bl_id"] = "039"
    if mutation == "crs":
        value["footprint_26910"]["crs"] = "EPSG:4326"
    if mutation == "bounds":
        value["footprint_26910"]["bounds"] = [0, 0, 1, 1]
    if mutation == "invalid":
        value["footprint_26910"]["geometry"]["coordinates"] = [
            [[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]
        ]
    if mutation != "digest":
        seal(value)
    with pytest.raises(ArtifactUnavailableError):
        ArtifactRepository(GPKG, overview_footprint_path=write(tmp_path, value))


def test_preview_http_facility_discovery_and_empty_levels(tmp_path):
    instance = create_server(
        "127.0.0.1", 0, GPKG, overview_footprint_path=write(tmp_path, envelope())
    )
    worker = threading.Thread(target=instance.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{instance.server_address[1]}"
        status, campus = request(base, "/demo/v1/campus")
        assert status == 200
        assert len(campus["facilities"]) == 4
        status, facilities = request(base, "/demo/v1/facilities")
        assert status == 200
        assert len(facilities["facilities"]) == 4
        assert facilities["provenance"] == campus["provenance"]
        status, levels = request(base, "/demo/v1/levels?facility_id=ROOMFINDER_BURNABY_038")
        assert status == 200
        assert levels["levels"] == []
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(timeout=5)


def test_preview_assistant_retains_artifact_only_evidence(tmp_path):
    from wayfinding.demo.assistant import respond

    repository = ArtifactRepository(GPKG, overview_footprint_path=write(tmp_path, envelope()))
    response = respond(repository, "List buildings")
    assert len(response["entities"]) == 3
    assert all(item["facility_id"] != "ROOMFINDER_BURNABY_038" for item in response["entities"])
