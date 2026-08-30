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
- **DT-003 (extract layers to GeoPackage)**: In progress (TDD RED). Detailed plan at [docs/plans/DT-003.md](plans/DT-003.md); test suite written and committed at [packages/wayfinding/tests/test_dt003_extract.py](../packages/wayfinding/tests/test_dt003_extract.py) (29 tests across 7 test classes, commit `6259836`).

## What changed most recently

- **DT-002 closed & approved:**
  - `infra/docker-compose.yml`: Added `etl` service.
  - `Makefile`: Added `etl` target.
  - `packages/wayfinding/src/wayfinding/etl/category_mapping.yaml`: 62 `USE_TYPE` mappings to controlled categories.
  - `packages/wayfinding/src/wayfinding/etl/schema.py`: 7 Pydantic v2 schemas (`FacilitySchema`, `LevelSchema`, `UnitSchema`, `LandmarkSchema`, `DetailSchema`, `PathwaySchema`, `TransitionSchema`) with CRS constants.
  - `packages/wayfinding/src/wayfinding/etl/run.py`: Initial ETL entry point returning 0.
  - `packages/wayfinding/tests/test_dt002_etl_infrastructure.py`: Comprehensive test suite (19 passed, 2 skipped, 96.67% coverage).
  - All gates clean (`make test lint type`), CHANGELOG updated, `judge` verdict `APPROVE`.
- **DT-003 initiated:**
  - Plan written: [docs/plans/DT-003.md](plans/DT-003.md).
  - Test suite written & committed: [packages/wayfinding/tests/test_dt003_extract.py](../packages/wayfinding/tests/test_dt003_extract.py) (commit `6259836`).

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps (for fresh session)

1. **Implement DT-003 (`implementer` agent)**:
   - Create `packages/wayfinding/src/wayfinding/etl/extract.py` implementing `extract_to_gpkg(gdb_path, gpkg_path, layers, overwrite)`.
   - Extract 7 AIIM layers from `/data/IndoorWayfinding.gdb` to `build/wayfinding.gpkg` with dual CRS: native EPSG:26910 (3D) and EPSG:4326 (`_wgs84` suffix, 2D) = 14 layers total.
   - Note container execution: ensure GDAL/`ogr2ogr` or `osgeo.gdal`/`fiona` is properly invoked within container context.
2. **Run gates & verify GREEN**:
   - Run `make test lint type` to confirm all DT-003 tests pass.
3. **Judge review**:
   - Run `judge` agent to review DT-003 against [docs/plans/DT-003.md](plans/DT-003.md) and [docs/DOD.md](DOD.md).
4. **Doc-writer & next ticket**:
   - Update CHANGELOG.md, commit, and advance to DT-004 (Normalise Tables).
