"""Shared read-only screening for the public Burnaby ASB footprint."""

import hashlib
import json
import math

import rfc8785
from osgeo import gdal, ogr, osr

SOURCE = (
    "https://viewsfu-prd.its.sfu.ca/fsgis/rest/services/"
    "RoomFinder/RoomFinder2023_CampusMap/MapServer/0/query"
)
WHERE = "Abbr = 'ASB'"
FIELDS = "OBJECTID,Abbr,bl_id,Name,Building,Campus"
IDS_QUERY = {"where": WHERE, "returnIdsOnly": "true", "f": "json"}
FEATURE_QUERY = {"where": WHERE, "outFields": FIELDS, "returnGeometry": "true", "f": "json"}
MAX_BYTES = 1024 * 1024


def _digest(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _project_footprint(response):
    native_crs = response.get("spatialReference")
    if not isinstance(native_crs, dict) or native_crs.get("wkid") not in (102100, 3857):
        raise ValueError("RoomFinder did not attest its native EPSG:3857 CRS")
    if native_crs.get("latestWkid", 3857) != 3857:
        raise ValueError("RoomFinder returned conflicting native CRS identifiers")

    if response.get("geometryType") != "esriGeometryPolygon":
        raise ValueError("RoomFinder did not return a polygon feature set")
    geometry = response["features"][0].get("geometry")
    rings = geometry.get("rings") if isinstance(geometry, dict) else None
    if not isinstance(rings, list) or not rings:
        raise ValueError("RoomFinder returned no polygon rings")
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("RoomFinder returned a malformed polygon ring")
        for point in ring:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(type(value) in (int, float) and math.isfinite(value) for value in point)
            ):
                raise ValueError("RoomFinder returned an invalid polygon coordinate")

    with gdal.ExceptionMgr(), ogr.ExceptionMgr(), osr.ExceptionMgr():
        dataset = gdal.OpenEx(json.dumps(response), gdal.OF_VECTOR, allowed_drivers=["ESRIJSON"])
        layer = dataset.GetLayer()
        feature = layer.GetNextFeature()
        if feature is None or layer.GetNextFeature() is not None:
            raise ValueError("GDAL could not read the expected one-feature polygon set")
        footprint = feature.GetGeometryRef()
        if footprint is None or footprint.GetGeometryName() not in ("POLYGON", "MULTIPOLYGON"):
            raise ValueError("GDAL could not read the footprint polygon")
        if footprint.IsEmpty() or not footprint.IsValid():
            raise ValueError("RoomFinder returned an empty or invalid native polygon")

        source = osr.SpatialReference()
        source.ImportFromEPSG(3857)
        target = osr.SpatialReference()
        target.ImportFromEPSG(26910)
        for crs in (source, target):
            crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        footprint.Transform(osr.CoordinateTransformation(source, target))
        min_x, max_x, min_y, max_y = footprint.GetEnvelope()
        bounds = [min_x, min_y, max_x, max_y]
        area = footprint.GetArea()
        if not footprint.IsValid() or not all(map(math.isfinite, [*bounds, area])) or area <= 0:
            raise ValueError("RoomFinder footprint is invalid in EPSG:26910")
        projected = json.loads(footprint.ExportToJson())

    polygons = projected["coordinates"]
    if projected["type"] == "Polygon":
        polygons = [polygons]
    if sorted(map(len, rings)) != sorted(len(ring) for polygon in polygons for ring in polygon):
        raise ValueError("GDAL changed the polygon ring and vertex counts")
    return {"crs": "EPSG:26910", "geometry": projected, "bounds": bounds, "area_m2": area}


def screen(response, object_ids):
    """Validate one complete response, keeping its unmodified native payload."""
    if response.get("exceededTransferLimit", False) is not False:
        raise ValueError("RoomFinder returned an incomplete feature set")
    if (
        not isinstance(object_ids, list)
        or len(object_ids) != 1
        or type(object_ids[0]) is not int
        or object_ids[0] <= 0
    ):
        raise ValueError("RoomFinder must return exactly one positive integer object ID")
    features = response.get("features")
    if not isinstance(features, list) or len(features) != 1 or not isinstance(features[0], dict):
        raise ValueError("RoomFinder must return exactly one footprint record")
    attributes = features[0].get("attributes")
    if not isinstance(attributes, dict):
        raise ValueError("RoomFinder footprint record is missing identity attributes")
    object_id = attributes.get("OBJECTID")
    if type(object_id) is not int or object_ids != [object_id]:
        raise ValueError("RoomFinder feature and object ID queries disagree")
    if (attributes.get("Abbr"), attributes.get("bl_id"), attributes.get("Campus")) != (
        "ASB",
        "038",
        "Burnaby",
    ):
        raise ValueError("RoomFinder footprint record does not identify Burnaby ASB building 038")
    for field in ("Name", "Building"):
        if not isinstance(attributes.get(field), str) or not attributes[field].strip():
            raise ValueError(f"RoomFinder footprint record is missing {field}")

    evidence = {
        "version": "dt023-asb-footprint-screen-v1",
        "source_url": SOURCE,
        "queries": {"object_ids": IDS_QUERY, "feature": FEATURE_QUERY},
        "review_scope": "footprint_only",
        "object_ids": object_ids,
        "native_response": response,
        "native_response_sha256": _digest(response),
        "footprint_26910": _project_footprint(response),
    }
    return {**evidence, "screen_sha256": _digest(evidence)}


def validate_screen(value):
    """Verify the JCS seal and reproduce every screened field from native evidence."""
    evidence = dict(value)
    digest = evidence.pop("screen_sha256")
    if _digest(evidence) != digest:
        raise ValueError("Footprint screen digest mismatch")
    expected = screen(evidence["native_response"], evidence["object_ids"])
    if value != expected:
        raise ValueError("Footprint screen does not reproduce from its native evidence")
    return expected
