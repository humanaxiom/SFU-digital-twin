# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `packages/wayfinding/src/wayfinding/etl/extract.py` with `extract_to_gpkg()` function extracting all seven AIIM layers (Facilities/Levels/Units/Pathways/Transitions/Landmarks/Details) from FileGDB to GeoPackage with dual CRS output: EPSG:26910 (native 3D, source of truth for routing) and EPSG:4326 (2D for web display) — produces exactly 14 layers, verified against authoritative feature counts (Facilities: 3, Levels: 11, Units: 1,210, Pathways: 22,426, Transitions: 63, Landmarks: 41, Details: 55,593) ([DT-003](docs/plans/DT-003.md))
- `Makefile` `etl-extract` target wrapping containerized extraction, writing `build/wayfinding.gpkg` ([DT-003](docs/plans/DT-003.md))
- Test suite `packages/wayfinding/tests/test_dt003_extract.py` with 29 tests covering extraction, CRS preservation, geometry types, determinism, and read-only boundary (51 passed, 2 skipped, 95.52% line coverage; `ruff` and `pyright` clean; data-QA PASS; judge APPROVE) ([DT-003](docs/plans/DT-003.md))
- `infra/docker-compose.yml` `etl` service updated to pinned GDAL container `ghcr.io/osgeo/gdal@sha256:3019206f...` for reproducible ETL execution ([DT-003](docs/plans/DT-003.md))
- `infra/docker-compose.yml` `etl` service configured with Python 3.12-slim, mounting source GDB read-only and `./build/` read-write ([DT-002](docs/plans/DT-002.md))
- `Makefile` `etl` target wrapping `docker compose run --rm etl` to run ETL pipeline in container ([DT-002](docs/plans/DT-002.md))
- `packages/wayfinding/src/wayfinding/etl/category_mapping.yaml` external controlled vocabulary mapping all 62 source GDB `USE_TYPE` values to normalized categories ([DT-002](docs/plans/DT-002.md))
- `packages/wayfinding/src/wayfinding/etl/schema.py` Pydantic v2 schemas for all 7 output tables (`Facility`, `Level`, `Unit`, `Landmark`, `Detail`, `Pathway`, `Transition`) with EPSG:26910 native CRS metadata ([DT-002](docs/plans/DT-002.md))
- `packages/wayfinding/src/wayfinding/etl/run.py` no-op ETL entry point callable via `python -m wayfinding.etl.run` or `make etl` ([DT-002](docs/plans/DT-002.md))
- Comprehensive test suite in `packages/wayfinding/tests/test_dt002_etl_infrastructure.py` validating all ETL infrastructure components ([DT-002](docs/plans/DT-002.md))
- `packages/wayfinding/` Python package skeleton with `pyproject.toml`, `src/wayfinding/`, and `tests/` directory structure ([DT-001](docs/plans/DT-001.md))
- `infra/docker-compose.yml` defining a containerized `test` service with GDAL support, mounting the package read-write and the source geodatabase read-only ([DT-001](docs/plans/DT-001.md))
- `Makefile` with `test`, `lint`, and `type` gates wrapping `docker compose run --rm test` commands to enforce container-only execution ([DT-001](docs/plans/DT-001.md))
- ADR-0002 documenting package layout convention, per-package coverage floors, container execution model, and the read-only mount rule for the source GDB ([DT-001](docs/plans/DT-001.md))
- Coverage floor of 85% line coverage for `packages/wayfinding` in `docs/DOD.md` ([DT-001](docs/plans/DT-001.md))
- Gate smoke tests in `tests/gate/` to verify no local Python execution and read-only GDB mount ([DT-001](docs/plans/DT-001.md))
