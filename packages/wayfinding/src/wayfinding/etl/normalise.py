"""Normalise extracted layers into production-ready tables.

This module transforms the 14 raw extracted layers from DT-003 into 6 normalised
tables (facility, level, unit, landmark, detail, door) stored as 12 dual-CRS
GeoPackage layers. Each table is persisted as <table>_26910 (EPSG:26910) and
<table>_wgs84 (EPSG:4326) layers.

Key invariants:
- Exact row counts: facility=3, level=11, unit=1017, landmark=40, detail=48728, door=6865
- Preserve source DETAIL_ID for details and doors
- Landmark IDs: LMK_<FID> from representative point after deduplication
- Greedy first-point-wins clustering for landmarks (0.5m threshold, sorted by category/level/X/Y)
- Accessibility provenance: verified_by="source_gdb_use_type", verified_date="2026-08-29"
- Idempotent overwrite of only normalised layers (preserve raw layers from DT-003)
"""

import json
import logging
import math
import subprocess
from pathlib import Path
from typing import Any

# Stable source GDB date for accessibility provenance (mtime 2026-08-29T01:44:22Z)
SOURCE_VERIFIED_DATE = "2026-08-29"
TOXIC_UNIT_ID = "SFU_BURNABY_QUAD_2000_2017"
TOXIC_UNIT_CENTROID_WKT = "POINT (506011.7248 5458491.1155)"

logger = logging.getLogger(__name__)


def normalise_facilities(gpkg_path: Path) -> int:
    """Normalise Facilities layer into facility table.

    Creates facility_26910 and facility_wgs84 layers with 3 rows (AQ, SH, ECC).

    Args:
        gpkg_path: Path to working GeoPackage (must contain Facilities_26910 and Facilities_wgs84)

    Returns:
        Number of facilities created (always 3)

    Raises:
        RuntimeError: If ogr2ogr command fails or row count is not 3
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    # Delete existing normalised layers if they exist (idempotent overwrite)
    _delete_layer_if_exists(gpkg_path, "facility_26910")
    _delete_layer_if_exists(gpkg_path, "facility_wgs84")

    # Create facility_26910 from Facilities_26910
    # Map: FACILITY_ID -> facility_id, NAME -> code, NAME_LONG -> name
    sql_26910 = """
        SELECT
            FACILITY_ID AS facility_id,
            NAME AS code,
            NAME_LONG AS name,
            Shape AS geom
        FROM Facilities_26910
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="facility_26910",
        sql=sql_26910,
        geom_type="MULTIPOLYGON25D",
        target_srs="EPSG:26910",
    )

    # Create facility_wgs84 from Facilities_wgs84 (2D)
    sql_wgs84 = """
        SELECT
            FACILITY_ID AS facility_id,
            NAME AS code,
            NAME_LONG AS name,
            Shape AS geom
        FROM Facilities_wgs84
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="facility_wgs84",
        sql=sql_wgs84,
        geom_type="MULTIPOLYGON",
        target_srs="EPSG:4326",
    )

    # Verify count
    count = _get_layer_count(gpkg_path, "facility_26910")
    if count != 3:
        raise RuntimeError(f"Expected 3 facilities, got {count}")

    return count


def normalise_levels(gpkg_path: Path) -> int:
    """Normalise Levels layer into level table.

    Creates level_26910 and level_wgs84 layers with 11 rows (6 AQ + 4 SH + 1 ECC).

    Args:
        gpkg_path: Path to working GeoPackage (must contain Levels_26910 and Levels_wgs84)

    Returns:
        Number of levels created (always 11)

    Raises:
        RuntimeError: If ogr2ogr command fails or row count is not 11
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    # Delete existing normalised layers if they exist
    _delete_layer_if_exists(gpkg_path, "level_26910")
    _delete_layer_if_exists(gpkg_path, "level_wgs84")

    # Create level_26910
    # Map: LEVEL_ID -> level_id, FACILITY_ID -> facility_id,
    # NAME_SHORT -> short_name, VERTICAL_ORDER -> vertical_order
    sql_26910 = """
        SELECT
            LEVEL_ID AS level_id,
            FACILITY_ID AS facility_id,
            NAME_SHORT AS short_name,
            VERTICAL_ORDER AS vertical_order,
            Shape AS geom
        FROM Levels_26910
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="level_26910",
        sql=sql_26910,
        geom_type="MULTIPOLYGON25D",
        target_srs="EPSG:26910",
    )

    # Create level_wgs84 (2D)
    sql_wgs84 = """
        SELECT
            LEVEL_ID AS level_id,
            FACILITY_ID AS facility_id,
            NAME_SHORT AS short_name,
            VERTICAL_ORDER AS vertical_order,
            Shape AS geom
        FROM Levels_wgs84
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="level_wgs84",
        sql=sql_wgs84,
        geom_type="MULTIPOLYGON",
        target_srs="EPSG:4326",
    )

    # Verify count
    count = _get_layer_count(gpkg_path, "level_26910")
    if count != 11:
        raise RuntimeError(f"Expected 11 levels, got {count}")

    return count


def normalise_units(gpkg_path: Path, category_mapping: dict[str, Any]) -> int:
    """Normalise Units layer into unit table with category mapping.

    Creates unit_26910 and unit_wgs84 layers with exactly 1017 searchable units.
    Applies category mapping from YAML, computes centroid, and adds accessibility provenance.

    Args:
        gpkg_path: Path to working GeoPackage (must contain Units_26910 and Units_wgs84)
        category_mapping: Dict from category_mapping.yaml mapping USE_TYPE to category/metadata

    Returns:
        Number of units created (always 1017)

    Raises:
        RuntimeError: If ogr2ogr command fails, row count is not 1017, or unmapped USE_TYPE found
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    # Delete existing normalised layers if they exist
    _delete_layer_if_exists(gpkg_path, "unit_26910")
    _delete_layer_if_exists(gpkg_path, "unit_wgs84")

    # Validate all USE_TYPEs are in mapping
    _validate_unit_mapping(gpkg_path, category_mapping)

    # Build SQL CASE statements for category, accessible, gender, verified_by, verified_date
    category_cases = []
    accessible_cases = []
    gender_cases = []
    verified_by_cases = []
    verified_date_cases = []

    for use_type, metadata in category_mapping.items():
        # Escape single quotes in USE_TYPE
        safe_use_type = use_type.replace("'", "''")
        category = metadata["category"]

        category_cases.append(f"WHEN USE_TYPE = '{safe_use_type}' THEN '{category}'")

        # accessible field
        if "accessible" in metadata:
            accessible_value = "1" if metadata["accessible"] else "0"
            accessible_cases.append(
                f"WHEN USE_TYPE = '{safe_use_type}' THEN {accessible_value}"
            )
            # Add provenance for non-null accessible values (both true and false)
            verified_by_cases.append(
                f"WHEN USE_TYPE = '{safe_use_type}' THEN 'source_gdb_use_type'"
            )
            verified_date_cases.append(
                f"WHEN USE_TYPE = '{safe_use_type}' THEN '{SOURCE_VERIFIED_DATE}'"
            )

        # gender field
        if "gender" in metadata:
            gender_value = metadata["gender"]
            gender_cases.append(f"WHEN USE_TYPE = '{safe_use_type}' THEN '{gender_value}'")

    category_case_sql = "CASE " + " ".join(category_cases) + " END"
    accessible_case_sql = (
        "CASE " + " ".join(accessible_cases) + " ELSE NULL END"
        if accessible_cases
        else "NULL"
    )
    gender_case_sql = (
        "CASE " + " ".join(gender_cases) + " ELSE NULL END"
        if gender_cases
        else "NULL"
    )
    verified_by_case_sql = (
        "CASE " + " ".join(verified_by_cases) + " ELSE NULL END"
        if verified_by_cases
        else "NULL"
    )
    verified_date_case_sql = (
        "CASE " + " ".join(verified_date_cases) + " ELSE NULL END"
        if verified_date_cases
        else "NULL"
    )

    # The source geometry for TOXIC_UNIT_ID is an empty geometry collection, but
    # its source envelope was audited and recorded in ADR-0003 section 8.
    centroid_26910_sql = f"""
        CASE
            WHEN ST_Centroid(Shape) IS NOT NULL THEN ST_AsText(ST_Centroid(Shape))
            WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN '{TOXIC_UNIT_CENTROID_WKT}'
            ELSE NULL
        END
    """
    centroid_method_26910_sql = f"""
        CASE
            WHEN ST_Centroid(Shape) IS NOT NULL THEN 'geometry_centroid'
            WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN 'envelope_center_fallback'
            ELSE NULL
        END
    """

    # Create unit_26910 with centroid_26910 field
    # Note: centroid_26910 is a separate WKT string field, not a registered geometry column
    sql_26910 = f"""
        SELECT
            UNIT_ID AS unit_id,
            ROOM_ID AS room_id,
            LEVEL_ID AS level_id,
            USE_TYPE AS use_type,
            {category_case_sql} AS category,
            {accessible_case_sql} AS accessible,
            {gender_case_sql} AS gender,
            {verified_by_case_sql} AS verified_by,
            {verified_date_case_sql} AS verified_date,
            {centroid_26910_sql} AS centroid_26910,
            {centroid_method_26910_sql} AS centroid_method,
            CASE WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN NULL ELSE Shape END AS geom
        FROM Units_26910
        WHERE SEARCHABLE = 'Y'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="unit_26910",
        sql=sql_26910,
        geom_type="GEOMETRY25D",
        target_srs="EPSG:26910",
    )

    centroid_wgs84_sql = f"""
        CASE
            WHEN ST_Centroid(ST_Transform(Shape, 26910)) IS NOT NULL
                THEN ST_AsText(ST_Centroid(ST_Transform(Shape, 26910)))
            WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN '{TOXIC_UNIT_CENTROID_WKT}'
            ELSE NULL
        END
    """
    centroid_method_wgs84_sql = f"""
        CASE
            WHEN ST_Centroid(ST_Transform(Shape, 26910)) IS NOT NULL
                THEN 'geometry_centroid'
            WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN 'envelope_center_fallback'
            ELSE NULL
        END
    """

    # Create unit_wgs84 with the same native-CRS centroid attributes.
    sql_wgs84 = f"""
        SELECT
            UNIT_ID AS unit_id,
            ROOM_ID AS room_id,
            LEVEL_ID AS level_id,
            USE_TYPE AS use_type,
            {category_case_sql} AS category,
            {accessible_case_sql} AS accessible,
            {gender_case_sql} AS gender,
            {verified_by_case_sql} AS verified_by,
            {verified_date_case_sql} AS verified_date,
            {centroid_wgs84_sql} AS centroid_26910,
            {centroid_method_wgs84_sql} AS centroid_method,
            CASE WHEN UNIT_ID = '{TOXIC_UNIT_ID}' THEN NULL ELSE Shape END AS geom
        FROM Units_wgs84
        WHERE SEARCHABLE = 'Y'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="unit_wgs84",
        sql=sql_wgs84,
        geom_type="GEOMETRY",
        target_srs="EPSG:4326",
    )

    # Verify count
    count = _get_layer_count(gpkg_path, "unit_26910")
    if count != 1017:
        raise RuntimeError(f"Expected 1017 searchable units, got {count}")

    logger.warning(
        "Applied envelope centroid fallback to unit %s at %s",
        TOXIC_UNIT_ID,
        TOXIC_UNIT_CENTROID_WKT,
    )

    return count


def normalise_landmarks(gpkg_path: Path) -> int:
    """Normalise Landmarks layer into landmark table with deduplication.

    Creates landmark_26910 and landmark_wgs84 layers with exactly 40 landmarks
    (41 source features - 1 duplicate pair at 0.250728m).

    Deduplication algorithm (greedy first-point-wins, per ADR-0003):
    1. Parse category from DESCRIPTION field (water_fountain or vending_machine)
    2. Sort points by (category, level_id, X, Y) ascending
    3. For each point, mark all others within 0.5m as duplicates; keep first

    Landmark IDs: LMK_<FID> from source FID of representative point.

    Args:
        gpkg_path: Path to working GeoPackage (must contain Landmarks_26910 and Landmarks_wgs84)

    Returns:
        Number of landmarks created (always 40)

    Raises:
        RuntimeError: If ogr2ogr command fails or row count is not 40
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    # Delete existing normalised layers if they exist
    _delete_layer_if_exists(gpkg_path, "landmark_26910")
    _delete_layer_if_exists(gpkg_path, "landmark_wgs84")

    landmarks = _read_landmark_features(gpkg_path)
    representatives = _deduplicate_landmarks(landmarks)
    feature_collection = {
        "type": "FeatureCollection",
        "features": representatives,
    }
    _write_geojson_layer(
        gpkg_path,
        "landmark_26910",
        feature_collection,
        "POINT25D",
        "EPSG:26910",
    )
    _write_geojson_layer(
        gpkg_path,
        "landmark_wgs84",
        feature_collection,
        "POINT",
        "EPSG:4326",
    )

    # Verify count
    count = _get_layer_count(gpkg_path, "landmark_26910")
    if count != 40:
        raise RuntimeError(f"Expected 40 landmarks (41 source - 1 duplicate), got {count}")

    return count


def _read_landmark_features(gpkg_path: Path) -> list[dict[str, Any]]:
    """Read the small native landmark layer into memory as GeoJSON features."""
    cmd = ["ogrinfo", "-json", "-features", str(gpkg_path), "Landmarks_26910"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ogrinfo failed to read landmarks: {result.stderr}")

    document = json.loads(result.stdout)
    return document["layers"][0]["features"]


def _deduplicate_landmarks(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply deterministic greedy first-point-wins clustering within 0.5 m."""
    parsed = []
    for feature in features:
        description = feature["properties"]["DESCRIPTION"]
        if description.startswith("Water Fountain"):
            category = "water_fountain"
        elif description.startswith("Vending Machine"):
            category = "vending_machine"
        else:
            category = "unknown"

        coordinates = feature["geometry"]["coordinates"]
        parsed.append(
            {
                "fid": feature["fid"],
                "category": category,
                "level_id": feature["properties"]["LEVEL_ID"],
                "coordinates": coordinates,
            }
        )

    parsed.sort(
        key=lambda item: (
            item["category"],
            item["level_id"],
            item["coordinates"][0],
            item["coordinates"][1],
            item["fid"],
        )
    )

    representatives = []
    for landmark in parsed:
        duplicate = any(
            existing["category"] == landmark["category"]
            and existing["level_id"] == landmark["level_id"]
            and math.hypot(
                existing["coordinates"][0] - landmark["coordinates"][0],
                existing["coordinates"][1] - landmark["coordinates"][1],
            ) <= 0.5
            for existing in representatives
        )
        if not duplicate:
            representatives.append(landmark)

    return [
        {
            "type": "Feature",
            "properties": {
                "landmark_id": f"LMK_{landmark['fid']}",
                "category": landmark["category"],
                "level_id": landmark["level_id"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": landmark["coordinates"],
            },
        }
        for landmark in representatives
    ]


def _write_geojson_layer(
    gpkg_path: Path,
    output_layer: str,
    feature_collection: dict[str, Any],
    geom_type: str,
    target_srs: str,
) -> None:
    """Stream in-memory GeoJSON to a final GeoPackage layer."""
    cmd = [
        "ogr2ogr",
        "-f", "GPKG",
        "-update",
        "-nln", output_layer,
        "-nlt", geom_type,
        "-s_srs", "EPSG:26910",
        "-t_srs", target_srs,
        str(gpkg_path),
        "/vsistdin/",
    ]
    result = subprocess.run(
        cmd,
        input=json.dumps(feature_collection),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ogr2ogr failed for layer {output_layer}: {result.stderr}")


def normalise_details(gpkg_path: Path) -> dict[str, int]:
    """Normalise Details layer into detail and door tables.

    Reads Details_26910 and Details_wgs84 once, splits by USE_TYPE:
    - USE_TYPE='ADO' -> door table (6865 rows)
    - All other USE_TYPE -> detail table (48728 rows)

    Preserves source DETAIL_ID field directly for detail_id and door_id.

    Args:
        gpkg_path: Path to working GeoPackage (must contain Details_26910 and Details_wgs84)

    Returns:
        {"detail": <row_count>, "door": <row_count>}

    Raises:
        RuntimeError: If ogr2ogr command fails or row counts are incorrect
    """
    if not gpkg_path.exists():
        raise FileNotFoundError(f"GeoPackage not found: {gpkg_path}")

    # Delete existing normalised layers if they exist
    _delete_layer_if_exists(gpkg_path, "detail_26910")
    _delete_layer_if_exists(gpkg_path, "detail_wgs84")
    _delete_layer_if_exists(gpkg_path, "door_26910")
    _delete_layer_if_exists(gpkg_path, "door_wgs84")

    # Create detail_26910 (exclude ADO)
    sql_detail_26910 = """
        SELECT
            DETAIL_ID AS detail_id,
            USE_TYPE AS use_type,
            LEVEL_ID AS level_id,
            Shape AS geom
        FROM Details_26910
        WHERE USE_TYPE != 'ADO'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="detail_26910",
        sql=sql_detail_26910,
        geom_type="MULTILINESTRING25D",
        target_srs="EPSG:26910",
    )

    # Create detail_wgs84 (2D)
    sql_detail_wgs84 = """
        SELECT
            DETAIL_ID AS detail_id,
            USE_TYPE AS use_type,
            LEVEL_ID AS level_id,
            Shape AS geom
        FROM Details_wgs84
        WHERE USE_TYPE != 'ADO'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="detail_wgs84",
        sql=sql_detail_wgs84,
        geom_type="MULTILINESTRING",
        target_srs="EPSG:4326",
    )

    # Create door_26910 (only ADO)
    sql_door_26910 = """
        SELECT
            DETAIL_ID AS door_id,
            USE_TYPE AS use_type,
            LEVEL_ID AS level_id,
            Shape AS geom
        FROM Details_26910
        WHERE USE_TYPE = 'ADO'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="door_26910",
        sql=sql_door_26910,
        geom_type="MULTILINESTRING25D",
        target_srs="EPSG:26910",
    )

    # Create door_wgs84 (2D)
    sql_door_wgs84 = """
        SELECT
            DETAIL_ID AS door_id,
            USE_TYPE AS use_type,
            LEVEL_ID AS level_id,
            Shape AS geom
        FROM Details_wgs84
        WHERE USE_TYPE = 'ADO'
    """
    _run_ogr2ogr_sql(
        gpkg_path=gpkg_path,
        output_layer="door_wgs84",
        sql=sql_door_wgs84,
        geom_type="MULTILINESTRING",
        target_srs="EPSG:4326",
    )

    # Verify counts
    detail_count = _get_layer_count(gpkg_path, "detail_26910")
    door_count = _get_layer_count(gpkg_path, "door_26910")

    if detail_count != 48728:
        raise RuntimeError(f"Expected 48728 detail rows, got {detail_count}")
    if door_count != 6865:
        raise RuntimeError(f"Expected 6865 door rows, got {door_count}")

    return {"detail": detail_count, "door": door_count}


# Helper functions

def _delete_layer_if_exists(gpkg_path: Path, layer_name: str) -> None:
    """Delete a layer from GeoPackage if it exists (for idempotent overwrite)."""
    cmd = ["ogrinfo", str(gpkg_path), "-sql", f"DROP TABLE IF EXISTS {layer_name}"]
    subprocess.run(cmd, capture_output=True, check=False)


def _run_ogr2ogr_sql(
    gpkg_path: Path,
    output_layer: str,
    sql: str,
    geom_type: str,
    target_srs: str,
) -> None:
    """Execute SQL and write results to a new layer using ogr2ogr."""
    cmd = [
        "ogr2ogr",
        "-f", "GPKG",
        "-update",
        "-nln", output_layer,
        "-nlt", geom_type,
        "-t_srs", target_srs,
        "-sql", sql,
        str(gpkg_path),
        str(gpkg_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogr2ogr failed for layer {output_layer}: {result.stderr}\nSQL: {sql}"
        )


def _get_layer_count(gpkg_path: Path, layer_name: str) -> int:
    """Get feature count for a layer using ogrinfo."""
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"ogrinfo failed for layer {layer_name}: {result.stderr}")

    output = result.stdout + result.stderr

    # Parse "Feature Count: 1017" line
    for line in output.splitlines():
        if line.startswith("Feature Count:"):
            count_str = line.split(":")[1].strip()
            return int(count_str)

    raise ValueError(f"Could not parse feature count from ogrinfo output for {layer_name}")


def _validate_unit_mapping(gpkg_path: Path, category_mapping: dict[str, Any]) -> None:
    """Validate all searchable units have USE_TYPE in category mapping."""
    # Query distinct USE_TYPE values for searchable units
    cmd = [
        "ogrinfo",
        str(gpkg_path),
        "-sql",
        "SELECT DISTINCT USE_TYPE FROM Units_26910 WHERE SEARCHABLE = 'Y'",
        "-q",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to query USE_TYPE values: {result.stderr}")

    output = result.stdout + result.stderr

    # Parse USE_TYPE values
    use_types_in_data = set()
    for line in output.splitlines():
        if "USE_TYPE (String)" in line and "=" in line:
            use_type = line.split("=")[1].strip()
            use_types_in_data.add(use_type)

    # Check for unmapped USE_TYPEs
    unmapped = use_types_in_data - set(category_mapping.keys())
    if unmapped:
        raise RuntimeError(
            f"Unmapped USE_TYPE values in searchable units: {sorted(unmapped)}. "
            f"Update category_mapping.yaml to include these."
        )
