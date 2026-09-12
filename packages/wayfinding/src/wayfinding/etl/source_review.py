"""Read-only, snapshot-specific indoor source comparison; no data reconciliation."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from osgeo import ogr

NAMES = ("Facilities", "Levels", "Units", "Pathways", "Transitions", "Landmarks", "Details")


def hash_directory(path: Path) -> dict[str, Any]:
    """Hash all regular files using ADR-0006's relative-path manifest algorithm."""
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Source symlink is forbidden")
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_dir():
        raise ValueError("Source must be a directory")
    files = []
    for item in path.rglob("*"):
        if item.is_symlink():
            raise ValueError("Source symlink is forbidden")
        if item.is_file():
            files.append(item)
        elif not item.is_dir():
            raise ValueError("Source contains a non-regular file")
    if not files:
        raise ValueError("Source directory is empty")
    digest = hashlib.sha256()
    size = 0
    for item in sorted(files, key=lambda item: item.relative_to(path).as_posix()):
        file_digest = hashlib.sha256()
        with item.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                file_digest.update(chunk)
                size += len(chunk)
        name = item.relative_to(path).as_posix()
        digest.update(f"{name}\0{file_digest.hexdigest()}\n".encode())
    return {"sha256": digest.hexdigest(), "files": len(files), "bytes": size}


def _json_value(value: Any) -> Any:
    # Preserve unusual OGR scalar values without producing nonstandard JSON NaN.
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"binary_sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _metadata(layer: Any) -> dict[str, Any]:
    definition = layer.GetLayerDefn()
    fields = []
    for index in range(definition.GetFieldCount()):
        field = definition.GetFieldDefn(index)
        fields.append(
            {
                "name": field.GetName(),
                "type": field.GetTypeName(),
                "width": field.GetWidth(),
                "precision": field.GetPrecision(),
                "nullable": bool(field.IsNullable()),
            }
        )
    reference = layer.GetSpatialRef()
    return {
        "count": layer.GetFeatureCount(),
        "fields": sorted(fields, key=lambda f: f["name"]),
        "geometry_type": ogr.GeometryTypeToName(definition.GetGeomType()),
        "crs_wkt": reference.ExportToWkt() if reference is not None else None,
    }


def _rows(layer: Any) -> dict[int, dict[str, Any]]:
    rows = {}
    layer.ResetReading()
    for feature in layer:
        definition = feature.GetDefnRef()
        attributes = {
            definition.GetFieldDefn(i).GetName(): _json_value(feature.GetField(i))
            for i in range(definition.GetFieldCount())
        }
        geometry = feature.GetGeometryRef()
        wkb = bytes(geometry.ExportToWkb(ogr.wkbNDR)) if geometry is not None else b""
        attribute_hash = hashlib.sha256(
            json.dumps(attributes, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        geometry_hash = hashlib.sha256(wkb).hexdigest()
        fid = feature.GetFID()
        if fid in rows:
            raise ValueError("Duplicate source FID")
        rows[fid] = {
            "attributes": attributes,
            "geometry": geometry.Clone() if geometry else None,
            "attribute_sha256": attribute_hash,
            "geometry_sha256": geometry_hash,
            "fingerprint": hashlib.sha256(
                f"{attribute_hash}\0{geometry_hash}".encode()
            ).hexdigest(),
        }
    return rows


def _identity(fid: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fid": fid,
        **{name: row[name] for name in ("fingerprint", "attribute_sha256", "geometry_sha256")},
    }


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _line_reasons(geometry: Any) -> list[str]:
    if geometry is None or geometry.IsEmpty():
        return ["missing_geometry"]
    kind = ogr.GT_Flatten(geometry.GetGeometryType())
    if kind not in (ogr.wkbLineString, ogr.wkbMultiLineString):
        return ["unsupported_geometry"]
    parts = (
        [geometry]
        if kind == ogr.wkbLineString
        else [geometry.GetGeometryRef(i) for i in range(geometry.GetGeometryCount())]
    )
    reasons = []
    previous = None
    geometry_length = 0.0
    for part in parts:
        points = part.GetPoints()
        if len(points) < 2:
            reasons.append("degenerate_geometry")
        if any(not all(math.isfinite(value) for value in point) for point in points):
            reasons.append("nonfinite_coordinates")
        geometry_length += sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
        if points:
            if previous is not None and previous != points[0]:
                reasons.append("discontinuous_multipart")
            previous = points[-1]
    # Include Z for vertical transitions; this never establishes floor identity.
    if not math.isfinite(geometry_length) or geometry_length <= 0:
        reasons.append("nonpositive_geometry_length")
    return reasons


def _diagnostics(
    snapshot: str, tables: dict[str, Any], names: dict[str, str]
) -> list[dict[str, Any]]:
    facilities = {
        row["attributes"].get("FACILITY_ID") for row in tables.get("Facilities", {}).values()
    }
    levels = {
        row["attributes"].get("LEVEL_ID"): row["attributes"].get("FACILITY_ID")
        for row in tables.get("Levels", {}).values()
    }
    identity_counts = {
        name: Counter(row["attributes"].get(field) for row in tables.get(name, {}).values())
        for name, field in (("Facilities", "FACILITY_ID"), ("Levels", "LEVEL_ID"))
    }
    diagnostics = []
    for name in NAMES:
        for fid, row in sorted(tables.get(name, {}).items()):
            attrs = row["attributes"]
            reasons = []
            facility = attrs.get("FACILITY_ID")
            # Units, Details and Landmarks normally reference facilities through Levels.
            # Validate a direct facility relationship only where the schema declares it.
            has_facility = name in ("Facilities", "Levels", "Pathways", "Transitions") or (
                "FACILITY_ID" in attrs
            )
            if name == "Facilities" and identity_counts[name][facility] > 1:
                reasons.append("duplicate_facility_id")
            if name == "Levels" and identity_counts[name][attrs.get("LEVEL_ID")] > 1:
                reasons.append("duplicate_level_id")
            if has_facility and _missing(facility):
                reasons.append("missing_facility_id")
            elif has_facility and name != "Facilities" and facility not in facilities:
                reasons.append("orphan_facility_id")
            if name == "Levels":
                order = attrs.get("VERTICAL_ORDER")
                if (
                    not isinstance(order, (int, float))
                    or not math.isfinite(order)
                    or int(order) != order
                ):
                    reasons.append("invalid_vertical_order")
            if name not in ("Facilities", "Transitions"):
                level = attrs.get("LEVEL_ID")
                if _missing(level):
                    reasons.append("missing_level_id")
                elif name != "Levels" and level not in levels:
                    reasons.append("orphan_level_id")
                elif has_facility and level in levels and levels[level] != facility:
                    reasons.append("facility_level_mismatch")
            if name in ("Pathways", "Transitions"):
                length = attrs.get("LENGTH_3D")
                if not isinstance(length, (int, float)) or not math.isfinite(length) or length <= 0:
                    reasons.append("invalid_length_3d")
                if attrs.get("TRAVEL_DIRECTION") != 1:
                    reasons.append("unsupported_travel_direction")
                reasons.extend(_line_reasons(row["geometry"]))
            if name == "Transitions":
                if attrs.get("TRANSITION_TYPE") not in (2, 4):
                    reasons.append("unsupported_transition_type")
                for side in ("FROM", "TO"):
                    level_name = attrs.get(f"LEVEL_NAME_{side}")
                    level = f"{facility}_{level_name}"
                    if _missing(level_name):
                        reasons.append(f"missing_level_name_{side.lower()}")
                    elif level not in levels:
                        reasons.append(f"orphan_level_{side.lower()}")
                    elif levels[level] != facility:
                        reasons.append("facility_level_mismatch")
            if reasons:
                diagnostics.append(
                    {
                        "snapshot": snapshot,
                        "layer": names[name],
                        **_identity(fid, row),
                        "reasons": sorted(set(reasons)),
                    }
                )
    return diagnostics


def review_sources(legacy: Path, revised: Path, supplemental: Path) -> dict[str, Any]:
    """Compare all indoor features and inventory supplemental metadata, read-only.

    FID matching is specific to these snapshots; fingerprints expose attribute and WKB
    changes. This does not establish globally stable feature identity or route readiness.
    """
    paths = {"legacy": legacy, "revised": revised, "supplemental": supplemental}
    report: dict[str, Any] = {
        "schema_version": 1,
        "sources": {},
        "layers": {},
        "diagnostics": [],
        "build_readiness": {},
        "comparison_basis": (
            "source FID within these snapshots; attributes and raw little-endian WKB fingerprints; "
            "FIDs are not universally stable"
        ),
        "limitations": [
            "No source correction, exclusion, or ingestion",
            "No facility or level inferred from geometry or Z",
            "Source checks do not authorize promotion or certify routability",
            "discontinuous_multipart flags discontinuity in stored part order; "
            "it does not establish physical disconnection between parts",
        ],
    }
    datasets = {}
    snapshots = {}
    metadata = {}
    for snapshot, path in paths.items():
        report["sources"][snapshot] = {"name": path.name, **hash_directory(path)}
        dataset = ogr.Open(str(path), 0)
        if dataset is None:
            raise ValueError(f"Cannot open source: {path.name}")
        datasets[snapshot] = dataset
        if snapshot == "supplemental":
            report["supplemental"] = {
                "policy": "inventory only; no attribute values or attachment bytes",
                "layers": {
                    layer.GetName(): _metadata(layer)
                    for layer in sorted(dataset, key=lambda x: x.GetName())
                },
            }
            continue
        tables = {}
        layer_metadata = {}
        names = {
            name: f"{name}_AQ_SH_ECC"
            + ("_Revised" if snapshot == "revised" and name == "Pathways" else "")
            for name in NAMES
        }
        structural = []
        for name, source_name in names.items():
            layer = dataset.GetLayerByName(source_name)
            if layer is None:
                structural.append(f"missing_layer:{source_name}")
                tables[name] = {}
                layer_metadata[name] = None
                continue
            layer_metadata[name] = _metadata(layer)
            reference = layer.GetSpatialRef()
            if reference is None or reference.GetAuthorityCode("PROJCS") != "26910":
                structural.append(f"unsupported_crs:{source_name}")
            tables[name] = _rows(layer)
        diagnostics = _diagnostics(snapshot, tables, names)
        report["diagnostics"].extend(diagnostics)
        report["build_readiness"][snapshot] = {
            "status": "blocked" if diagnostics or structural else "source_checks_passed",
            "reason": "Source diagnostics require explicit review"
            if diagnostics or structural
            else "Source checks passed; isolated rebuild and separate acceptance still required",
            "diagnostic_features": len(diagnostics),
            "structural_issues": structural,
        }
        snapshots[snapshot] = tables
        metadata[snapshot] = layer_metadata
    for name in NAMES:
        before, after = snapshots["legacy"][name], snapshots["revised"][name]
        added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
        changed = [
            fid
            for fid in sorted(before.keys() & after.keys())
            if before[fid]["fingerprint"] != after[fid]["fingerprint"]
        ]
        left, right = metadata["legacy"][name], metadata["revised"][name]
        report["layers"][name] = {
            "source_layers": {
                "legacy": f"{name}_AQ_SH_ECC",
                "revised": f"{name}_AQ_SH_ECC" + ("_Revised" if name == "Pathways" else ""),
            },
            "metadata": {"legacy": left, "revised": right},
            "schema_changed": left is None
            or right is None
            or left["fields"] != right["fields"]
            or left["geometry_type"] != right["geometry_type"],
            "crs_changed": left is None or right is None or left["crs_wkt"] != right["crs_wkt"],
            "counts": {
                "legacy": len(before),
                "revised": len(after),
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
                "unchanged": len(before.keys() & after.keys()) - len(changed),
            },
            "changes": {
                "added": [_identity(fid, after[fid]) for fid in added],
                "removed": [_identity(fid, before[fid]) for fid in removed],
                "changed": [
                    {
                        "fid": fid,
                        "legacy": _identity(fid, before[fid]),
                        "revised": _identity(fid, after[fid]),
                    }
                    for fid in changed
                ],
            },
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("legacy", "revised", "supplemental", "output"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    output: Path = args.output
    if output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        parser.error("Output symlinks are forbidden")
    if output.exists():
        parser.error("Output already exists")
    paths = [args.legacy, args.revised, args.supplemental]
    if any(output.resolve().is_relative_to(path.resolve()) for path in paths):
        parser.error("Output must be outside every source")
    report = review_sources(*paths)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
