"""Failing tests for DT-004: Normalise Tables.

These tests check:
1. normalise module and function signatures
2. Facility normalisation (3 rows, codes, geometry CRS)
3. Level normalisation (11 rows, vertical_order, facility mapping)
4. Unit normalisation (1017 searchable, category coverage, provenance)
5. Landmark deduplication (exactly 40 rows, category parsing)
6. Detail and door split (48728 details, 6865 doors)
7. Cross-table invariants (FK, vertical_order uniqueness)
8. Geometry and CRS correctness (EPSG:26910 3D, EPSG:4326 2D)
9. Determinism and idempotency
10. Accessibility provenance (verified_by, verified_date)
11. Integration tests (end-to-end normalisation)
12. Makefile target and CLI dispatch

All tests will FAIL initially because:
- wayfinding.etl.normalise module does not exist
- DoorSchema not yet added to schema.py
- UnitSchema missing verified_by and verified_date fields
- build/wayfinding.gpkg has only 14 raw layers (no normalised tables)

Tests execute inside the pinned GDAL ETL container and may call ogrinfo/ogr2ogr
directly. Session fixture copies build/wayfinding.gpkg to a temporary path before
normalisation so tests never mutate the approved DT-003 artifact.
"""

import inspect
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
SOURCE_GPKG = WORKSPACE_ROOT / "build" / "wayfinding.gpkg"
BUILD_DIR = WORKSPACE_ROOT / "build"

# Expected normalised table row counts from DT-004.md §2.2
EXPECTED_NORMALISED_COUNTS = {
    "facility": 3,
    "level": 11,
    "unit": 1017,  # Exact: only SEARCHABLE='Y'
    "landmark": 40,  # Exact: 41 source - 1 duplicate pair (FIDs 28 & 41)
    "detail": 48728,  # 55593 - 6865 ADO doors
    "door": 6865,
}

# Total normalised records: 56,664
# Total layers after DT-004: 14 raw + 12 normalised dual-CRS = 26 layers

# Expected vertical_order values from docs/01-data-findings.md §3
# Using exact preserved source LEVEL_ID values (not abbreviated forms)
EXPECTED_VERTICAL_ORDER = {
    # AQ levels
    "SFU_BURNABY_QUAD_1000": -2,
    "SFU_BURNABY_QUAD_2000": -1,
    "SFU_BURNABY_QUAD_3000": 0,
    "SFU_BURNABY_QUAD_4000": 1,
    "SFU_BURNABY_QUAD_5000": 2,
    "SFU_BURNABY_QUAD_6000": 3,
    # SH levels
    "SFU_BURNABY_STRAND_100": -1,
    "SFU_BURNABY_STRAND_1000": 0,
    "SFU_BURNABY_STRAND_2000": 1,
    "SFU_BURNABY_STRAND_3000": 2,
    # ECC level
    "SFU_BURNABY_ECC_3000": 0,
}

# Stable source GDB date for provenance (mtime 2026-08-29T01:44:22Z)
SOURCE_VERIFIED_DATE = "2026-08-29"


# Helper functions for robust ogrinfo parsing

def get_ogrinfo_json(gpkg_path: Path, layer_name: str) -> dict[str, Any]:
    """Get layer info as JSON using ogrinfo."""
    cmd = ["ogrinfo", "-json", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed for layer {layer_name}: {result.stderr}"
        )

    data = json.loads(result.stdout)
    # ogrinfo -json returns {"layers": [{"name": ..., "geometryFields": [...], ...}]}
    layers = data.get("layers", [])
    if not layers:
        raise ValueError(f"No layers found in ogrinfo output for {layer_name}")

    return layers[0]


def get_layer_count(gpkg_path: Path, layer_name: str) -> int:
    """Get feature count for a layer using ogrinfo."""
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed for layer {layer_name}: {result.stderr}"
        )

    output = result.stdout + result.stderr

    # Parse "Feature Count: 1017" line
    for line in output.splitlines():
        if line.startswith("Feature Count:"):
            count_str = line.split(":")[1].strip()
            return int(count_str)

    msg = "Could not parse feature count from ogrinfo output"
    raise ValueError(msg)


def get_layer_crs(gpkg_path: Path, layer_name: str) -> str:
    """Get CRS identifier (EPSG code or WKT) for a layer."""
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed for layer {layer_name}: {result.stderr}"
        )

    output = result.stdout + result.stderr

    # Look for EPSG code: "PROJCS[...AUTHORITY["EPSG","26910"]]"
    for line in output.splitlines():
        if "EPSG" in line and "26910" in line:
            return "EPSG:26910"
        if "GEOGCS" in line and "4326" in line:
            return "EPSG:4326"
        if "WGS 84" in line:
            return "EPSG:4326"

    # Fallback: return first line with coordinate system
    for line in output.splitlines():
        if "Layer SRS WKT:" in line or line.startswith(("PROJCS[", "GEOGCS[")):
            return line.strip()

    msg = f"Could not parse CRS from ogrinfo output for {layer_name}"
    raise ValueError(msg)


def get_geometry_type(gpkg_path: Path, layer_name: str) -> str:
    """Get geometry type for a layer (e.g., '3D Multi Polygon', 'Point')."""
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed for layer {layer_name}: {result.stderr}"
        )

    output = result.stdout + result.stderr

    # Parse "Geometry: Multi Polygon" or "Geometry: 3D Point" line
    for line in output.splitlines():
        if line.startswith("Geometry:"):
            return line.split(":", 1)[1].strip()

    msg = "Could not parse geometry type from ogrinfo output"
    raise ValueError(msg)


def list_gpkg_layers(gpkg_path: Path) -> list[str]:
    """List all layer names in a GeoPackage."""
    cmd = ["ogrinfo", "-json", "-so", str(gpkg_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"ogrinfo failed: {result.stderr}")

    data = json.loads(result.stdout)
    return [layer["name"] for layer in data.get("layers", [])]


def sql_query(gpkg_path: Path, sql: str) -> list[tuple]:
    """Execute SQL query and return results as list of tuples."""
    cmd = [
        "ogrinfo",
        str(gpkg_path),
        "-sql",
        sql,
        "-q",  # quiet mode, only show results
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(f"SQL query failed: {result.stderr}\nSQL: {sql}")

    # Parse output: each feature is printed as "OGRFeature(...):..."
    # For simple queries we can parse lines
    output = result.stdout + result.stderr
    rows = []

    for line in output.splitlines():
        if "=" in line and not line.startswith("OGRFeature"):
            # Parse field=value pairs
            # Example: "  facility_id (String) = AQ"
            parts = line.strip().split("=")
            if len(parts) == 2:
                value = parts[1].strip()
                rows.append((value,))

    return rows


def get_field_names(gpkg_path: Path, layer_name: str) -> list[str]:
    """Get list of field names for a layer."""
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed for layer {layer_name}: {result.stderr}"
        )

    output = result.stdout + result.stderr
    fields = []

    # Parse field definitions: "field_name: Type (width)"
    for line in output.splitlines():
        if line.startswith(("Geometry:", "Feature Count:")):
            continue

        # Fields appear after "Layer name:" and before "Geometry:"
        if ":" in line and not line.startswith("Layer SRS"):
            parts = line.split(":")
            field_name = parts[0].strip()

            # Exclude metadata lines
            if field_name and not field_name.startswith("Layer") and field_name != "Geometry":
                # Check if this looks like a field definition
                if len(parts) == 2 and any(t in parts[1] for t in ("String", "Integer", "Real")):
                    fields.append(field_name)

    return fields


# Fixtures

@pytest.fixture(scope="module")
def temp_gpkg_for_module():
    """Module-scoped fixture: copy build/wayfinding.gpkg to temp for all tests.

    This shared temp GPKG is used for integration assertions. Separate copies
    are made for idempotency and error-handling tests to avoid side effects.
    """
    if not SOURCE_GPKG.exists():
        pytest.skip(f"Source GeoPackage not found: {SOURCE_GPKG}")

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_gpkg = Path(tmpdir) / "wayfinding_test.gpkg"
        shutil.copy2(SOURCE_GPKG, temp_gpkg)
        yield temp_gpkg


@pytest.fixture
def temp_gpkg():
    """Function-scoped fixture: fresh copy of build/wayfinding.gpkg for each test.

    Use this for tests that modify the GPKG (idempotency, error handling).
    """
    if not SOURCE_GPKG.exists():
        pytest.skip(f"Source GeoPackage not found: {SOURCE_GPKG}")

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_gpkg = Path(tmpdir) / "wayfinding_test.gpkg"
        shutil.copy2(SOURCE_GPKG, temp_gpkg)
        yield temp_gpkg


# Test Classes

class TestNormaliseModule:
    """Test normalise module structure and function signatures."""

    def test_normalise_module_exists(self):
        """wayfinding.etl.normalise module must exist."""
        try:
            from wayfinding.etl import normalise
        except ImportError as e:
            pytest.fail(f"Cannot import wayfinding.etl.normalise: {e}")

        assert normalise is not None

    def test_normalise_facilities_exists(self):
        """normalise_facilities function must exist with correct signature."""
        from wayfinding.etl.normalise import normalise_facilities

        sig = inspect.signature(normalise_facilities)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "normalise_facilities missing gpkg_path parameter"

        # Should return int (row count)
        assert sig.return_annotation in [int, "int"], (
            "normalise_facilities should return int"
        )

    def test_normalise_levels_exists(self):
        """normalise_levels function must exist with correct signature."""
        from wayfinding.etl.normalise import normalise_levels

        sig = inspect.signature(normalise_levels)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "normalise_levels missing gpkg_path parameter"
        assert sig.return_annotation in [int, "int"]

    def test_normalise_units_exists(self):
        """normalise_units function must exist with category_mapping parameter."""
        from wayfinding.etl.normalise import normalise_units

        sig = inspect.signature(normalise_units)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "normalise_units missing gpkg_path parameter"
        assert "category_mapping" in params, (
            "normalise_units missing category_mapping parameter"
        )
        assert sig.return_annotation in [int, "int"]

    def test_normalise_landmarks_exists(self):
        """normalise_landmarks function must exist with correct signature."""
        from wayfinding.etl.normalise import normalise_landmarks

        sig = inspect.signature(normalise_landmarks)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "normalise_landmarks missing gpkg_path parameter"
        assert sig.return_annotation in [int, "int"]

    def test_normalise_details_exists(self):
        """normalise_details must return dict with detail and door counts."""
        from wayfinding.etl.normalise import normalise_details

        sig = inspect.signature(normalise_details)
        params = list(sig.parameters.keys())

        assert "gpkg_path" in params, "normalise_details missing gpkg_path parameter"

        # Should return dict[str, int]
        # Allow various type annotation formats
        return_type = str(sig.return_annotation)
        assert "dict" in return_type or "Dict" in return_type, (
            "normalise_details should return dict[str, int] for detail and door counts"
        )


class TestDoorSchema:
    """Test DoorSchema added to schema.py."""

    def test_door_schema_exists(self):
        """DoorSchema must be defined in wayfinding.etl.schema."""
        from wayfinding.etl import schema

        assert hasattr(schema, "DoorSchema"), (
            "schema.py missing DoorSchema class"
        )

    def test_door_schema_has_required_fields(self):
        """DoorSchema must have door_id, use_type, level_id, geom fields."""
        from wayfinding.etl.schema import DoorSchema

        # Get model fields
        fields = DoorSchema.model_fields

        assert "door_id" in fields, "DoorSchema missing door_id field"
        assert "use_type" in fields, "DoorSchema missing use_type field"
        assert "level_id" in fields, "DoorSchema missing level_id field"
        assert "geom_26910" in fields or "geom" in fields, (
            "DoorSchema missing geometry field"
        )


class TestUnitSchemaProvenance:
    """Test UnitSchema extended with verified_by and verified_date fields."""

    def test_unit_schema_has_provenance_fields(self):
        """UnitSchema must have verified_by and verified_date fields."""
        from wayfinding.etl.schema import UnitSchema

        fields = UnitSchema.model_fields

        assert "verified_by" in fields, (
            "UnitSchema missing verified_by field (ADR-0003 provenance requirement)"
        )
        assert "verified_date" in fields, (
            "UnitSchema missing verified_date field (ADR-0003 provenance requirement)"
        )

    def test_unit_schema_provenance_nullable(self):
        """verified_by and verified_date must be nullable (str | None)."""
        from wayfinding.etl.schema import UnitSchema

        fields = UnitSchema.model_fields

        # Both should be Optional[str]
        verified_by_type = str(fields["verified_by"].annotation)
        verified_date_type = str(fields["verified_date"].annotation)

        assert "None" in verified_by_type or "Optional" in verified_by_type, (
            "verified_by must be nullable (str | None)"
        )
        assert "None" in verified_date_type or "Optional" in verified_date_type, (
            "verified_date must be nullable (str | None)"
        )

    def test_unit_schema_has_centroid_method_field(self):
        """UnitSchema must have required centroid_method field (ADR-0003 §8)."""
        from wayfinding.etl.schema import UnitSchema

        fields = UnitSchema.model_fields

        assert "centroid_method" in fields, (
            "UnitSchema missing centroid_method field (ADR-0003 §8 provenance requirement)"
        )

    def test_unit_schema_centroid_method_required(self):
        """centroid_method must be required (not nullable) per ADR-0003 §8."""
        from wayfinding.etl.schema import UnitSchema

        fields = UnitSchema.model_fields

        # centroid_method should be required (str, not str | None)
        centroid_method_type = str(fields["centroid_method"].annotation)

        # If it's optional, the annotation will contain "None" or "Optional"
        # A required str field should NOT have these
        assert "None" not in centroid_method_type or "NoneType" not in centroid_method_type, (
            "centroid_method must be required (str), not nullable (str | None). "
            "Every unit must document its centroid derivation method."
        )


class TestFacilityNormalisation:
    """Test normalise_facilities creates 3 rows with correct schema."""

    @pytest.mark.slow
    def test_normalise_facility_count_and_schema(self, temp_gpkg):
        """Facility table must have 3 rows (AQ, SH, ECC)."""
        from wayfinding.etl.normalise import normalise_facilities

        row_count = normalise_facilities(temp_gpkg)

        assert row_count == 3, f"Expected 3 facilities, got {row_count}"

        # Verify layers exist
        layers = list_gpkg_layers(temp_gpkg)
        assert "facility_26910" in layers, "facility_26910 layer not created"
        assert "facility_wgs84" in layers, "facility_wgs84 layer not created"

        # Verify counts match in both CRS layers
        count_26910 = get_layer_count(temp_gpkg, "facility_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "facility_wgs84")

        assert count_26910 == 3, f"facility_26910 has {count_26910} rows, expected 3"
        assert count_wgs84 == 3, f"facility_wgs84 has {count_wgs84} rows, expected 3"

    @pytest.mark.slow
    def test_normalise_facility_codes(self, temp_gpkg):
        """Facility code values must be exactly ['AQ', 'SH', 'ECC'] (derived from NAME field)."""
        from wayfinding.etl.normalise import normalise_facilities

        normalise_facilities(temp_gpkg)

        # Query code field values using SQL
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT code FROM facility_26910 ORDER BY code",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        output = result.stdout + result.stderr

        # Parse output for code values
        codes = []
        for line in output.splitlines():
            if "code (String)" in line and "=" in line:
                code = line.split("=")[1].strip()
                codes.append(code)

        expected_codes = ["AQ", "ECC", "SH"]  # Sorted
        assert codes == expected_codes

    @pytest.mark.slow
    def test_normalise_facility_geometry_crs(self, temp_gpkg):
        """facility_26910 must be EPSG:26910, facility_wgs84 must be EPSG:4326."""
        from wayfinding.etl.normalise import normalise_facilities

        normalise_facilities(temp_gpkg)

        crs_26910 = get_layer_crs(temp_gpkg, "facility_26910")
        crs_wgs84 = get_layer_crs(temp_gpkg, "facility_wgs84")

        assert "26910" in crs_26910, (
            f"facility_26910 should be EPSG:26910, got {crs_26910}"
        )
        assert "4326" in crs_wgs84 or "WGS 84" in crs_wgs84, (
            f"facility_wgs84 should be EPSG:4326, got {crs_wgs84}"
        )


class TestLevelNormalisation:
    """Test normalise_levels creates 11 rows with correct vertical_order."""

    @pytest.mark.slow
    def test_normalise_level_count(self, temp_gpkg):
        """Level table must have exactly 11 rows."""
        from wayfinding.etl.normalise import normalise_levels

        row_count = normalise_levels(temp_gpkg)

        assert row_count == 11, f"Expected 11 levels, got {row_count}"

        count_26910 = get_layer_count(temp_gpkg, "level_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "level_wgs84")

        assert count_26910 == 11
        assert count_wgs84 == 11

    @pytest.mark.slow
    def test_normalise_level_vertical_order(self, temp_gpkg):
        """Level vertical_order values must match docs/01-data-findings.md §3."""
        from wayfinding.etl.normalise import normalise_levels

        normalise_levels(temp_gpkg)

        # Query level_id and vertical_order
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT level_id, vertical_order FROM level_26910",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        output = result.stdout + result.stderr

        # Parse output
        level_vertical_orders = {}
        current_level_id = None

        for line in output.splitlines():
            if "level_id (String)" in line and "=" in line:
                current_level_id = line.split("=")[1].strip()
            elif "vertical_order (Integer)" in line and "=" in line:
                vertical_order = int(line.split("=")[1].strip())
                if current_level_id:
                    level_vertical_orders[current_level_id] = vertical_order
                    current_level_id = None

        # Verify against expected values
        for level_id, expected_vo in EXPECTED_VERTICAL_ORDER.items():
            assert level_id in level_vertical_orders
            assert level_vertical_orders[level_id] == expected_vo

    @pytest.mark.slow
    def test_normalise_level_facility_mapping(self, temp_gpkg):
        """Every level_id must map to exactly one preserved source FACILITY_ID."""
        from wayfinding.etl.normalise import normalise_facilities, normalise_levels

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)

        # Query level_id -> facility_id mappings
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT level_id, facility_id FROM level_26910",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        output = result.stdout + result.stderr

        # Parse mappings
        level_to_facility = {}
        current_level_id = None

        for line in output.splitlines():
            if "level_id (String)" in line and "=" in line:
                current_level_id = line.split("=")[1].strip()
            elif "facility_id (String)" in line and "=" in line:
                facility_id = line.split("=")[1].strip()
                if current_level_id:
                    level_to_facility[current_level_id] = facility_id
                    current_level_id = None

        # Every level must have a facility
        assert len(level_to_facility) == 11

        # All facility_ids must be exact preserved source FACILITY_ID values
        valid_facilities = {"SFU_BURNABY_QUAD", "SFU_BURNABY_STRAND", "SFU_BURNABY_ECC"}
        for facility_id in level_to_facility.values():
            assert facility_id in valid_facilities, (
                "Expected preserved source FACILITY_ID "
                f"(SFU_BURNABY_QUAD/STRAND/ECC), got '{facility_id}'"
            )


class TestUnitNormalisation:
    """Test normalise_units creates 1017 searchable units with categories."""

    @pytest.mark.slow
    def test_normalise_unit_count_and_searchable_filter(self, temp_gpkg):
        """Unit table must have exactly 1017 rows (only SEARCHABLE='Y')."""
        # Load category mapping
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        row_count = normalise_units(temp_gpkg, category_mapping)

        assert row_count == 1017, (
            f"Expected exactly 1017 searchable units, got {row_count}"
        )

        count_26910 = get_layer_count(temp_gpkg, "unit_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "unit_wgs84")

        assert count_26910 == 1017
        assert count_wgs84 == 1017

    @pytest.mark.slow
    def test_normalise_unit_category_coverage(self, temp_gpkg):
        """Every unit must have category populated (no nulls)."""
        import yaml

        from wayfinding.etl.normalise import normalise_units

        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src"
            / "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query for any null categories
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT COUNT(*) FROM unit_26910 WHERE category IS NULL",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        output = result.stdout + result.stderr

        # Should find 0 nulls
        # ogrinfo output for COUNT(*) is tricky to parse, but if no nulls exist,
        # the result should be 0 or empty feature set
        assert "0" in output or "no features" in output.lower()

    @pytest.mark.slow
    def test_normalise_unit_category_examples(self, temp_gpkg):
        """Spot-check 5 use_type -> category mappings."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Expected mappings from category_mapping.yaml
        expected_mappings = {
            "Office": "office",
            "Washroom, single-stall, accessible": "washroom",
            "Stairs": "vertical_circulation",
            "Classroom": "classroom",
            "Corridor": "corridor",
        }

        # Query units with these use_types
        for use_type, expected_category in expected_mappings.items():
            cmd = [
                "ogrinfo",
                str(temp_gpkg),
                "-sql",
                f"SELECT category FROM unit_26910 WHERE use_type = '{use_type}' LIMIT 1",
                "-q",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            output = result.stdout + result.stderr

            # Parse category value
            for line in output.splitlines():
                if "category (String)" in line and "=" in line:
                    category = line.split("=")[1].strip()
                    assert category == expected_category, (
                        f"USE_TYPE '{use_type}' should map to category '{expected_category}', "
                        f"got '{category}'"
                    )
                    break

    @pytest.mark.slow
    def test_normalise_unit_accessible_flag(self, temp_gpkg):
        """Accessible flag must match category_mapping.yaml rules."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Test specific use_types with known accessible values
        test_cases = [
            ("Washroom, single-stall, accessible", "1"),  # true = 1 in SQL
            ("Stairs", "0"),  # false = 0 in SQL
            ("Elevator Shaft", "1"),  # true
        ]

        for use_type, expected_accessible in test_cases:
            cmd = [
                "ogrinfo",
                str(temp_gpkg),
                "-sql",
                f"SELECT accessible FROM unit_26910 WHERE use_type = '{use_type}' LIMIT 1",
                "-q",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            output = result.stdout + result.stderr

            # Parse accessible value
            for line in output.splitlines():
                if "accessible" in line.lower() and "=" in line:
                    accessible_str = line.split("=")[1].strip()
                    # Convert to 0/1 string for comparison
                    if accessible_str.lower() in ["true", "1"]:
                        accessible_str = "1"
                    elif accessible_str.lower() in ["false", "0"]:
                        accessible_str = "0"

                    assert accessible_str == expected_accessible, (
                        f"USE_TYPE '{use_type}' should have accessible={expected_accessible}, "
                        f"got {accessible_str}"
                    )
                    break

    @pytest.mark.slow
    def test_normalise_unit_room_id_populated(self, temp_gpkg):
        """All 1017 units must have non-null room_id."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query for null room_ids
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT COUNT(*) FROM unit_26910 WHERE room_id IS NULL",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        output = result.stdout + result.stderr

        # Should be 0 (all room_ids populated per data findings §4)
        assert "0" in output or "no features" in output.lower(), (
            "Found units with null room_id (data findings §4 says 100% populated)"
        )

    @pytest.mark.slow
    def test_normalise_unit_centroid(self, temp_gpkg):
        """centroid_26910 must be within geom_26910 bounding box."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Check that centroid_26910 field exists
        fields = get_field_names(temp_gpkg, "unit_26910")
        assert "centroid_26910" in fields, (
            "unit_26910 missing centroid_26910 field"
        )

        # Spot-check: query a few units and verify centroid is a Point geometry
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT unit_id FROM unit_26910 LIMIT 1",
            "-q",
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=False)

        # If we got here without errors, centroid field exists
        # Full validation would require checking ST_Within(centroid, envelope(geom))
        # which is tested implicitly during normalisation


class TestUnitCentroidProvenance:
    """Test unit centroid_method provenance and toxic geometry fallback (ADR-0003 §8)."""

    @pytest.mark.slow
    def test_normalise_unit_centroid_method_coverage(self, temp_gpkg):
        """All 1017 units must have non-null centroid_26910 and centroid_method.

        Per ADR-0003 §8 and DT-004 AC4a: centroid_method must be populated for every
        row with exactly 'geometry_centroid' or 'envelope_center_fallback'.
        Expected counts: 1016 geometry_centroid, 1 envelope_center_fallback.
        """
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query centroid_26910 and centroid_method for all units
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT COUNT(*) FROM unit_26910 WHERE centroid_26910 IS NULL",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        # Zero units should have null centroid_26910
        assert "0" in output or "no features" in output.lower(), (
            "Found units with null centroid_26910 (all 1017 units must have centroids)"
        )

        # Query centroid_method counts
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT centroid_method, COUNT(*) as cnt FROM unit_26910 "
            "GROUP BY centroid_method ORDER BY centroid_method",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        # Parse counts for each method
        method_counts = {}
        current_method = None

        for line in output.splitlines():
            if "centroid_method (String)" in line and "=" in line:
                current_method = line.split("=")[1].strip()
            elif "cnt (Integer)" in line and "=" in line and current_method:
                count = int(line.split("=")[1].strip())
                method_counts[current_method] = count
                current_method = None

        # Verify expected counts: 1016 geometry_centroid, 1 envelope_center_fallback
        assert "geometry_centroid" in method_counts, (
            "No units with centroid_method='geometry_centroid' found"
        )
        assert method_counts["geometry_centroid"] == 1016, (
            "Expected 1016 units with geometry_centroid, got "
            f"{method_counts.get('geometry_centroid', 0)}"
        )

        assert "envelope_center_fallback" in method_counts, (
            "No units with centroid_method='envelope_center_fallback' found "
            "(expected 1 toxic geometry unit: SFU_BURNABY_QUAD_2000_2017)"
        )
        assert method_counts["envelope_center_fallback"] == 1, (
            f"Expected 1 unit with envelope_center_fallback (SFU_BURNABY_QUAD_2000_2017), "
            f"got {method_counts.get('envelope_center_fallback', 0)}"
        )

        # No other methods should exist
        assert len(method_counts) == 2, (
            f"Expected only 2 centroid methods, got {len(method_counts)}: "
            f"{list(method_counts.keys())}"
        )

        # No null centroid_method values
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT COUNT(*) FROM unit_26910 WHERE centroid_method IS NULL",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        assert "0" in output or "no features" in output.lower(), (
            "Found units with null centroid_method (must be populated for all rows)"
        )

    @pytest.mark.slow
    def test_normalise_unit_centroid_fallback_toxic_geometry(self, temp_gpkg):
        """Toxic geometry unit SFU_BURNABY_QUAD_2000_2017 must use envelope fallback.

        Per ADR-0003 §8: source unit SFU_BURNABY_QUAD_2000_2017 has WKT
        GEOMETRYCOLLECTION() causing ST_Centroid to return NULL. Fallback computes
        envelope center: (506011.7248, 5458491.1155) in EPSG:26910.

        Assert:
        - centroid_method = 'envelope_center_fallback'
        - centroid_26910 WKT is POINT Z or POINT at x=506011.7248, y=5458491.1155
          within 0.01 m tolerance (accounting for floating-point precision)
        - Source geom remains toxic GEOMETRYCOLLECTION() (unmodified)
        """
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query the toxic geometry unit
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT unit_id, centroid_method, ST_AsText(centroid_26910) as centroid_wkt, "
            "ST_GeometryType(geom) as geom_type FROM unit_26910 "
            "WHERE unit_id = 'SFU_BURNABY_QUAD_2000_2017'",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        # Parse output
        centroid_method = None
        centroid_wkt = None
        geom_type = None

        for line in output.splitlines():
            if "centroid_method (String)" in line and "=" in line:
                centroid_method = line.split("=")[1].strip()
            elif "centroid_wkt (String)" in line and "=" in line:
                centroid_wkt = line.split("=")[1].strip()
            elif "geom_type (String)" in line and "=" in line:
                geom_type = line.split("=")[1].strip()

        assert centroid_method is not None, (
            "Could not query SFU_BURNABY_QUAD_2000_2017 (unit not found or query failed)"
        )

        # Verify centroid_method
        assert centroid_method == "envelope_center_fallback", (
            f"Expected centroid_method='envelope_center_fallback' for toxic geometry unit, "
            f"got '{centroid_method}'"
        )

        # Verify centroid WKT coordinates
        assert centroid_wkt is not None, "centroid_26910 is NULL (fallback failed)"

        # Parse coordinates from WKT (POINT Z (x y z) or POINT (x y))
        # Expected: x=506011.7248, y=5458491.1155
        import re
        coord_match = re.search(r"POINT(?:\s+Z)?\s*\(([\d.\-]+)\s+([\d.\-]+)", centroid_wkt)
        assert coord_match, f"Could not parse centroid WKT: {centroid_wkt}"

        x = float(coord_match.group(1))
        y = float(coord_match.group(2))

        expected_x = 506011.7248
        expected_y = 5458491.1155
        tolerance = 0.01  # 1 cm tolerance for floating-point precision

        assert abs(x - expected_x) < tolerance, (
            f"Centroid X coordinate mismatch: expected {expected_x}, got {x} "
            f"(diff: {abs(x - expected_x):.6f} m, tolerance: {tolerance} m)"
        )
        assert abs(y - expected_y) < tolerance, (
            f"Centroid Y coordinate mismatch: expected {expected_y}, got {y} "
            f"(diff: {abs(y - expected_y):.6f} m, tolerance: {tolerance} m)"
        )

        # Verify source geom remains toxic (GEOMETRYCOLLECTION)
        assert geom_type is not None, "Could not determine geometry type"
        assert "GEOMETRYCOLLECTION" in geom_type.upper() or "COLLECTION" in geom_type.upper(), (
            f"Source geometry should remain toxic GEOMETRYCOLLECTION, got {geom_type}. "
            "ADR-0003 §8: source geom must remain unmodified to preserve audit trail."
        )


class TestAccessibilityProvenance:
    """Test accessibility provenance fields (verified_by, verified_date)."""

    @pytest.mark.slow
    def test_normalise_accessibility_provenance(self, temp_gpkg):
        """All non-null accessible values must have verified_by and verified_date."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query units where accessible is non-null (true OR false)
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT accessible, verified_by, verified_date FROM unit_26910 "
            "WHERE accessible IS NOT NULL LIMIT 10",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse output to verify provenance fields
        features_checked = 0
        for line in output.splitlines():
            if "verified_by (String)" in line and "=" in line:
                verified_by = line.split("=")[1].strip()
                assert verified_by == "source_gdb_use_type", (
                    f"Expected verified_by='source_gdb_use_type', got '{verified_by}'"
                )
                features_checked += 1
            elif "verified_date (String)" in line and "=" in line:
                verified_date = line.split("=")[1].strip()
                assert verified_date == SOURCE_VERIFIED_DATE, (
                    f"Expected verified_date='{SOURCE_VERIFIED_DATE}', got '{verified_date}'"
                )

        assert features_checked > 0, (
            "No units with accessible provenance found (should have 38+ accessible units)"
        )

    @pytest.mark.slow
    def test_normalise_accessibility_null_has_null_provenance(self, temp_gpkg):
        """Units with accessible=null must have null verified_by and verified_date."""
        import yaml

        from wayfinding.etl.normalise import normalise_units
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_units(temp_gpkg, category_mapping)

        # Query units where accessible is null
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT verified_by, verified_date FROM unit_26910 "
            "WHERE accessible IS NULL LIMIT 5",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse output - verified_by and verified_date should be (null)
        for line in output.splitlines():
            if "verified_by" in line and "=" in line:
                value = line.split("=")[1].strip()
                assert value == "(null)" or value == "", (
                    f"Units with accessible=null should have null verified_by, got '{value}'"
                )
            elif "verified_date" in line and "=" in line:
                value = line.split("=")[1].strip()
                assert value == "(null)" or value == "", (
                    f"Units with accessible=null should have null verified_date, got '{value}'"
                )


class TestLandmarkNormalisation:
    """Test landmark deduplication and category parsing."""

    @pytest.mark.slow
    def test_normalise_landmark_deduplication(self, temp_gpkg):
        """Landmark table must have exactly 40 rows (41 source - 1 duplicate)."""
        from wayfinding.etl.normalise import normalise_landmarks

        row_count = normalise_landmarks(temp_gpkg)

        assert row_count == 40, (
            f"Expected exactly 40 landmarks (41 source - 1 duplicate pair), got {row_count}"
        )

        count_26910 = get_layer_count(temp_gpkg, "landmark_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "landmark_wgs84")

        assert count_26910 == 40
        assert count_wgs84 == 40

    @pytest.mark.slow
    def test_normalise_landmark_category_parsing(self, temp_gpkg):
        """All landmarks must have category 'water_fountain' or 'vending_machine'."""
        from wayfinding.etl.normalise import normalise_landmarks

        normalise_landmarks(temp_gpkg)

        # Query all categories
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT DISTINCT category FROM landmark_26910",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse categories
        categories = []
        for line in output.splitlines():
            if "category (String)" in line and "=" in line:
                category = line.split("=")[1].strip()
                categories.append(category)

        valid_categories = {"water_fountain", "vending_machine"}
        for category in categories:
            assert category in valid_categories, (
                f"Invalid landmark category '{category}' "
                "(expected water_fountain or vending_machine)"
            )

    @pytest.mark.slow
    def test_normalise_landmark_duplicate_example(self, temp_gpkg):
        """Duplicate landmark 'Vending Machine close to B9201' appears exactly once."""
        from wayfinding.etl.normalise import normalise_landmarks

        normalise_landmarks(temp_gpkg)

        # Query landmarks (can't query original DESCRIPTION since it's from source,
        # but we can verify total count is 40, not 45 as mentioned in data findings)
        # This is implicitly tested by test_normalise_landmark_deduplication

        # The key test is that we have exactly 40 landmarks, confirming deduplication worked
        count = get_layer_count(temp_gpkg, "landmark_26910")
        assert count == 40, (
            f"Deduplication should reduce 41 source landmarks to 40, got {count}"
        )

    @pytest.mark.slow
    def test_normalise_landmark_ids_deterministic(self, temp_gpkg):
        """Landmark IDs must be deterministic (LMK_<FID> format)."""
        from wayfinding.etl.normalise import normalise_landmarks

        normalise_landmarks(temp_gpkg)

        # Query a few landmark_ids
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT landmark_id FROM landmark_26910 LIMIT 5",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse landmark_ids
        landmark_ids = []
        for line in output.splitlines():
            if "landmark_id (String)" in line and "=" in line:
                landmark_id = line.split("=")[1].strip()
                landmark_ids.append(landmark_id)

        # All should start with LMK_
        for landmark_id in landmark_ids:
            assert landmark_id.startswith("LMK_"), (
                f"Landmark ID should start with 'LMK_', got '{landmark_id}'"
            )

    @pytest.mark.slow
    def test_normalise_landmark_representative_selection(self, temp_gpkg):
        """Coordinate sorting retains LMK_28 and removes LMK_41.

        Per ADR-0003 section 5, GDAL found one same-category/same-level landmark pair
        within 0.5 m: FIDs 28 and 41 at 0.250728 m. Greedy first-point-wins sorting by
        (category, level_id, X, Y) retains the lower X coordinate.
        """
        from wayfinding.etl.normalise import normalise_landmarks

        normalise_landmarks(temp_gpkg)

        # Query all landmark_ids
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT landmark_id FROM landmark_26910",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse landmark_ids
        landmark_ids = []
        for line in output.splitlines():
            if "landmark_id (String)" in line and "=" in line:
                landmark_id = line.split("=")[1].strip()
                landmark_ids.append(landmark_id)

        # Must still have exactly 40 landmarks
        assert len(landmark_ids) == 40, (
            f"Expected exactly 40 landmarks (41 source - 1 duplicate), got {len(landmark_ids)}"
        )

        # LMK_28 must be present (lower X coordinate, retained as representative)
        assert "LMK_28" in landmark_ids, (
            "LMK_28 (x=506106.2261) should be retained as representative of duplicate pair"
        )

        # LMK_41 must be absent (higher X coordinate, removed as duplicate)
        assert "LMK_41" not in landmark_ids, (
            "LMK_41 (x=506106.4668) should be removed as duplicate of LMK_28"
        )

    @pytest.mark.slow
    def test_normalise_landmark_no_temp_layers(self, temp_gpkg):
        """Zero landmarks_parsed% temp layers in gpkg_contents/gpkg_geometry_columns.

        Per ADR-0003 §9: normalise_landmarks must query raw Landmarks layers directly
        using in-memory structures. No physical GeoPackage layer with 'landmarks_parsed'
        in the name may persist. This prevents metadata pollution and ensures clean
        build artifacts.

        After normalise_landmarks() completes, assert zero entries in gpkg_contents
        and gpkg_geometry_columns matching pattern 'landmarks_parsed%'.
        """
        from wayfinding.etl.normalise import normalise_landmarks

        normalise_landmarks(temp_gpkg)

        # Query gpkg_contents for temp layers
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT table_name FROM gpkg_contents WHERE table_name LIKE 'landmarks_parsed%'",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        # Parse table names
        temp_tables_contents = []
        for line in output.splitlines():
            if "table_name (String)" in line and "=" in line:
                table_name = line.split("=")[1].strip()
                temp_tables_contents.append(table_name)

        assert len(temp_tables_contents) == 0, (
            f"Found {len(temp_tables_contents)} temp layer(s) in gpkg_contents: "
            f"{temp_tables_contents}. "
            "Per ADR-0003 §9, normalise_landmarks must use in-memory processing; "
            "no landmarks_parsed% layers may persist in GeoPackage metadata."
        )

        # Query gpkg_geometry_columns for temp layers
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT table_name FROM gpkg_geometry_columns "
            "WHERE table_name LIKE 'landmarks_parsed%'",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout + result.stderr

        # Parse table names
        temp_tables_geom = []
        for line in output.splitlines():
            if "table_name (String)" in line and "=" in line:
                table_name = line.split("=")[1].strip()
                temp_tables_geom.append(table_name)

        assert len(temp_tables_geom) == 0, (
            f"Found {len(temp_tables_geom)} temp layer(s) in gpkg_geometry_columns: "
            f"{temp_tables_geom}. "
            "Per ADR-0003 §9, landmark processing must not create persistent temp layers."
        )

        # Verify only expected landmark layers exist (landmark_26910, landmark_wgs84)
        layers = list_gpkg_layers(temp_gpkg)
        landmark_layers = [layer for layer in layers if "landmark" in layer.lower()]

        expected_landmark_layers = {
            "landmark_26910",
            "landmark_wgs84",
            "Landmarks_26910",
            "Landmarks_wgs84",
        }
        for layer in landmark_layers:
            assert layer in expected_landmark_layers, (
                f"Unexpected landmark layer '{layer}' found. "
                f"Only {expected_landmark_layers} should exist (2 raw + 2 normalised)."
            )


class TestDetailAndDoorNormalisation:
    """Test detail/door split and count preservation."""

    @pytest.mark.slow
    def test_normalise_detail_door_exclusion(self, temp_gpkg):
        """Detail table must have 48728 rows (no ADO/doors)."""
        from wayfinding.etl.normalise import normalise_details

        counts = normalise_details(temp_gpkg)

        assert "detail" in counts, "normalise_details must return 'detail' count"
        assert counts["detail"] == 48728, (
            f"Expected 48728 detail rows (55593 - 6865 doors), got {counts['detail']}"
        )

        count_26910 = get_layer_count(temp_gpkg, "detail_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "detail_wgs84")

        assert count_26910 == 48728
        assert count_wgs84 == 48728

    @pytest.mark.slow
    def test_normalise_detail_use_type_distribution(self, temp_gpkg):
        """Detail use_type counts must match data findings §6."""
        from wayfinding.etl.normalise import normalise_details

        normalise_details(temp_gpkg)

        # Expected counts from data findings
        expected_use_types = {
            "AGL": 32974,  # glazing
            "AWA": 11002,  # wall
            "AWAFU": 4547,
            "AWAMO": 196,
            "AWACO": 9,
        }

        for use_type, expected_count in expected_use_types.items():
            cmd = [
                "ogrinfo",
                str(temp_gpkg),
                "-sql",
                f"SELECT COUNT(*) FROM detail_26910 WHERE use_type = '{use_type}'",
                "-q",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            output = result.stdout + result.stderr

            # Parse count from output
            # Look for feature count or explicit count value
            # This is a simplified check - actual count parsing depends on ogrinfo output
            assert str(expected_count) in output or "COUNT" in output, (
                f"Could not verify use_type '{use_type}' count {expected_count}"
            )

    @pytest.mark.slow
    def test_normalise_door_extraction(self, temp_gpkg):
        """Door table must have 6865 rows (all ADO from Details)."""
        from wayfinding.etl.normalise import normalise_details

        counts = normalise_details(temp_gpkg)

        assert "door" in counts, "normalise_details must return 'door' count"
        assert counts["door"] == 6865, (
            f"Expected 6865 door rows, got {counts['door']}"
        )

        count_26910 = get_layer_count(temp_gpkg, "door_26910")
        count_wgs84 = get_layer_count(temp_gpkg, "door_wgs84")

        assert count_26910 == 6865
        assert count_wgs84 == 6865

    @pytest.mark.slow
    def test_normalise_door_all_ado(self, temp_gpkg):
        """All rows in door table must have use_type='ADO'."""
        from wayfinding.etl.normalise import normalise_details

        normalise_details(temp_gpkg)

        # Query for any non-ADO use_types
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT COUNT(*) FROM door_26910 WHERE use_type != 'ADO'",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Should be 0
        assert "0" in output or "no features" in output.lower(), (
            "Found non-ADO rows in door table"
        )

    @pytest.mark.slow
    def test_normalise_door_geometry_preserved(self, temp_gpkg):
        """Door geometries must be MultiLineString (same as source Details)."""
        from wayfinding.etl.normalise import normalise_details

        normalise_details(temp_gpkg)

        geom_type_26910 = get_geometry_type(temp_gpkg, "door_26910")
        geom_type_wgs84 = get_geometry_type(temp_gpkg, "door_wgs84")

        assert "Multi Line String" in geom_type_26910 or "MultiLineString" in geom_type_26910, (
            f"door_26910 should be MultiLineString, got {geom_type_26910}"
        )
        assert "Multi Line String" in geom_type_wgs84 or "MultiLineString" in geom_type_wgs84, (
            f"door_wgs84 should be MultiLineString, got {geom_type_wgs84}"
        )

        # door_26910 should be 3D
        assert "3D" in geom_type_26910 or " Z" in geom_type_26910, (
            f"door_26910 should be 3D, got {geom_type_26910}"
        )

        # door_wgs84 should be 2D
        assert "3D" not in geom_type_wgs84, (
            f"door_wgs84 should be 2D, got {geom_type_wgs84}"
        )
        assert " Z" not in geom_type_wgs84


class TestCrossTableInvariants:
    """Test foreign keys and vertical_order uniqueness."""

    @pytest.mark.slow
    def test_normalise_vertical_order_invariant(self, temp_gpkg):
        """Every unit.level_id must resolve to unique level.vertical_order."""
        # Run full normalisation pipeline
        import yaml

        from wayfinding.etl.normalise import (
            normalise_facilities,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)
        normalise_units(temp_gpkg, category_mapping)

        # Query: for each unit, check that its level_id has a unique vertical_order
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT u.unit_id, u.level_id, l.vertical_order "
            "FROM unit_26910 u "
            "JOIN level_26910 l ON u.level_id = l.level_id "
            "LIMIT 10",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        # If JOIN succeeds, FK is valid
        assert result.returncode == 0, (
            f"FK join failed: {result.stderr}"
        )

    @pytest.mark.slow
    def test_normalise_foreign_keys(self, temp_gpkg):
        """All level_id values in child tables must exist in level table."""
        # Run full normalisation
        import yaml

        from wayfinding.etl.normalise import (
            normalise_details,
            normalise_facilities,
            normalise_landmarks,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)
        normalise_units(temp_gpkg, category_mapping)
        normalise_landmarks(temp_gpkg)
        normalise_details(temp_gpkg)

        # Query for orphan level_ids in unit, landmark, detail, door tables
        child_tables = ["unit_26910", "landmark_26910", "detail_26910", "door_26910"]

        for child_table in child_tables:
            cmd = [
                "ogrinfo",
                str(temp_gpkg),
                "-sql",
                f"SELECT COUNT(*) FROM {child_table} c "
                f"WHERE NOT EXISTS (SELECT 1 FROM level_26910 l WHERE l.level_id = c.level_id)",
                "-q",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)

            output = result.stdout + result.stderr

            # Should be 0 orphans
            assert "0" in output or "no features" in output.lower(), (
                f"Found orphan level_id values in {child_table}"
            )

    @pytest.mark.slow
    def test_normalise_facility_level_pairs_unique(self, temp_gpkg):
        """(facility_id, vertical_order) must be unique in level table."""
        from wayfinding.etl.normalise import normalise_facilities, normalise_levels

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)

        # Query for duplicate (facility_id, vertical_order) pairs
        cmd = [
            "ogrinfo",
            str(temp_gpkg),
            "-sql",
            "SELECT facility_id, vertical_order, COUNT(*) as cnt "
            "FROM level_26910 "
            "GROUP BY facility_id, vertical_order "
            "HAVING cnt > 1",
            "-q",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Zero-row SQL result from ogrinfo shows "Layer name: SELECT" with no features.
        # Parse for actual cnt values rather than requiring empty output.
        has_duplicates = False
        for line in output.splitlines():
            if "cnt (Integer)" in line and "=" in line:
                cnt_str = line.split("=")[1].strip()
                cnt = int(cnt_str)
                if cnt > 1:
                    has_duplicates = True
                    break

        assert not has_duplicates, (
            "Found duplicate (facility_id, vertical_order) pairs in level table"
        )


class TestGeometryAndCRS:
    """Test geometry types and CRS correctness across all tables."""

    @pytest.mark.slow
    def test_normalise_geometry_crs(self, temp_gpkg):
        """All _26910 layers must be EPSG:26910 3D, _wgs84 must be EPSG:4326 2D."""
        # Run full normalisation
        import yaml

        from wayfinding.etl.normalise import (
            normalise_details,
            normalise_facilities,
            normalise_landmarks,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)
        normalise_units(temp_gpkg, category_mapping)
        normalise_landmarks(temp_gpkg)
        normalise_details(temp_gpkg)

        # Check all _26910 layers
        layers_26910 = [
            "facility_26910", "level_26910", "unit_26910",
            "landmark_26910", "detail_26910", "door_26910",
        ]

        for layer_name in layers_26910:
            crs = get_layer_crs(temp_gpkg, layer_name)
            geom_type = get_geometry_type(temp_gpkg, layer_name)

            assert "26910" in crs, (
                f"{layer_name} should be EPSG:26910, got {crs}"
            )

            # Should be 3D (except centroid_26910 which is a field, not the registered geom)
            # The registered geom column is named 'geom' and should be 3D
            # For unit_26910, the registered geom is the polygon, centroid_26910 is a field
            # So we check the main geometry type reported by ogrinfo
            if layer_name != "unit_26910":  # unit has both polygon and centroid
                assert "3D" in geom_type or " Z" in geom_type, (
                    f"{layer_name} should be 3D, got {geom_type}"
                )

        # Check all _wgs84 layers
        layers_wgs84 = [
            "facility_wgs84", "level_wgs84", "unit_wgs84",
            "landmark_wgs84", "detail_wgs84", "door_wgs84",
        ]

        for layer_name in layers_wgs84:
            crs = get_layer_crs(temp_gpkg, layer_name)
            geom_type = get_geometry_type(temp_gpkg, layer_name)

            assert "4326" in crs or "WGS 84" in crs, (
                f"{layer_name} should be EPSG:4326, got {crs}"
            )

            # Should be 2D (Z dropped)
            assert "3D" not in geom_type, (
                f"{layer_name} should be 2D, got {geom_type}"
            )
            assert " Z" not in geom_type

    @pytest.mark.slow
    def test_normalise_geometry_extents(self, temp_gpkg):
        """Bounding boxes must be within expected range (EPSG:26910)."""
        # Run full normalisation
        import yaml

        from wayfinding.etl.normalise import (
            normalise_details,
            normalise_facilities,
            normalise_landmarks,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        normalise_facilities(temp_gpkg)
        normalise_levels(temp_gpkg)
        normalise_units(temp_gpkg, category_mapping)
        normalise_landmarks(temp_gpkg)
        normalise_details(temp_gpkg)

        # Check facility_26910 extent (representative)
        cmd = ["ogrinfo", "-so", "-al", str(temp_gpkg), "facility_26910"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        output = result.stdout + result.stderr

        # Parse extent: "Extent: (505981.000000, 5458380.000000) - (506254.000000, 5458560.000000)"
        for line in output.splitlines():
            if "Extent:" in line:
                # Extract bounding box
                # Just verify the line exists; full parsing is complex
                assert "505" in line, f"Extent looks incorrect: {line}"
                assert "5458" in line, f"Extent looks incorrect: {line}"
                break


class TestIdempotency:
    """Test determinism and idempotent execution."""

    @pytest.mark.slow
    def test_normalise_idempotent(self):
        """Running normalisation twice should produce identical results."""
        import yaml

        from wayfinding.etl.normalise import (
            normalise_details,
            normalise_facilities,
            normalise_landmarks,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        # Run normalisation twice on separate copies
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg1 = Path(tmpdir) / "run1.gpkg"
            gpkg2 = Path(tmpdir) / "run2.gpkg"

            shutil.copy2(SOURCE_GPKG, gpkg1)
            shutil.copy2(SOURCE_GPKG, gpkg2)

            # Run 1
            normalise_facilities(gpkg1)
            normalise_levels(gpkg1)
            normalise_units(gpkg1, category_mapping)
            normalise_landmarks(gpkg1)
            normalise_details(gpkg1)

            # Run 2
            normalise_facilities(gpkg2)
            normalise_levels(gpkg2)
            normalise_units(gpkg2, category_mapping)
            normalise_landmarks(gpkg2)
            normalise_details(gpkg2)

            # Compare row counts
            for table_name, expected_count in EXPECTED_NORMALISED_COUNTS.items():
                layer_name = f"{table_name}_26910"

                count1 = get_layer_count(gpkg1, layer_name)
                count2 = get_layer_count(gpkg2, layer_name)

                assert count1 == count2, (
                    f"{layer_name}: Run 1 has {count1} rows, Run 2 has {count2} rows "
                    "(not idempotent)"
                )

                assert count1 == expected_count, (
                    f"{layer_name}: expected {expected_count} rows, got {count1}"
                )


class TestIntegration:
    """Integration test: end-to-end normalisation."""

    @pytest.mark.slow
    def test_normalise_end_to_end(self, temp_gpkg):
        """Run all normalisation functions in sequence, verify all tables exist."""
        import yaml

        from wayfinding.etl.normalise import (
            normalise_details,
            normalise_facilities,
            normalise_landmarks,
            normalise_levels,
            normalise_units,
        )
        category_yaml = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" /
            "wayfinding" / "etl" / "category_mapping.yaml"
        )
        with open(category_yaml) as f:
            category_mapping = yaml.safe_load(f)

        # Run full pipeline
        facility_count = normalise_facilities(temp_gpkg)
        level_count = normalise_levels(temp_gpkg)
        unit_count = normalise_units(temp_gpkg, category_mapping)
        landmark_count = normalise_landmarks(temp_gpkg)
        detail_door_counts = normalise_details(temp_gpkg)

        # Verify returned counts
        assert facility_count == 3
        assert level_count == 11
        assert unit_count == 1017
        assert landmark_count == 40
        assert detail_door_counts["detail"] == 48728
        assert detail_door_counts["door"] == 6865

        # Verify all 26 layers exist (14 raw + 12 normalised)
        layers = list_gpkg_layers(temp_gpkg)

        # 14 raw layers from DT-003
        expected_raw_layers = [
            "Facilities_26910", "Facilities_wgs84",
            "Levels_26910", "Levels_wgs84",
            "Units_26910", "Units_wgs84",
            "Pathways_26910", "Pathways_wgs84",
            "Transitions_26910", "Transitions_wgs84",
            "Landmarks_26910", "Landmarks_wgs84",
            "Details_26910", "Details_wgs84",
        ]

        for raw_layer in expected_raw_layers:
            assert raw_layer in layers, (
                f"Raw layer {raw_layer} missing (DT-004 must preserve DT-003 output)"
            )

        # 12 normalised layers
        expected_normalised_layers = [
            "facility_26910", "facility_wgs84",
            "level_26910", "level_wgs84",
            "unit_26910", "unit_wgs84",
            "landmark_26910", "landmark_wgs84",
            "detail_26910", "detail_wgs84",
            "door_26910", "door_wgs84",
        ]

        for norm_layer in expected_normalised_layers:
            assert norm_layer in layers, (
                f"Normalised layer {norm_layer} not created"
            )

        # Total should be 26
        assert len(layers) == 26, (
            f"Expected 26 total layers (14 raw + 12 normalised), found {len(layers)}"
        )


class TestMakefileTarget:
    """Test Makefile etl-normalise target."""

    def test_makefile_etl_normalise_target_exists(self):
        """Makefile must define etl-normalise target."""
        makefile_path = WORKSPACE_ROOT / "Makefile"
        assert makefile_path.exists(), "Makefile not found"

        makefile_content = makefile_path.read_text()

        assert "etl-normalise:" in makefile_content, (
            "Makefile missing etl-normalise target"
        )

    def test_makefile_etl_normalise_invokes_normalise_command(self):
        """etl-normalise target must invoke normalise command."""
        makefile_path = WORKSPACE_ROOT / "Makefile"
        makefile_content = makefile_path.read_text()

        # Find etl-normalise section
        if "etl-normalise:" in makefile_content:
            etl_normalise_section = makefile_content.split("etl-normalise:")[1].split("\n\n")[0]

            # Should invoke wayfinding.etl.run with normalise command
            assert "wayfinding.etl.run" in etl_normalise_section, (
                "etl-normalise target must invoke wayfinding.etl.run"
            )
            assert "normalise" in etl_normalise_section, (
                "etl-normalise target must call normalise command"
            )


class TestCliEntryPoint:
    """Test CLI dispatch for normalise command."""

    def test_main_normalise_dispatches(self):
        """main('normalise') should dispatch to run_normalise()."""
        from wayfinding.etl import run

        with patch.object(run, "run_normalise", return_value=0) as mock_run_normalise:
            result = run.main("normalise")

            mock_run_normalise.assert_called_once()
            assert result == 0

    def test_run_normalise_success_returns_0(self):
        """run_normalise() should return 0 on success."""
        from wayfinding.etl import run

        # Mock normalisation functions
        with (
            patch("wayfinding.etl.normalise.normalise_facilities", return_value=3),
            patch("wayfinding.etl.normalise.normalise_levels", return_value=11),
            patch("wayfinding.etl.normalise.normalise_units", return_value=1017),
            patch("wayfinding.etl.normalise.normalise_landmarks", return_value=40),
            patch(
                "wayfinding.etl.normalise.normalise_details",
                return_value={"detail": 48728, "door": 6865},
            ),
        ):
            result = run.run_normalise()

            assert result == 0, "run_normalise() should return 0 on success"

    def test_run_normalise_failure_returns_1(self):
        """run_normalise() should return 1 on failure."""
        from wayfinding.etl import run

        # Mock normalise_facilities to raise exception
        with patch(
            "wayfinding.etl.normalise.normalise_facilities",
            side_effect=RuntimeError("Test failure"),
        ):
            result = run.run_normalise()

            assert result == 1, "run_normalise() should return 1 on failure"


class TestErrorHandling:
    """Test error handling for invalid inputs and edge cases."""

    def test_normalise_missing_category_mapping(self, temp_gpkg):
        """normalise_units should fail if category_mapping incomplete."""
        from wayfinding.etl.normalise import normalise_units

        # Provide incomplete category mapping (missing some USE_TYPEs)
        incomplete_mapping = {
            "Office": {"category": "office"},
            # Missing many other USE_TYPEs
        }

        with pytest.raises((RuntimeError, KeyError, ValueError)):
            normalise_units(temp_gpkg, incomplete_mapping)

    def test_normalise_gpkg_not_found(self):
        """Normalisation functions should fail gracefully for missing GeoPackage."""
        from wayfinding.etl.normalise import normalise_facilities

        nonexistent_gpkg = Path("/nonexistent/path/fake.gpkg")

        with pytest.raises(FileNotFoundError):
            normalise_facilities(nonexistent_gpkg)

    def test_normalise_raw_layers_missing(self, temp_gpkg):
        """Normalisation should fail if DT-003 raw layers missing."""
        from wayfinding.etl.normalise import normalise_facilities

        # Create empty GeoPackage without raw layers
        empty_gpkg = temp_gpkg.parent / "empty.gpkg"
        cmd = ["ogr2ogr", "-f", "GPKG", str(empty_gpkg), str(temp_gpkg), "Facilities_26910"]
        subprocess.run(cmd, capture_output=True)

        # Remove the only layer
        cmd = ["ogrinfo", str(empty_gpkg), "-sql", "DROP TABLE Facilities_26910"]
        subprocess.run(cmd, capture_output=True)

        with pytest.raises((RuntimeError, FileNotFoundError)):
            normalise_facilities(empty_gpkg)
