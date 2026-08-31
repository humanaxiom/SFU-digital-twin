# Handoff — Living Project State

Read this first every session. Update it when the user asks, and whenever a ticket closes or a
decision is made that would leave this file materially stale — it should stay current enough that a
fresh session can resume cold from it alone.

## Current phase

**Phase 0 — complete.** Data profiled and documented
([docs/01-data-findings.md](01-data-findings.md)), system designed
([docs/02-system-design.md](02-system-design.md)), and the delivery harness scaffolded
([docs/03-harness-design.md](03-harness-design.md)): `.github/agents/`, `.github/prompts/`,
`.github/instructions/`, `.github/copilot-instructions.md`, `docs/DOD.md`, this file.

**Phase 1 ETL — in progress.**
- **DT-001 (harness bootstrap)**: Complete & approved. Skeleton `packages/wayfinding/`, `infra/docker-compose.yml` test service, `Makefile` gates (`test`/`lint`/`type`), ADR-0002.
- **DT-002 (ETL infrastructure & schema)**: Complete & approved. `etl` service in `infra/docker-compose.yml`, `make etl` target, `category_mapping.yaml` (all 62 `USE_TYPE` values), `schema.py` (7 Pydantic schemas with EPSG:26910 native CRS metadata), `run.py` (entry point). 19 passed, 2 skipped, 96.67% coverage.
- **DT-003 (extract layers to GeoPackage)**: Complete & approved. `extract.py::extract_to_gpkg()` function, `make etl-extract` target, `build/wayfinding.gpkg` with 14 layers (7 EPSG:26910 native 3D, 7 EPSG:4326 web 2D), 158,694 records (79,347 features × 2 CRS). 51 tests passed, 2 skipped, 95.52% coverage. Lint/type clean, data-QA PASS, judge APPROVE.

## What changed most recently

- **DT-003 closed & approved:**
  - `packages/wayfinding/src/wayfinding/etl/extract.py`: `extract_to_gpkg()` function extracting all 7 AIIM layers from FileGDB to GeoPackage with dual CRS (EPSG:26910 native 3D + EPSG:4326 web 2D) via containerised `ogr2ogr`.
  - `build/wayfinding.gpkg`: 14 layers, 158,694 records (Facilities: 3, Levels: 11, Units: 1,210, Pathways: 22,426, Transitions: 63, Landmarks: 41, Details: 55,593 × 2 CRS copies).
  - `Makefile`: Added `etl-extract` target.
  - `infra/docker-compose.yml`: Updated `etl` service to pinned GDAL container (`ghcr.io/osgeo/gdal@sha256:3019206f...`).
  - `packages/wayfinding/tests/test_dt003_extract.py`: Comprehensive test suite (29 tests across 7 test classes, 51 passed, 2 skipped, 95.52% coverage).
  - All gates clean (`make test lint type`), data-QA PASS, CHANGELOG updated, `judge` verdict `APPROVE`.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps (for fresh session)

1. **Plan DT-004 (Normalise Tables) with `planner` agent**:
   - Read [docs/plans/PHASE-1-ETL.md](plans/PHASE-1-ETL.md) DT-004 section for scope: transform extracted layers into target schema, apply category mapping, deduplicate landmarks, derive `vertical_order` mappings.
   - Create detailed plan at [docs/plans/DT-004.md](plans/DT-004.md) following established plan template.
2. **Execute DT-004 via `/tdd-feature` workflow**:
   - Invoke `test-writer` to create comprehensive test suite before implementation.
   - Invoke `implementer` to create `packages/wayfinding/src/wayfinding/etl/normalise.py` with functions `normalise_facilities()`, `normalise_levels()`, `normalise_units()`, `normalise_landmarks()`, `normalise_details()`.
   - Write 5 normalised tables to `build/wayfinding.gpkg`: `facility`, `level`, `unit`, `landmark`, `detail`.
3. **Judge review & doc-writer**:
   - Run `judge` agent against plan and DOD.
   - Update CHANGELOG, HANDOFF, and advance to DT-005 (Graph Node Snapping).
