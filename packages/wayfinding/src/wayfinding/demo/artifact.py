"""Read-only access to the normalized DT-013 demonstration artifact."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from osgeo import ogr

REQUIRED_FIELDS = {
    "facility_26910": {"facility_id", "code", "name"},
    "level_26910": {"level_id", "facility_id", "short_name", "vertical_order"},
    "unit_26910": {
        "unit_id",
        "room_id",
        "level_id",
        "use_type",
        "category",
        "accessible",
        "verified_by",
        "verified_date",
    },
    "detail_26910": {"detail_id", "use_type", "level_id"},
    "landmark_26910": {"landmark_id", "category", "level_id"},
}
REQUIRED_LAYERS = set(REQUIRED_FIELDS)


class ArtifactUnavailableError(RuntimeError):
    """Raised when the approved artifact cannot be read safely."""


class RecordNotFoundError(LookupError):
    """Raised when a requested public artifact record does not exist."""


def _geometry(feature: Any) -> dict[str, Any] | None:
    value = feature.GetGeometryRef()
    return json.loads(value.ExportToJson()) if value is not None else None


def _fields(feature: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {name: feature.GetField(name) for name in names}


def _accessible(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


class ArtifactRepository:
    """Expose the narrow, public DT-013 view of a normalized GeoPackage."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise ArtifactUnavailableError("The normalized demo artifact is unavailable.")
        dataset = ogr.Open(str(self.path), 0)
        if dataset is None:
            raise ArtifactUnavailableError("The normalized demo artifact could not be opened.")
        layers = {
            dataset.GetLayerByIndex(index).GetName(): dataset.GetLayerByIndex(index)
            for index in range(dataset.GetLayerCount())
        }
        if not REQUIRED_LAYERS <= set(layers):
            dataset = None
            raise ArtifactUnavailableError("The normalized demo artifact is incomplete.")
        for layer_name, required_fields in REQUIRED_FIELDS.items():
            definition = layers[layer_name].GetLayerDefn()
            actual_fields = {
                definition.GetFieldDefn(index).GetName()
                for index in range(definition.GetFieldCount())
            }
            if not required_fields <= actual_fields:
                dataset = None
                raise ArtifactUnavailableError(
                    "The normalized demo artifact schema is incomplete."
                )
        dataset = None
        self.artifact_sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def _dataset(self) -> Any:
        dataset = ogr.Open(str(self.path), 0)
        if dataset is None:
            raise ArtifactUnavailableError("The normalized demo artifact is unavailable.")
        return dataset

    def facilities(self) -> list[dict[str, Any]]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("facility_26910")
        records = [_fields(feature, ("facility_id", "code", "name")) for feature in layer]
        dataset = None
        return sorted(records, key=lambda item: (item["name"] or "", item["facility_id"]))

    @staticmethod
    def _campus_geometry_bounds(geometry: dict[str, Any] | None) -> list[float] | None:
        """Return bounds only for finite Polygon/MultiPolygon GeoJSON geometry."""
        if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            return None
        coordinates = geometry.get("coordinates")
        polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
        if not isinstance(polygons, list) or not polygons:
            return None
        values: list[tuple[float, float]] = []

        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                return None
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4:
                    return None
                if any(
                    not isinstance(position, list)
                    or len(position) < 2
                    or any(
                        isinstance(item, bool)
                        or not isinstance(item, (int, float))
                        or not math.isfinite(item)
                        for item in position
                    )
                    for position in ring
                ):
                    return None
                if ring[0][:2] != ring[-1][:2]:
                    return None
                values.extend((float(position[0]), float(position[1])) for position in ring)
        if not values:
            return None
        xs, ys = zip(*values, strict=True)
        return [min(xs), min(ys), max(xs), max(ys)]

    def campus_overview(self) -> dict[str, Any]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("facility_26910")
        facilities: list[dict[str, Any]] = []
        all_bounds: list[list[float]] = []
        for feature in layer:
            facility_id = feature.GetField("facility_id")
            geometry = _geometry(feature)
            bounds = self._campus_geometry_bounds(geometry)
            if bounds is not None:
                ogr_geometry = ogr.CreateGeometryFromJson(json.dumps(geometry))
                if ogr_geometry is None or not ogr_geometry.IsValid():
                    bounds = None
            if bounds is None:
                geometry = None
            if bounds is not None:
                all_bounds.append(bounds)
            levels = self.levels(facility_id)
            facilities.append(
                {
                    "facility_id": facility_id,
                    "code": feature.GetField("code"),
                    "name": feature.GetField("name"),
                    "geometry": geometry,
                    "bounds": bounds,
                    "levels": levels,
                    "coverage": "partial_indoor" if levels else "overview_only",
                    "geometry_status": "available" if bounds is not None else "unavailable",
                    "known_entrances": [],
                    "verified_building_destination": False,
                    "outdoor_routing": "unavailable",
                }
            )
        dataset = None
        campus_bounds = None
        if all_bounds:
            campus_bounds = [
                min(item[0] for item in all_bounds),
                min(item[1] for item in all_bounds),
                max(item[2] for item in all_bounds),
                max(item[3] for item in all_bounds),
            ]
        facilities.sort(key=lambda item: (item["name"] or "", item["facility_id"] or ""))
        return {
            "version": "campus-overview-v1",
            "crs": "EPSG:26910",
            "scope": "three-building-pilot",
            "campus_inventory_complete": False,
            "facilities": facilities,
            "bounds": campus_bounds,
            "provenance": self.provenance("facility_26910"),
            "limitations": [
                "Pilot inventory is incomplete for the Burnaby campus.",
                "No verified outdoor or building destinations are available.",
                "Indoor coverage is not full routing coverage.",
            ],
        }

    def levels(self, facility_id: str | None = None) -> list[dict[str, Any]]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("level_26910")
        records = []
        for feature in layer:
            item = _fields(feature, ("level_id", "facility_id", "short_name", "vertical_order"))
            if facility_id is None or item["facility_id"] == facility_id:
                records.append(item)
        dataset = None
        return sorted(
            records,
            key=lambda item: (item["vertical_order"], item["facility_id"], item["short_name"]),
        )

    def scene(self, level_id: str) -> dict[str, Any]:
        dataset = self._dataset()
        level_layer = dataset.GetLayerByName("level_26910")
        level = None
        for feature in level_layer:
            if feature.GetField("level_id") == level_id:
                level = _fields(
                    feature,
                    ("level_id", "facility_id", "short_name", "vertical_order"),
                )
                level["geometry"] = _geometry(feature)
                break
        if level is None:
            dataset = None
            raise RecordNotFoundError("Level not found.")

        units = self._level_features(
            dataset,
            "unit_26910",
            level_id,
            (
                "unit_id",
                "room_id",
                "level_id",
                "use_type",
                "category",
                "accessible",
                "verified_by",
                "verified_date",
            ),
        )
        for unit in units:
            unit["accessible"] = _accessible(unit["accessible"])
        details = self._level_features(
            dataset,
            "detail_26910",
            level_id,
            ("detail_id", "use_type", "level_id"),
        )
        landmarks = self._level_features(
            dataset,
            "landmark_26910",
            level_id,
            ("landmark_id", "category", "level_id"),
        )
        dataset = None
        return {
            "crs": "EPSG:26910",
            "level": level,
            "units": units,
            "details": details,
            "landmarks": landmarks,
        }

    @staticmethod
    def _level_features(
        dataset: Any,
        layer_name: str,
        level_id: str,
        names: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        records = []
        for feature in dataset.GetLayerByName(layer_name):
            if feature.GetField("level_id") != level_id:
                continue
            item = _fields(feature, names)
            item["geometry"] = _geometry(feature)
            records.append(item)
        return records

    def unit(self, unit_id: str) -> dict[str, Any]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("unit_26910")
        for feature in layer:
            if feature.GetField("unit_id") == unit_id:
                item = _fields(
                    feature,
                    (
                        "unit_id",
                        "room_id",
                        "level_id",
                        "use_type",
                        "category",
                        "accessible",
                        "verified_by",
                        "verified_date",
                    ),
                )
                item["accessible"] = _accessible(item["accessible"])
                item["provenance"] = self.provenance("unit_26910")
                dataset = None
                return item
        dataset = None
        raise RecordNotFoundError("Unit not found.")

    def units(self) -> list[dict[str, Any]]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("unit_26910")
        records = [
            _fields(feature, ("unit_id", "room_id", "level_id", "use_type", "category"))
            for feature in layer
        ]
        dataset = None
        return sorted(records, key=lambda item: ((item["room_id"] or ""), item["unit_id"]))

    def landmarks(self, level_id: str | None = None) -> list[dict[str, Any]]:
        dataset = self._dataset()
        layer = dataset.GetLayerByName("landmark_26910")
        records = []
        for feature in layer:
            item = _fields(feature, ("landmark_id", "category", "level_id"))
            if level_id is None or item["level_id"] == level_id:
                records.append(item)
        dataset = None
        return sorted(records, key=lambda item: (item["category"] or "", item["landmark_id"]))

    def provenance(self, layer: str) -> dict[str, str]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "layer": layer,
            "source": "normalized Phase 1 artifact derived from read-only AIIM source",
        }
