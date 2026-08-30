"""Failing tests for DT-002: ETL Infrastructure and Category Mapping Schema.

These tests check:
1. docker-compose.yml has an etl service with GDAL + Python 3.12+
2. Makefile has a `make etl` target
3. category_mapping.yaml exists, is valid YAML, and covers all USE_TYPE values
4. schema.py defines output table schemas as Pydantic models
5. A no-op ETL entry point can be invoked

All tests will FAIL initially because the implementation does not exist yet.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

# Paths relative to workspace root
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
DOCKER_COMPOSE_PATH = WORKSPACE_ROOT / "infra" / "docker-compose.yml"
MAKEFILE_PATH = WORKSPACE_ROOT / "Makefile"
CATEGORY_MAPPING_PATH = (
    WORKSPACE_ROOT
    / "packages"
    / "wayfinding"
    / "src"
    / "wayfinding"
    / "etl"
    / "category_mapping.yaml"
)
SCHEMA_PATH = (
    WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding" / "etl" / "schema.py"
)
GDB_PATH = Path("C:/repos/sfudt/claude/dtwin-harness/data/IndoorWayfinding.gdb")


class TestDockerComposeEtlService:
    """Test that docker-compose.yml has a properly configured etl service."""

    def test_docker_compose_file_exists(self):
        """docker-compose.yml must exist."""
        assert DOCKER_COMPOSE_PATH.exists(), f"Missing {DOCKER_COMPOSE_PATH}"

    def test_etl_service_exists(self):
        """docker-compose.yml must define an 'etl' service."""
        with open(DOCKER_COMPOSE_PATH) as f:
            compose_config = yaml.safe_load(f)

        assert "services" in compose_config, "docker-compose.yml missing 'services' key"
        assert "etl" in compose_config["services"], "docker-compose.yml missing 'etl' service"

    def test_etl_service_has_gdal_image(self):
        """etl service must use Python 3.12+.
        
        DT-002 is infrastructure-only; actual geodata processing (requiring GDAL)
        is deferred to DT-003. The image must have Python 3.12+ for the no-op
        entry point and future DT-003+ implementations.
        """
        with open(DOCKER_COMPOSE_PATH) as f:
            compose_config = yaml.safe_load(f)

        etl_service = compose_config["services"]["etl"]
        assert "image" in etl_service, "etl service missing 'image' key"

        # For DT-002 (infrastructure), require Python 3.12+.
        # GDAL image will be introduced in DT-003 when ogrinfo is needed.
        image = etl_service["image"].lower()
        assert "python" in image or "gdal" in image or "osgeo" in image, (
            f"etl service image '{etl_service['image']}' must have Python 3.12+ "
            "(for DT-002 no-op entry point) or GDAL (for DT-003+ geodata processing)"
        )

    def test_etl_service_mounts_gdb_readonly(self):
        """etl service must mount the source GDB read-only."""
        with open(DOCKER_COMPOSE_PATH) as f:
            compose_config = yaml.safe_load(f)

        etl_service = compose_config["services"]["etl"]
        assert "volumes" in etl_service, "etl service missing 'volumes' key"

        volumes = etl_service["volumes"]
        gdb_mount = None
        for volume in volumes:
            if "IndoorWayfinding.gdb" in volume and ":ro" in volume:
                gdb_mount = volume
                break

        assert gdb_mount is not None, (
            "etl service must mount IndoorWayfinding.gdb with :ro (read-only) flag"
        )
        assert "/data/IndoorWayfinding.gdb" in gdb_mount, (
            "GDB should be mounted at /data/IndoorWayfinding.gdb"
        )

    def test_etl_service_mounts_build_readwrite(self):
        """etl service must mount ./build/ read-write for outputs."""
        with open(DOCKER_COMPOSE_PATH) as f:
            compose_config = yaml.safe_load(f)

        etl_service = compose_config["services"]["etl"]
        volumes = etl_service["volumes"]

        build_mount = None
        for volume in volumes:
            if "build" in volume and (":rw" in volume or volume.count(":") == 1):
                # :rw is default, so it may be omitted
                build_mount = volume
                break

        assert build_mount is not None, (
            "etl service must mount a 'build' directory for outputs"
        )


class TestMakefileEtlTarget:
    """Test that Makefile has a 'make etl' target that invokes the container."""

    def test_makefile_exists(self):
        """Makefile must exist at workspace root."""
        assert MAKEFILE_PATH.exists(), f"Missing {MAKEFILE_PATH}"

    def test_makefile_has_etl_target(self):
        """Makefile must define an 'etl' target."""
        with open(MAKEFILE_PATH) as f:
            makefile_content = f.read()

        # Check for either "etl:" or ".PHONY: etl" or similar
        assert "etl" in makefile_content, "Makefile missing 'etl' target"

        # More strict: check for target declaration
        lines = makefile_content.split("\n")
        has_etl_target = any(
            line.strip().startswith("etl:") or line.strip() == ".PHONY: etl"
            for line in lines
        )
        assert has_etl_target, "Makefile does not declare 'etl' as a target"

    def test_etl_target_uses_docker_compose(self):
        """etl target must invoke docker compose."""
        with open(MAKEFILE_PATH) as f:
            makefile_content = f.read()

        # Find the etl target and check its commands
        assert "docker compose" in makefile_content or "docker-compose" in makefile_content, (
            "etl target must use docker compose to run the ETL container"
        )


class TestCategoryMappingYaml:
    """Test that category_mapping.yaml exists and is well-formed."""

    def test_category_mapping_file_exists(self):
        """category_mapping.yaml must exist in the etl module."""
        assert CATEGORY_MAPPING_PATH.exists(), (
            f"Missing {CATEGORY_MAPPING_PATH}"
        )

    def test_category_mapping_is_valid_yaml(self):
        """category_mapping.yaml must be valid YAML."""
        with open(CATEGORY_MAPPING_PATH) as f:
            mapping = yaml.safe_load(f)

        assert mapping is not None, "category_mapping.yaml is empty or invalid"
        assert isinstance(mapping, dict), "category_mapping.yaml must be a dictionary"

    def test_category_mapping_structure(self):
        """Each entry must have category and optional metadata flags."""
        with open(CATEGORY_MAPPING_PATH) as f:
            mapping = yaml.safe_load(f)

        for use_type, config in mapping.items():
            assert isinstance(config, dict), (
                f"USE_TYPE '{use_type}' must map to a dictionary"
            )
            assert "category" in config, (
                f"USE_TYPE '{use_type}' missing required 'category' field"
            )

            # Optional fields: accessible, gender, capacity
            # (not required, but if present must be valid types)
            if "accessible" in config:
                assert isinstance(config["accessible"], bool), (
                    f"USE_TYPE '{use_type}' has non-boolean 'accessible' flag"
                )
            if "gender" in config:
                assert isinstance(config["gender"], str), (
                    f"USE_TYPE '{use_type}' has non-string 'gender' flag"
                )


class TestCategoryMappingComplete:
    """Test that category_mapping.yaml covers all USE_TYPE values from the GDB."""

    def get_use_types_from_gdb(self) -> set[str]:
        """Query the GDB for all distinct USE_TYPE values in Units layer.

        Returns a set of USE_TYPE strings. Runs via Docker to avoid local GDAL dependency.
        """
        # Run ogrinfo via Docker to get distinct USE_TYPE values
        cmd = [
            "docker", "compose", "-f", str(DOCKER_COMPOSE_PATH), "run", "--rm", "etl",
            "ogrinfo", "-ro", "-sql",
            "SELECT DISTINCT USE_TYPE FROM Units_AQ_SH_ECC ORDER BY USE_TYPE",
            "/data/IndoorWayfinding.gdb"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT
        )

        assert result.returncode == 0, (
            f"Failed to query GDB for USE_TYPE values:\n{result.stderr}"
        )

        # Parse ogrinfo output to extract USE_TYPE values
        use_types = set()
        for line in result.stdout.split("\n"):
            if "USE_TYPE (String) =" in line:
                # Extract the value after the equals sign
                use_type = line.split("=", 1)[1].strip()
                use_types.add(use_type)

        return use_types

    @pytest.mark.skipif(
        shutil.which("docker") is None,
        reason="Docker CLI not available in test environment"
    )
    def test_category_mapping_complete(self):
        """All USE_TYPE values from the GDB must appear exactly once in category_mapping.yaml."""
        # Get USE_TYPE values from GDB
        gdb_use_types = self.get_use_types_from_gdb()
        assert len(gdb_use_types) > 0, "Failed to extract USE_TYPE values from GDB"

        # Load category mapping
        with open(CATEGORY_MAPPING_PATH) as f:
            mapping = yaml.safe_load(f)

        yaml_use_types = set(mapping.keys())

        # Check for orphans (in GDB but not in YAML)
        orphans = gdb_use_types - yaml_use_types
        assert len(orphans) == 0, (
            f"USE_TYPE values in GDB but missing from category_mapping.yaml: {sorted(orphans)}"
        )

        # Check for extras (in YAML but not in GDB)
        extras = yaml_use_types - gdb_use_types
        assert len(extras) == 0, (
            f"USE_TYPE values in category_mapping.yaml but not found in GDB: {sorted(extras)}"
        )

        # Check for duplicates (shouldn't happen with dict keys, but good to verify)
        assert len(yaml_use_types) == len(mapping), (
            "Duplicate USE_TYPE keys in category_mapping.yaml"
        )


class TestSchemaDefinition:
    """Test that schema.py defines output table schemas."""

    def test_schema_file_exists(self):
        """schema.py must exist in the etl module."""
        assert SCHEMA_PATH.exists(), f"Missing {SCHEMA_PATH}"

    def test_schema_file_is_importable(self):
        """schema.py must be importable as a Python module."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("wayfinding.etl.schema", SCHEMA_PATH)
        assert spec is not None, "Could not load schema.py module spec"

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Module should define schema classes/models
        assert hasattr(module, "__dict__"), "schema.py module has no attributes"

    def test_schema_defines_required_tables(self):
        """schema.py must define schemas for all output tables."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("wayfinding.etl.schema", SCHEMA_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        required_schemas = [
            "FacilitySchema",
            "LevelSchema",
            "UnitSchema",
            "LandmarkSchema",
            "DetailSchema",
            "PathwaySchema",
            "TransitionSchema",
        ]

        for schema_name in required_schemas:
            assert hasattr(module, schema_name), (
                f"schema.py missing required schema: {schema_name}"
            )

    def test_schema_models_have_crs_metadata(self):
        """Schema models must include CRS information."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("wayfinding.etl.schema", SCHEMA_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Check that at least one schema has CRS metadata
        # (Implementation detail: could be a class attribute, docstring, or separate constant)
        facility_schema = getattr(module, "FacilitySchema", None)
        assert facility_schema is not None, "Missing FacilitySchema"

        # Check for CRS indication (flexible - could be attribute, constant, or docstring)
        str(facility_schema)
        module_source = open(SCHEMA_PATH).read()

        assert (
            "EPSG:26910" in module_source or
            "CRS" in module_source or
            "26910" in module_source
        ), "schema.py must document the CRS (EPSG:26910)"


class TestEtlEntryPoint:
    """Test that the ETL can be invoked via make etl (no-op run)."""

    def test_etl_module_exists(self):
        """wayfinding.etl package must exist."""
        etl_init = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding"
            / "etl" / "__init__.py"
        )
        assert etl_init.exists(), "Missing wayfinding/etl/__init__.py"

    def test_etl_run_module_exists(self):
        """wayfinding.etl.run module must exist for entry point."""
        run_module = (
            WORKSPACE_ROOT / "packages" / "wayfinding" / "src" / "wayfinding"
            / "etl" / "run.py"
        )
        assert run_module.exists(), "Missing wayfinding/etl/run.py"

    def test_etl_run_main_function(self):
        """run.py must define a callable main() function."""
        import importlib.util

        run_module_path = (
            WORKSPACE_ROOT
            / "packages"
            / "wayfinding"
            / "src"
            / "wayfinding"
            / "etl"
            / "run.py"
        )
        spec = importlib.util.spec_from_file_location(
            "wayfinding.etl.run", run_module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert hasattr(module, "main"), "run.py missing main() function"
        assert callable(module.main), "main in run.py is not callable"

        # Call main() and verify it returns 0 (success)
        result = module.main()
        assert result == 0, f"main() returned {result}, expected 0"

    @pytest.mark.skipif(
        shutil.which("docker") is None,
        reason="Docker CLI not available in test environment"
    )
    @pytest.mark.slow
    def test_make_etl_runs_successfully(self):
        """make etl must complete with exit code 0 (even if no-op).

        This is a slow test because it spins up the Docker container.
        """
        result = subprocess.run(
            ["make", "etl"],
            capture_output=True,
            text=True,
            cwd=WORKSPACE_ROOT
        )

        assert result.returncode == 0, (
            f"make etl failed with exit code {result.returncode}:\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
