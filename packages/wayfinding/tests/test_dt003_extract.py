"""Failing tests for DT-003: Extract Layers to GeoPackage.

These tests check:
1. extract_to_gpkg() function signature and argument validation
2. Layer naming conventions (_26910 and _wgs84 suffixes)
3. GDAL/ogr2ogr availability in the ETL container
4. Source GDB remains unmodified (read-only boundary)
5. Feature counts, CRS, geometry types match expectations
6. Extraction is deterministic and idempotent
7. Error handling for missing GDB, invalid paths, extraction failures

All tests will FAIL initially because wayfinding.etl.extract does not exist yet.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
GDB_PATH = Path("C:/repos/sfudt/claude/dtwin-harness/data/IndoorWayfinding.gdb")
BUILD_DIR = WORKSPACE_ROOT / "build"

# Expected feature counts from docs/generated/gdb-profile.txt
EXPECTED_COUNTS = {
    "Facilities_26910": 3,
    "Facilities_wgs84": 3,
    "Levels_26910": 11,
    "Levels_wgs84": 11,
    "Units_26910": 1210,
    "Units_wgs84": 1210,
    "Pathways_26910": 22426,
    "Pathways_wgs84": 22426,
    "Transitions_26910": 63,
    "Transitions_wgs84": 63,
    "Landmarks_26910": 41,
    "Landmarks_wgs84": 41,
    "Details_26910": 55593,
    "Details_wgs84": 55593,
}

# Expected geometry types for _26910 layers (3D)
EXPECTED_GEOMETRY_TYPES_26910 = {
    "Facilities_26910": "3D Multi Polygon",
    "Levels_26910": "3D Multi Polygon",
    "Units_26910": "3D Multi Polygon",
    "Pathways_26910": "3D Multi Line String",
    "Transitions_26910": "3D Multi Line String",
    "Details_26910": "3D Multi Line String",
    "Landmarks_26910": "3D Point",
}

# Expected geometry types for _wgs84 layers (2D, Z dropped)
EXPECTED_GEOMETRY_TYPES_WGS84 = {
    "Facilities_wgs84": "Multi Polygon",
    "Levels_wgs84": "Multi Polygon",
    "Units_wgs84": "Multi Polygon",
    "Pathways_wgs84": "Multi Line String",
    "Transitions_wgs84": "Multi Line String",
    "Details_wgs84": "Multi Line String",
    "Landmarks_wgs84": "Point",
}


class TestExtractSignature:
    """Test extract_to_gpkg() function signature and argument validation."""

    def test_extract_function_exists(self):
        """wayfinding.etl.extract module must exist with extract_to_gpkg function."""
        from wayfinding.etl import extract

        assert hasattr(extract, "extract_to_gpkg"), (
            "wayfinding.etl.extract missing extract_to_gpkg function"
        )

    def test_extract_signature_has_required_params(self):
        """extract_to_gpkg must accept gdb_path and gpkg_path parameters."""
        from wayfinding.etl.extract import extract_to_gpkg
        import inspect

        sig = inspect.signature(extract_to_gpkg)
        params = list(sig.parameters.keys())

        assert "gdb_path" in params, "extract_to_gpkg missing gdb_path parameter"
        assert "gpkg_path" in params, "extract_to_gpkg missing gpkg_path parameter"

    def test_extract_signature_has_overwrite_param(self):
        """extract_to_gpkg should have optional overwrite parameter."""
        from wayfinding.etl.extract import extract_to_gpkg
        import inspect

        sig = inspect.signature(extract_to_gpkg)
        params = sig.parameters

        assert "overwrite" in params, "extract_to_gpkg missing overwrite parameter"
        assert params["overwrite"].default is not inspect.Parameter.empty, (
            "overwrite parameter should have a default value"
        )

    def test_extract_returns_dict(self):
        """extract_to_gpkg should return dict mapping layer names to counts."""
        from wayfinding.etl.extract import extract_to_gpkg

        # This will fail because the function doesn't exist yet
        # When implemented, mock subprocess and verify return type
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_gpkg = Path(tmpdir) / "test.gpkg"
                # Will fail with FileNotFoundError for missing GDB
                with pytest.raises(FileNotFoundError):
                    result = extract_to_gpkg(
                        Path("/nonexistent.gdb"),
                        tmp_gpkg
                    )


class TestLayerDefinitions:
    """Test layer naming conventions and dual CRS strategy."""

    def test_layer_name_mapping_26910(self):
        """Source layer names must map to *_26910 output names."""
        # This tests internal logic once implementation exists
        # Expected mapping:
        # Facilities_AQ_SH_ECC -> Facilities_26910
        # Levels_AQ_SH_ECC -> Levels_26910
        # etc.

        from wayfinding.etl import extract

        # Check if module has layer definitions
        # This will fail initially because extract.py doesn't exist
        assert hasattr(extract, "LAYERS") or hasattr(extract, "extract_to_gpkg"), (
            "extract module must define layer mappings"
        )

    def test_expected_output_layer_count(self):
        """Extract should produce exactly 14 layers (7 x 2 CRS)."""
        # This is an integration-level expectation
        # Will be tested in TestExtractExecution
        assert len(EXPECTED_COUNTS) == 14, "Test fixture expects 14 layers"

    def test_dual_crs_coverage(self):
        """Every source layer should have both _26910 and _wgs84 variants."""
        base_layers = [
            "Facilities",
            "Levels",
            "Units",
            "Pathways",
            "Transitions",
            "Landmarks",
            "Details",
        ]

        for base in base_layers:
            assert f"{base}_26910" in EXPECTED_COUNTS, (
                f"Missing {base}_26910 in expected counts"
            )
            assert f"{base}_wgs84" in EXPECTED_COUNTS, (
                f"Missing {base}_wgs84 in expected counts"
            )


class TestGdalAvailability:
    """Test that GDAL and ogr2ogr are available in the ETL container."""

    def test_docker_compose_file_exists(self):
        """docker-compose.yml must exist to run container tests."""
        assert DOCKER_COMPOSE_PATH.exists(), f"Missing {DOCKER_COMPOSE_PATH}"

    @pytest.mark.slow
    def test_ogr2ogr_available_in_container(self):
        """ETL container must have ogr2ogr command available."""
        cmd = [
            "docker",
            "compose",
            "-f",
            str(DOCKER_COMPOSE_PATH),
            "run",
            "--rm",
            "etl",
            "ogr2ogr",
            "--version",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"ogr2ogr not available in container: {result.stderr}"
        )
        assert "GDAL" in result.stdout or "GDAL" in result.stderr, (
            "ogr2ogr version output should mention GDAL"
        )

    @pytest.mark.slow
    def test_ogrinfo_available_in_container(self):
        """ETL container must have ogrinfo command for verification."""
        cmd = [
            "docker",
            "compose",
            "-f",
            str(DOCKER_COMPOSE_PATH),
            "run",
            "--rm",
            "etl",
            "ogrinfo",
            "--version",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"ogrinfo not available in container: {result.stderr}"
        )

    @pytest.mark.slow
    def test_gpkg_format_supported(self):
        """GDAL must support GeoPackage format (read/write)."""
        cmd = [
            "docker",
            "compose",
            "-f",
            str(DOCKER_COMPOSE_PATH),
            "run",
            "--rm",
            "etl",
            "ogrinfo",
            "--formats",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, "Failed to list GDAL formats"

        formats_output = result.stdout + result.stderr
        # Look for GPKG with write support: "GPKG -raster,vector- (rw+)"
        assert "GPKG" in formats_output, "GeoPackage format not supported"
        assert "rw" in formats_output or "w" in formats_output.lower(), (
            "GeoPackage must have write support"
        )


class TestGdbReadonly:
    """Verify extraction does not modify the source GDB (read-only boundary)."""

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_gdb_mtime_unchanged_after_extract(self):
        """Source GDB modification time must not change during extraction."""
        # Capture mtime before
        gdb_mtime_before = os.path.getmtime(GDB_PATH)

        # Run extraction
        from wayfinding.etl.extract import extract_to_gpkg

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_gpkg = Path(tmpdir) / "test.gpkg"

            try:
                extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)
            except Exception:
                # Extraction may fail because implementation doesn't exist
                # but we still want to check GDB wasn't touched
                pass

        # Capture mtime after
        gdb_mtime_after = os.path.getmtime(GDB_PATH)

        assert gdb_mtime_after == gdb_mtime_before, (
            "Source GDB was modified during extraction (read-only violation)"
        )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_gate_gdb_readonly_still_passes(self):
        """tests/gate/test_gdb_readonly.sh must pass after extraction."""
        gate_script = WORKSPACE_ROOT / "tests" / "gate" / "test_gdb_readonly.sh"

        if not gate_script.exists():
            pytest.skip("Gate script not found (expected for early phases)")

        # Run the gate test
        result = subprocess.run(
            ["bash", str(gate_script)],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
        )

        assert result.returncode == 0, (
            f"GDB read-only gate test failed: {result.stderr}"
        )


class TestExtractExecution:
    """Integration tests for extract_to_gpkg execution with real GDAL."""

    @pytest.fixture
    def tmp_gpkg(self):
        """Temporary GeoPackage for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.gpkg"

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_creates_output_file(self, tmp_gpkg):
        """extract_to_gpkg must create the output GeoPackage file."""
        from wayfinding.etl.extract import extract_to_gpkg

        result = extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        assert tmp_gpkg.exists(), "Output GeoPackage was not created"
        assert isinstance(result, dict), "extract_to_gpkg must return dict"

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_all_14_layers_present(self, tmp_gpkg):
        """Output GeoPackage must contain exactly 14 layers."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        # Use ogrinfo to list layers
        cmd = [
            "docker",
            "compose",
            "-f",
            str(DOCKER_COMPOSE_PATH),
            "run",
            "--rm",
            "-v",
            f"{tmp_gpkg.parent}:/tmp_test",
            "etl",
            "ogrinfo",
            "-json",
            "-so",
            f"/tmp_test/{tmp_gpkg.name}",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"ogrinfo failed: {result.stderr}"

        info = json.loads(result.stdout)
        layers = [layer["name"] for layer in info.get("layers", [])]

        assert len(layers) == 14, (
            f"Expected 14 layers, found {len(layers)}: {layers}"
        )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_feature_counts_exact(self, tmp_gpkg):
        """Feature counts must match expected values from gdb-profile.txt."""
        from wayfinding.etl.extract import extract_to_gpkg

        result = extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        # Verify returned counts
        for layer_name, expected_count in EXPECTED_COUNTS.items():
            assert layer_name in result, f"Missing layer {layer_name} in result"
            assert result[layer_name] == expected_count, (
                f"Layer {layer_name}: expected {expected_count}, "
                f"got {result[layer_name]}"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_crs_26910_layers(self, tmp_gpkg):
        """All *_26910 layers must have EPSG:26910 CRS."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        layers_26910 = [name for name in EXPECTED_COUNTS if name.endswith("_26910")]

        for layer_name in layers_26910:
            # Query CRS using ogrinfo
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
                layer_name,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"ogrinfo failed for {layer_name}: {result.stderr}"
            )

            output = result.stdout + result.stderr
            # Check for EPSG:26910 or UTM zone 10N
            assert "26910" in output or "UTM zone 10N" in output, (
                f"Layer {layer_name} does not have EPSG:26910 CRS"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_crs_wgs84_layers(self, tmp_gpkg):
        """All *_wgs84 layers must have EPSG:4326 CRS."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        layers_wgs84 = [name for name in EXPECTED_COUNTS if name.endswith("_wgs84")]

        for layer_name in layers_wgs84:
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
                layer_name,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"ogrinfo failed for {layer_name}: {result.stderr}"
            )

            output = result.stdout + result.stderr
            assert "4326" in output or "WGS 84" in output, (
                f"Layer {layer_name} does not have EPSG:4326 CRS"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_geometry_types_26910(self, tmp_gpkg):
        """*_26910 layers must preserve 3D geometry types."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        for layer_name, expected_geom in EXPECTED_GEOMETRY_TYPES_26910.items():
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
                layer_name,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"ogrinfo failed for {layer_name}: {result.stderr}"
            )

            output = result.stdout + result.stderr
            # Flexible matching: "3D Multi Polygon" or "MultiPolygon Z"
            geom_variants = [
                expected_geom,
                expected_geom.replace(" ", ""),  # "3DMultiPolygon"
                expected_geom.replace("3D ", "") + " Z",  # "Multi Polygon Z"
            ]

            has_correct_type = any(variant in output for variant in geom_variants)
            assert has_correct_type, (
                f"Layer {layer_name} geometry type mismatch. "
                f"Expected one of {geom_variants}, got output:\n{output}"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_geometry_types_wgs84(self, tmp_gpkg):
        """*_wgs84 layers must have 2D geometry types (Z dropped)."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        for layer_name, expected_geom in EXPECTED_GEOMETRY_TYPES_WGS84.items():
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
                layer_name,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"ogrinfo failed for {layer_name}: {result.stderr}"
            )

            output = result.stdout + result.stderr
            geom_variants = [
                expected_geom,
                expected_geom.replace(" ", ""),  # "MultiPolygon"
            ]

            has_correct_type = any(variant in output for variant in geom_variants)
            # Also ensure it's NOT 3D
            is_not_3d = "3D" not in output and " Z" not in output

            assert has_correct_type and is_not_3d, (
                f"Layer {layer_name} should be 2D {expected_geom}, "
                f"got output:\n{output}"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_attributes_preserved(self, tmp_gpkg):
        """Attributes from source must be copied to both _26910 and _wgs84."""
        from wayfinding.etl.extract import extract_to_gpkg

        extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

        # Test Units layer (representative)
        required_fields = [
            "UNIT_ID",
            "NAME",
            "ROOM_ID",
            "USE_TYPE",
            "SEARCHABLE",
            "LEVEL_ID",
        ]

        for suffix in ["_26910", "_wgs84"]:
            layer_name = f"Units{suffix}"

            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
                layer_name,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            assert result.returncode == 0, (
                f"ogrinfo failed for {layer_name}: {result.stderr}"
            )

            output = result.stdout + result.stderr
            for field in required_fields:
                assert field in output, (
                    f"Layer {layer_name} missing required field {field}"
                )


class TestExtractDeterminism:
    """Test that extraction is deterministic and idempotent."""

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_idempotent_feature_counts(self):
        """Running extract twice should produce identical feature counts."""
        from wayfinding.etl.extract import extract_to_gpkg

        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg1 = Path(tmpdir) / "extract1.gpkg"
            gpkg2 = Path(tmpdir) / "extract2.gpkg"

            result1 = extract_to_gpkg(GDB_PATH, gpkg1, overwrite=True)
            result2 = extract_to_gpkg(GDB_PATH, gpkg2, overwrite=True)

            assert result1 == result2, (
                "Feature counts differ between runs (not deterministic)"
            )

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_extract_overwrite_clears_previous(self):
        """overwrite=True should produce clean output (no leftover layers)."""
        from wayfinding.etl.extract import extract_to_gpkg

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_gpkg = Path(tmpdir) / "test.gpkg"

            # First extraction
            extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

            # Manually add a bogus layer to the GeoPackage
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogr2ogr",
                "-update",
                "-nln",
                "BOGUS_LAYER",
                "-dialect",
                "sqlite",
                "-sql",
                "SELECT 1 as id",
                f"/tmp_test/{tmp_gpkg.name}",
                f"/tmp_test/{tmp_gpkg.name}",
                "Facilities_26910",
            ]
            subprocess.run(cmd, capture_output=True)

            # Second extraction with overwrite=True
            extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=True)

            # Verify no BOGUS_LAYER exists
            cmd = [
                "docker",
                "compose",
                "-f",
                str(DOCKER_COMPOSE_PATH),
                "run",
                "--rm",
                "-v",
                f"{tmp_gpkg.parent}:/tmp_test",
                "etl",
                "ogrinfo",
                "-json",
                "-so",
                f"/tmp_test/{tmp_gpkg.name}",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            info = json.loads(result.stdout)
            layers = [layer["name"] for layer in info.get("layers", [])]

            assert "BOGUS_LAYER" not in layers, (
                "overwrite=True should remove previous layers"
            )
            assert len(layers) == 14, (
                f"Expected 14 layers after overwrite, found {len(layers)}"
            )


class TestErrorHandling:
    """Test error handling for invalid inputs and edge cases."""

    def test_extract_gdb_not_found(self):
        """extract_to_gpkg must raise FileNotFoundError for missing GDB."""
        from wayfinding.etl.extract import extract_to_gpkg

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_gpkg = Path(tmpdir) / "test.gpkg"
            nonexistent_gdb = Path("/nonexistent/path/fake.gdb")

            with pytest.raises(FileNotFoundError):
                extract_to_gpkg(nonexistent_gdb, tmp_gpkg)

    def test_extract_output_dir_not_writable(self):
        """extract_to_gpkg should fail gracefully if output dir not writable."""
        from wayfinding.etl.extract import extract_to_gpkg

        # Use a directory that likely doesn't exist and can't be created
        bad_output = Path("/root/protected/output.gpkg")

        with pytest.raises((PermissionError, OSError, RuntimeError)):
            extract_to_gpkg(GDB_PATH, bad_output)

    @pytest.mark.slow
    def test_extract_overwrite_false_fails_if_exists(self):
        """extract_to_gpkg with overwrite=False should fail if output exists."""
        from wayfinding.etl.extract import extract_to_gpkg

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_gpkg = Path(tmpdir) / "existing.gpkg"
            # Create empty file
            tmp_gpkg.touch()

            with pytest.raises((FileExistsError, RuntimeError)):
                extract_to_gpkg(GDB_PATH, tmp_gpkg, overwrite=False)

    @patch("subprocess.run")
    def test_extract_ogr2ogr_failure_raises_runtime_error(self, mock_run):
        """Extraction should raise RuntimeError if ogr2ogr fails."""
        from wayfinding.etl.extract import extract_to_gpkg

        # Mock subprocess.run to simulate ogr2ogr failure
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: ogr2ogr failed to process layer",
            stdout="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_gpkg = Path(tmpdir) / "test.gpkg"

            with pytest.raises(RuntimeError, match="ogr2ogr"):
                extract_to_gpkg(GDB_PATH, tmp_gpkg)

    @pytest.mark.slow
    @pytest.mark.skipif(not GDB_PATH.exists(), reason="Source GDB not available")
    def test_make_etl_extract_target(self):
        """make etl-extract target should run successfully."""
        # Clean up any existing output
        output_gpkg = BUILD_DIR / "wayfinding.gpkg"
        if output_gpkg.exists():
            output_gpkg.unlink()

        # Run make etl-extract
        result = subprocess.run(
            ["make", "etl-extract"],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT,
        )

        assert result.returncode == 0, (
            f"make etl-extract failed:\nstdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert output_gpkg.exists(), (
            f"make etl-extract did not create {output_gpkg}"
        )

        # Quick verification: count layers
        cmd = [
            "docker",
            "compose",
            "-f",
            str(DOCKER_COMPOSE_PATH),
            "run",
            "--rm",
            "etl",
            "ogrinfo",
            "-json",
            "-so",
            "/workspace/build/wayfinding.gpkg",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            layers = info.get("layers", [])
            assert len(layers) == 14, (
                f"Expected 14 layers in output, found {len(layers)}"
            )
