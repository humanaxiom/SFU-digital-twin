#!/usr/bin/env python3
"""Offline regression cases for the ASB public footprint intake."""

import copy
import json

import burnaby_footprint as intake
import pytest


@pytest.fixture
def response():
    return {
        "geometryType": "esriGeometryPolygon",
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "features": [
            {
                "attributes": {
                    "OBJECTID": 7,
                    "Abbr": "ASB",
                    "bl_id": "038",
                    "Name": "Applied Science Building",
                    "Building": "APPLIED SCIENCE",
                    "Campus": "Burnaby",
                },
                "geometry": {
                    "rings": [[
                        [-13682270, 6318540], [-13682270, 6318570],
                        [-13682240, 6318570], [-13682240, 6318540],
                        [-13682270, 6318540],
                    ]],
                },
            },
        ],
    }


def test_geometry_and_identity_are_retained(response):
    evidence = intake.screen(response, [7])
    assert evidence["native_response"] == response
    assert evidence["object_ids"] == [7]
    polygon = evidence["footprint_26910"]
    assert polygon["geometry"]["type"] == "Polygon"
    assert len(polygon["geometry"]["coordinates"][0]) == 5
    assert 300 < polygon["area_m2"] < 500
    assert polygon["bounds"][0] < polygon["bounds"][2]
    assert polygon["bounds"][1] < polygon["bounds"][3]
    reordered = json.loads(json.dumps(response, sort_keys=True))
    assert intake.screen(reordered, [7])["screen_sha256"] == evidence["screen_sha256"]


@pytest.mark.parametrize("object_ids", [[], [7, 7], [7, 8], [8], [True]])
def test_missing_duplicate_or_inconsistent_identity_fails(response, object_ids):
    with pytest.raises(ValueError, match="object ID"):
        intake.screen(response, object_ids)


def test_duplicate_geometry_records_fail(response):
    response["features"].append(copy.deepcopy(response["features"][0]))
    with pytest.raises(ValueError, match="exactly one"):
        intake.screen(response, [7])


def test_partial_results_fail(response):
    response["exceededTransferLimit"] = True
    with pytest.raises(ValueError, match="incomplete"):
        intake.screen(response, [7])


def test_other_campus_fails(response):
    response["features"][0]["attributes"]["Campus"] = "Surrey"
    with pytest.raises(ValueError, match="Burnaby"):
        intake.screen(response, [7])


def test_missing_coordinate_system_fails(response):
    del response["spatialReference"]
    with pytest.raises(ValueError, match="CRS"):
        intake.screen(response, [7])


def test_invalid_geometry_fails(response):
    ring = response["features"][0]["geometry"]["rings"][0]
    ring[1], ring[2] = ring[2], ring[1]
    with pytest.raises(ValueError, match="polygon"):
        intake.screen(response, [7])
