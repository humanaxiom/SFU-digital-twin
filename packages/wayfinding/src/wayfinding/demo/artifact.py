"""Read-only access to the normalized DT-013 demonstration artifact."""

from __future__ import annotations

import hashlib
import json
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
