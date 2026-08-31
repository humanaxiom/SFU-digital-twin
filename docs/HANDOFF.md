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
- **DT-005 (graph node snapping and raw pathway graph)**: Complete & approved. `graph.py` with `load_level_lookup()`, `snap_nodes()`, `build_raw_graph()` functions. Outputs: `build/graph_raw.pkl` (NetworkX MultiDiGraph, 15,582 nodes, 44,826 directed pathway arcs, 12.4 MB), `build/node_map.pkl` (44,978 entries: 44,852 pathway + 126 transition endpoints, 1.5 MB), `build/graph_raw_stats.json` (metadata). Node identity per ADR-0004 uses coordinate tuples `(x, y, vertical_order)` with 1 cm EPSG:26910 grid snapping and vertical_order from `level_26910` table (never Z). All 11 levels represented. 13 self-loops removed. Pathway edges only (mode='pathway'); transition edges deferred to DT-006. Bidirectional arcs with forward key `PW_{fid}` and reverse key `PW_{fid}_R`. Edge attributes: `{length_3d, mode, level_id, feature_id, geometry}` with reverse-arc geometries coordinate-reversed. Within-level connectivity: largest component 2,957 nodes (AQ 3000), highest fragmentation 253 components (AQ 6000, pre-contraction). ADR-0004 documents MultiDiGraph rationale, node-identity semantics, node-map vs graph-membership distinction, round-half-up quantization, parallel-edge keys, and pickle serialization. 155 tests passed, 2 skipped, 90.29% coverage. Lint/type clean, data-QA PASS (17 checks), judge APPROVE. Commit: 14652a9.

## What changed most recently

- **DT-005 closed & approved:**
  - `packages/wayfinding/src/wayfinding/etl/graph.py`: Three core functions implementing graph construction per ADR-0004. `load_level_lookup()` reads `level_26910` table returning 11-entry `{level_id: vertical_order}` dict. `snap_nodes()` snaps all pathway and transition endpoints to 1 cm EPSG:26910 grid with round-half-up quantization, producing `node_map` (44,978 entries: 44,852 pathway + 126 transition) mapping `(layer_prefix, feature_id, endpoint_role)` → `(x, y, vertical_order)` coordinate tuples, plus node attributes (`level_ids`, `z_min`/`z_max`/`z_mean`). `build_raw_graph()` constructs NetworkX MultiDiGraph with 22,426 pathway features creating 44,826 bidirectional arcs (mode='pathway' only; transition edges deferred to DT-006), excluding 13 detected self-loops (logged with FIDs).
  - `build/graph_raw.pkl`: Serialized NetworkX MultiDiGraph (12.4 MB, pickle protocol 5). 15,582 nodes with coordinate-tuple IDs `(x, y, vertical_order)`. All 11 levels represented. Node attributes include x, y, vertical_order, level_ids (set), z_min, z_max, z_mean. Edge attributes: `{length_3d, mode, level_id, feature_id, geometry: LineString}` with reverse-arc geometries coordinate-reversed per ADR-0004 §7. Shapely LineString objects stored directly (not WKT/WKB) for DT-007 contraction efficiency.
  - `build/node_map.pkl`: Serialized endpoint map (1.5 MB) for DT-006 to consume; avoids re-snapping transition endpoints (ensures exact coordinate match with pathway-graph nodes).
  - `build/graph_raw_stats.json`: Metadata artifact per ADR-0004 §10. Node/edge counts, mean degree 5.75, self_loops_removed=13 with FID list, connectivity-by-level (largest component 2,957 nodes on AQ 3000; highest fragmentation 253 components on AQ 6000 pre-contraction), z_range_by_level (all Z values logged but excluded from node identity per spatial-invariants), ETL version, ISO 8601 timestamp.
  - Node identity design (ADR-0004 §2): Uses snapped coordinate tuples `(x, y, vertical_order)` as deterministic stable IDs rather than UUID or sequential int. Round-half-up quantization `floor(coord*100 + 0.5)/100` ensures platform-independent reproducibility. Z coordinate excluded from identity; vertical_order sourced exclusively from `level_26910` table (never LEVEL_NUMBER or Z, per spatial-invariants).
  - Node-map vs graph-membership distinction (ADR-0004 §3): DT-005 snaps all endpoints (pathways + transitions) into `node_map` but adds nodes to NetworkX graph only when referenced by edges. Transition endpoints present in `node_map.pkl` but not in `graph_raw.pkl` until DT-006 adds transition edges. Zero isolated nodes in DT-005 output (all 15,582 graphed nodes have degree ≥1).
  - Bidirectional edge convention (ADR-0004 §4): Forward key `PW_{fid}`, reverse key `PW_{fid}_R`. DT-006 will use `TR_{fid}` / `TR_{fid}_R` for transitions; DT-008 `UC_{fid}` / `UC_{fid}_R` for unit connectors. Reverse-edge geometry coordinates explicitly reversed to simplify DT-007 chain merging and DT-010 bearing calculations.
  - ADR-0004: Documents graph-representation choice (MultiDiGraph for parallel edges and future directed features), endpoint extraction from MultiLineString Z (first coord of first part / last coord of last part), source LENGTH_3D as authoritative edge weight (no recomputation), and pickle serialization with native Shapely objects (not node-link JSON).
  - `Makefile`: Added `etl-graph-raw` target invoking `docker compose run etl python -m wayfinding.etl.run graph-raw`.
  - `packages/wayfinding/tests/test_dt005_graph.py`: Comprehensive test suite (155 passed, 2 skipped, 90.29% coverage). Tests: snapping precision (1 cm), vertical_order lookup from `level_26910`, node-identity schema (coordinate tuples), bidirectionality (200 sampled forward/reverse pairs), edge-attribute contract, self-loop exclusion, zero isolated nodes, within-level connectivity (all 11 levels), determinism (reproducible graph structure), container-only execution, and source GDB read-only boundary.
  - All gates clean: `make test lint type` PASS. `ruff` and `pyright` zero errors. data-QA PASS with 17 validation checks (EPSG:26910 snapping, round-half-up quantization, vertical_order provenance, node-identity tuples, collision-safe node-map keys, pathway-only edges, edge schema, self-loop removal, zero isolated nodes, level-aware connectivity, read-only source, no GDB access, no unsupported accessibility claims, pickle protocol 5, stats JSON schema, Makefile target, test suite). `judge` verdict `APPROVE` with no findings. Commit: 14652a9.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps (for fresh session)

1. **Plan DT-006 (Add Transition Edges to Graph) with `planner` agent**:
   - Read [docs/plans/PHASE-1-ETL.md](plans/PHASE-1-ETL.md) DT-006 section for scope: add 63 transition features (stairs/elevators) as 126 bidirectional arcs to `graph_raw.pkl`, mark transition endpoints as protected for DT-007 contraction, validate cross-level connectivity (1 connected component over mode='pathway'|'stairs'|'elevator').
   - Create detailed plan at [docs/plans/DT-006.md](plans/DT-006.md) following established plan template (see DT-003/DT-004/DT-005 for reference).
2. **Execute DT-006 via `/tdd-feature` workflow**:
   - Invoke `test-writer` to create comprehensive test suite before implementation (RED first).
   - Invoke `implementer` to extend `packages/wayfinding/src/wayfinding/etl/graph.py` with transition-edge logic, consuming `build/node_map.pkl` from DT-005 to ensure exact coordinate match.
   - Output updated artifact `build/graph_transitions.pkl` (or overwrite `graph_raw.pkl` with combined pathway + transition graph, per planner's design).
3. **Judge review & doc-writer**:
   - Run `judge` agent against plan, DOD, and spatial-invariants (especially elevator-only accessibility rule).
   - Update CHANGELOG, HANDOFF, and advance to DT-007 (Contract Degree-2 Chains).
