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
- **DT-004 (normalise tables)**: Complete & approved. `normalise.py` with 5 normalisation functions transforming raw layers into 6 tables (facility 3, level 11, unit 1017, landmark 40, detail 48728, door 6865; total 56,664 normalised records) stored as 12 dual-CRS layers in `build/wayfinding.gpkg` (26 total layers: 14 raw + 12 normalised). Includes category mapping, in-memory landmark dedupe (LMK_28 kept / LMK_41 removed), accessibility provenance (`verified_by`, `verified_date`), centroid fallback (1016 geometry_centroid + 1 envelope_center_fallback for SFU_BURNABY_QUAD_2000_2017), door separation. ADR-0003 documents dual-CRS storage & provenance model. 105 tests passed, 2 skipped, 92.74% coverage. Lint/type clean, data-QA PASS, judge APPROVE. Commits: adb9196, fbaf84b, 221373d.

## What changed most recently

- **DT-004 closed & approved:**
  - `packages/wayfinding/src/wayfinding/etl/normalise.py`: Five normalisation functions (`normalise_facilities()`, `normalise_levels()`, `normalise_units()`, `normalise_landmarks()`, `normalise_details()`) transforming 14 raw layers into 6 normalised tables with exact counts: facility 3, level 11, unit 1017 (SEARCHABLE='Y' only), landmark 40 (deduplicated from 41 source features), detail 48728, door 6865. Total 56,664 normalised records.
  - `build/wayfinding.gpkg`: Now contains 26 layers total (14 raw from DT-003 + 12 normalised dual-CRS: `facility_26910/wgs84`, `level_26910/wgs84`, `unit_26910/wgs84`, `landmark_26910/wgs84`, `detail_26910/wgs84`, `door_26910/wgs84`).
  - `packages/wayfinding/src/wayfinding/etl/schema.py`: Updated with `DoorSchema` and accessibility provenance fields (`verified_by`, `verified_date`, `centroid_method`) per ADR-0003.
  - In-memory landmark deduplication: Exactly one duplicate pair found (LMK_28/LMK_41, same-category/same-level, 0.250728 m apart). Greedy first-point-wins algorithm kept LMK_28, removed LMK_41.
   - Accessibility provenance: `verified_by="source_gdb_use_type"` and `verified_date="2026-08-29"` populated for all 103 units where `accessible` is non-null (all false in the current data); the other 914 units retain null accessibility and provenance. Both true and false values require provenance because they drive routing decisions, per ADR-0003 elevator-only honesty rule.
  - Centroid method: 1016 units used `geometry_centroid` (ST_Centroid succeeded), 1 unit (SFU_BURNABY_QUAD_2000_2017) used `envelope_center_fallback` (ST_Centroid returned NULL due to toxic geometry; raw audit geom preserved in `Units_26910` layer).
  - Door separation: 6865 ADO (door) features split from `Details_26910` layer into dedicated `door` table for instruction-hint generation (DT-010+).
  - ADR-0003: Documents dual-CRS storage model, accessibility provenance requirements, PK derivation rules, landmark deduplication algorithm, centroid fallback for toxic geometries, and prohibition of temp metadata tables.
  - `Makefile`: Added `etl-normalise` target.
  - `packages/wayfinding/tests/test_dt004_normalise.py`: Comprehensive test suite (105 passed, 2 skipped, 92.74% coverage).
  - All gates clean (`make test lint type`), data-QA PASS, CHANGELOG updated, `judge` verdict `APPROVE` with no findings. Commits: adb9196, fbaf84b, 221373d.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps (for fresh session)

1. **Plan DT-005 (Graph Node Snapping and Raw Graph Construction) with `planner` agent**:
   - Read [docs/plans/PHASE-1-ETL.md](plans/PHASE-1-ETL.md) DT-005 section for scope: snap pathway/transition endpoints to 1 cm grid in (x, y, vertical_order), build raw undirected NetworkX graph with ~22.5k edges.
   - Create detailed plan at [docs/plans/DT-005.md](plans/DT-005.md) following established plan template.
2. **Execute DT-005 via `/tdd-feature` workflow**:
   - Invoke `test-writer` to create comprehensive test suite before implementation.
   - Invoke `implementer` to create `packages/wayfinding/src/wayfinding/etl/graph.py` with `snap_nodes()` and `build_raw_graph()` functions.
   - Output intermediate artifact `build/graph_raw.pkl` (NetworkX DiGraph).
3. **Judge review & doc-writer**:
   - Run `judge` agent against plan and DOD.
   - Update CHANGELOG, HANDOFF, and advance to DT-006 (Add Transition Edges to Graph).
