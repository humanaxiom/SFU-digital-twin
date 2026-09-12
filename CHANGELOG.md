# Changelog

## Unreleased — DT-022 exact source-vertex topology

- Added an opt-in topology mode that joins exact same-level source vertices while
  preserving source slices, authoritative lengths and the legacy default behavior.
- Built and audited isolated same-source baseline/candidate artifacts. The candidate
  gains 257,108 default and 230,356 elevator-only reachable room pairs with zero losses;
  AQ6071 reaches 696 destinations, 695 more than the baseline.
- Clear stale route failures when choosing a new origin and offer explicit named
  destination actions for small reachable sets.
- Passed candidate and accepted-artifact browser/API E2E; no accepted artifact was promoted.

## Unreleased — DT-021 route framing and map zoom

- Frame a newly opened route in useful current-floor context, including point-only departure,
  arrival and transition steps.
- Add accessible zoom, route-fit and whole-floor reset controls while preserving exact selected-step
  highlighting, floor changes and mobile layout behavior.
- Keep camera behavior client-only: route geometry, backend algorithms, source data and accepted
  artifacts are unchanged.

## Unreleased — DT-020 route availability choices

- Added origin/profile-specific connected-destination choices while preserving the full room catalog
  and explicit unsupported-route failures.
- Distinguish directed graph availability from route quality: `same_anchor` rooms have no positive
  walking segment, and connected availability does not certify guidance geometry, doors, or physical
  accessibility.
- Preserve the selected profile, deterministic counts, provenance and warnings; source data and
  routing edges are unchanged.
- Keep routing failures beside the map, identify outdated server responses, and preserve native
  destination selections when swapping rooms or applying assistant results.

## Unreleased — DT-019 rebuild launcher support

- Explain missing/invalid image inspection failures and explicit local-image use,
  preserving Docker diagnostics and the published-image default.
- Document the correct PowerShell rebuild command and its legacy-source scope.
- Docker launcher checks and 3 infrastructure tests passed; a fresh complete
  PowerShell-to-Docker source/candidate rebuild passed with accepted artifacts unchanged.

## Unreleased — DT-018 route UI

- Wrote a short GIS data request with keyed corrections and connection/verification needs.
- Added an ordered floor journey, explicit departure/arrival controls, readable
  directions, and exact blue selected spans with arrows, numbers and keyboard controls.
- Added deterministic geometry spans and distance reconciliation without changing
  canonical routing or accepted artifacts. Ambiguous/misaligned geometry refuses
  guidance; distance disagreement shows a conservative preview with a review notice.
- Fixed stale selection, loading state and floor controls during rapid navigation
  and Clear. Added synthetic regressions and expanded real browser/API checks.
- Fixed fragmented map strokes using a shared local display origin while preserving
  exact native coordinates; paint all selection halos before the blue segments.
- Final gate evidence and remaining limitations are recorded in the DT-018 report.
- Final Docker suite: 572 passed, 16 skipped, 86.88% coverage; post-render client
  checks: 27 passed. Fresh browser/API E2E and desktop/mobile/320px visual review passed.
  Refreshed the user's local demo at port 18087; accepted artifacts remain unchanged.

## Unreleased — DT-016 isolated builds

- Require fresh Docker end-to-end evidence before every green judgment, including
  small and docs-only deliveries. Updated shared instructions, DOD, judge and plans.
- Reran the full source-to-candidate pipeline and semantic comparison successfully;
  separately reran the accepted-artifact browser/API gate with all four canonical
  routes passing at desktop/mobile sizes. Existing delivery blockers remain open.

- Added deterministic seven-layer source comparison, immutable directory identities,
  explicit per-feature diagnostics and supplemental metadata inventory.
- Replaced the `make etl` no-op with a full isolated legacy rebuild. Separate Docker
  capabilities preserve raw extraction, enforce stage/hash/code/image checks and
  write only new experiment outputs. Added PowerShell/POSIX launchers and fast checks.
- Added canonical graph, unit, anchor and profile room-pair comparison. Two final
  independent candidates match semantically; their artifact bytes differ.
- Exposed eleven inherited multipart storage-order defects, including four accepted
  chains with non-source joins and cost/geometry disagreement. DT-017 prioritizes
  their correction before the 141 unassigned revised pathways are integrated.
- Accepted artifacts, source files and running demo stacks remain unchanged.
- Final Docker suite: 535 passed, 16 skipped, 86.01% coverage; lint, type, artifact-QA
  and launcher gates pass. Published-image execution remains unverified.

## Unreleased — Codex takeover

- Verified all three local geodatabases for ECC/AQ/Strand in Docker. The local
  legacy copy matches the sibling snapshot byte-for-byte. Source-etl and the legacy
  profiling launcher now default to local `data/`; Compose masks `/workspace/data`
  to prevent the repository bind exposing raw inputs. Fresh runtime boundary checks
  and local source QA pass; focused gates pass 90 tests with 2 skips, plus Ruff and
  launcher/no-host-Python checks. Existing containers require recreation to acquire new mounts.
- Recorded 141 revised-only pathways with missing facility/level identities;
  revised rebuild and supplemental entrance/door/ramp ingestion remain separate work.

- Earlier clean local-image suite (before the source-mount repair): 468 passed,
  16 skipped, 87.50% coverage; lint, types,
  artifact QA and launcher checks pass. Docker-only Chromium checks pass all four
  fixtures at desktop/mobile widths. Published-image access, CI activation and
  physical second-device LAN acceptance remain open.

- Fixed out-of-order floor rendering, manual incomplete-pair correction and stale
  chat route state. All route entry paths now clear old geometry and synchronize
  pending/invalid selection state; rejected mobility requests retain the disclosure.
- Sanitized unmatched access-log paths and unknown methods; rate-denial responses
  now retain shared security headers and sanitized access logging. Unexpected handler
  failures emit a generic diagnostic instead of exception values or filesystem traces.
- Restored DT-015's missing Strand corridor fixture (`SH1001C` → `SH1003`, 21.8 m,
  12 measured pathway edges) alongside the three AQ fixtures. Added a repeatable
  Docker-only Chromium gate with isolated networking and screenshot evidence.

- Added shared AGENTS.md, a thin Copilot adapter, reconciled spatial instructions,
  aggregate/fast container gates and a source-independent PR validation workflow.
- Recorded the image digest from successful publication run 34501691967; local
  registry access still returns 403, so local-image validation is explicitly separate.
- Fixed malformed route profiles, pre-thread HTTP admission, idle socket deadlines,
  stale profile routes and clear-during-inspection request races with behavioral regressions.
- Recorded the current model-routing preference: large models for planning, orchestration,
  architecture and final judging; smaller models for bounded mechanical edits, routine
  documentation and gate execution; ambiguous, security-sensitive or GIS-logic work escalates
  to a large model.
- Recorded the persistent coordination preference for the lead to delegate independent bounded
  tasks to multiple concurrent agents with clear file ownership; all project execution remains
  Docker-only for every agent tier.
- Reconciled obsolete infrastructure tests and source-independent extraction error tests.
- Added synthetic GDAL round-trip and evidence-regeneration tests; combined full and
  supplemental coverage reaches 85.38% without lowering the 85% floor.
- Preserved inherited DT-015 changes. Full DOD and browser/LAN acceptance are tracked
  in docs/HANDOFF.md and docs/reports/CODEX-TAKEOVER.md; no new approval is implied.
- Strengthened the repository execution policy: all project code, scripts, tests, builds,
  data processing, and evidence/hash generation run in Docker for every agent tier. Host
  activity is limited to repository inspection/editing, Git and Docker CLI operations,
  and thin Docker launcher glue; Docker unavailability now stops execution rather than
  permitting a host-runtime fallback. Removed the direct-file PowerShell parser exception.

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- DT-014 bounded indoor routing proof of concept over the hash-verified legacy GeoPackage and contracted graph artifacts. It uses immutable same-level approximate room anchors bounded to 10 m, deterministic graph-only shortest paths and geometry-derived steps, explicit fail-closed envelopes, elevator-only stairs exclusion and unverified-property disclosures, a route-enabled deterministic assistant/UI, and canonical RFC 8785 evidence with full artifact, edge, component, and reachability provenance. ADR-0009 preserves the measured 816/840 edge-induced component baseline while giving profile-isolated nodes deterministic query-time identities. Routing/GIS integrity and focused gates pass; repository-wide DOD remains blocked by the pre-existing unpublished ADR-0006 image digest ([DT-014](docs/plans/DT-014.md), [ADR-0008](docs/adr/0008-bounded-indoor-routing-poc.md), [ADR-0009](docs/adr/0009-edge-induced-profile-components-and-endpoint-reachability.md))
- DT-013 artifact-backed browser demo with real normalized floor, room, detail, and landmark geometry; global `vertical_order` floor controls; pointer/keyboard record selection; exact artifact provenance; and a disclosed deterministic assistant. The loopback-only service explicitly refuses routing, nearest-place, distance, travel-time, live-status, LLM, and path-accessibility capabilities. Focused tests, lint, type, launcher, and desktop/mobile browser checks pass; repository data-QA remains blocked by the pre-existing unpublished ADR-0006 image digest ([DT-013](docs/plans/DT-013.md))
- Matched `tools/teardown-stack.ps1` and `tools/teardown-stack.sh` commands require the exact Compose project name printed at startup and destroy only that selected project. Volumes are preserved by default and removed only with explicit `-Volumes` / `--volumes`; the README now documents the paired start and destroy workflows. Contract and dry-run verification passed, but no real teardown was executed ([DT-012](docs/plans/DT-012.md))
- Phase 1 developer launchers for PowerShell and POSIX shells now build and start persistent, healthy `artifact` and `source-etl` capability containers; `-Test` / `--test` optionally runs the containerized `test`, `lint`, `type`, and `dataqa` gates. Launcher-focused gates and Compose configuration pass, and an actual PowerShell standup reached healthy; full-suite verification remains blocked by the pre-existing ADR-0006 `PUBLISHED_DIGEST_REQUIRED` image placeholder ([DT-012](docs/plans/DT-012.md))
- `packages/wayfinding/src/wayfinding/etl/graph.py` updated with `add_transitions()` function adding 63 transition features (42 stairs, 21 elevators) as 126 bidirectional directed edges to the pathway graph from DT-005, creating `build/graph_with_transitions.pkl` — 15,587 nodes (15,582 from pathways + 5 transition-only), 44,952 directed arcs (44,826 pathway + 84 stairs + 42 elevator), 85 transition endpoints protected from contraction with `is_transition_endpoint=True` node attribute; default routing profile (pathways + stairs + elevators) yields 816 connected components (largest 7,436 nodes, 39 components bridged by transitions from 855-component pathway baseline), elevator-only accessible profile yields 840 components (largest 7,060 nodes, 15 components bridged by elevators); 2 express elevators span vertical_order 0→2 as single edges; fragmentation documented per ADR-0005 with routing limited to within-component origin/destination pairs; accessible routing explicitly stated as elevator-only with no wheelchair certification and referencing unverified attributes (door_width, path_width, slope, powered_doors, surface) pending facilities survey ([DT-006](docs/plans/DT-006.md))
- `build/graph_with_transitions.pkl` serialized NetworkX MultiDiGraph (12.6 MB, pickle protocol 5) with Shapely LineString geometries, all transition edges keyed `TR_{fid}` / `TR_{fid}_R` per ADR-0004 convention, transition-only nodes added with complete node-attribute contract (x, y, vertical_order, level_ids, z_min, z_max, z_mean) derived from transition source rows ([DT-006](docs/plans/DT-006.md))
- `build/graph_with_transitions_stats.json` artifact metadata including transition counts by type (84 stairs arcs, 42 elevator arcs), cross-level connectivity analysis per routing profile (default 816 components down from 855, elevator-only 840 components), 85 protected transition endpoints, 5 transition-only nodes, 2 express elevators, 39 default-profile bridged components (24 stairs-only contributions), 15 elevator-profile bridged components, per ADR-0005 measured baseline ([DT-006](docs/plans/DT-006.md))
- ADR-0005 documenting measured connectivity baseline superseding ADR-0004 §12 global-connectivity assumption: pathway-only graph from DT-005 has 855 components (severe fragmentation from data-collection gaps or topology errors, not 1 expected component), transitions reduce to 816 (default) / 840 (elevator-only), non-regression validation enforced (component count must not increase, each transition mode must bridge ≥1 component), global connectivity deferred to DT-009 topology-repair disposition, routing explicitly limited to within-component reachability ([DT-006](docs/plans/DT-006.md))
- `Makefile` `etl-graph-transitions` target wrapping containerised transition-graph construction, writing `build/graph_with_transitions.pkl` and `build/graph_with_transitions_stats.json` ([DT-006](docs/plans/DT-006.md))
- Test suite `packages/wayfinding/tests/test_dt006_transitions.py` with comprehensive coverage of transition edge addition, bidirectionality, mode mapping (TRANSITION_TYPE 2→stairs, 4→elevator), edge-attribute schema, endpoint protection, transition-only node addition, express elevator handling, cross-level connectivity validation per ADR-0005 (212 passed, 2 skipped, 88.19% line coverage; `ruff` and `pyright` clean; data-QA PASS with 30 validation checks; judge APPROVE) ([DT-006](docs/plans/DT-006.md))
- `packages/wayfinding/src/wayfinding/etl/graph.py` with functions `load_level_lookup()`, `snap_nodes()`, `build_raw_graph()` constructing a NetworkX MultiDiGraph from the 22,426 pathway features in `build/wayfinding.gpkg` — 15,582 nodes snapped to 1 cm EPSG:26910 grid with vertical_order from `level_26910` table, 44,826 bidirectional pathway arcs (mode='pathway' only; transition edges deferred to DT-006), 13 self-loops detected and removed, all 11 levels represented with within-level connectivity metrics (largest component 2,957 nodes on AQ 3000; highest fragmentation 253 components on AQ 6000 pre-contraction); node identity per ADR-0004 §2 uses coordinate tuples `(x, y, vertical_order)` as deterministic stable IDs; edge attributes `{length_3d, mode, level_id, feature_id, geometry: LineString}` with reverse-arc geometries coordinate-reversed; Z coordinates logged (z_min/z_max/z_mean per node) but excluded from node identity per spatial-invariants instructions ([DT-005](docs/plans/DT-005.md))
- `build/graph_raw.pkl` serialized NetworkX MultiDiGraph (12.4 MB, pickle protocol 5) with Shapely LineString geometries preserved in-memory, deterministic output across runs ([DT-005](docs/plans/DT-005.md))
- `build/node_map.pkl` serialized node-map (1.5 MB) with 44,978 entries (44,852 pathway + 126 transition endpoints) mapping `(layer_prefix, feature_id, endpoint_role)` → `(x, y, vertical_order)` for DT-006 transition-edge construction without re-snapping ([DT-005](docs/plans/DT-005.md))
- `build/graph_raw_stats.json` artifact metadata including node/edge counts, self-loops removed (with FID list), connectivity-by-level stats, z_range_by_level, ETL version, and timestamp per ADR-0004 §10 ([DT-005](docs/plans/DT-005.md))
- ADR-0004 documenting graph construction decisions: MultiDiGraph vs undirected rationale, node identity as coordinate tuples, round-half-up quantization, node-map vs graph-membership distinction (transition endpoints snapped but not graphed until DT-006), parallel-edge keys, endpoint extraction from MultiLineString Z, source LENGTH_3D as authoritative edge weight, reverse-edge geometry representation, pickle serialization with Shapely objects ([DT-005](docs/plans/DT-005.md))
- `Makefile` `etl-graph-raw` target wrapping containerised graph construction, writing `build/graph_raw.pkl`, `build/node_map.pkl`, `build/graph_raw_stats.json` ([DT-005](docs/plans/DT-005.md))
- Test suite `packages/wayfinding/tests/test_dt005_graph.py` with comprehensive coverage of snapping precision, vertical_order lookup, node identity, bidirectionality, edge attributes, self-loop exclusion, isolated-node prohibition, within-level connectivity, determinism, and container-only execution (155 passed, 2 skipped, 90.29% line coverage; `ruff` and `pyright` clean; data-QA PASS with 17 validation checks; judge APPROVE) ([DT-005](docs/plans/DT-005.md))
- `packages/wayfinding/src/wayfinding/etl/normalise.py` with functions `normalise_facilities()`, `normalise_levels()`, `normalise_units()`, `normalise_landmarks()`, `normalise_details()` transforming raw extracted layers into 6 normalised tables (facility: 3, level: 11, unit: 1017, landmark: 40, detail: 48728, door: 6865; total 56,664 records) with dual-CRS storage as 12 GeoPackage layers alongside 14 raw layers from DT-003 (26 total layers) — includes category mapping via `category_mapping.yaml`, in-memory landmark deduplication (LMK_28 kept / LMK_41 removed at 0.250728 m), accessibility provenance fields (`verified_by`, `verified_date`), centroid fallback for toxic geometries (1016 geometry_centroid + 1 envelope_center_fallback for unit SFU_BURNABY_QUAD_2000_2017 with NULL normalised geom and retained raw audit geometry), and door separation for instruction hints ([DT-004](docs/plans/DT-004.md))
- `packages/wayfinding/src/wayfinding/etl/schema.py` updated with `DoorSchema` and accessibility provenance fields (`verified_by`, `verified_date`, `centroid_method`) per ADR-0003 ([DT-004](docs/plans/DT-004.md))
- ADR-0003 documenting normalised ETL schema design, dual-CRS storage model (paired `_26910` and `_wgs84` layers), accessibility provenance requirements, centroid fallback for toxic geometries, landmark deduplication algorithm (greedy first-point-wins), and temp-table prohibition ([DT-004](docs/plans/DT-004.md))
- `Makefile` `etl-normalise` target wrapping containerised normalisation, updating `build/wayfinding.gpkg` with normalised tables ([DT-004](docs/plans/DT-004.md))
- Test suite `packages/wayfinding/tests/test_dt004_normalise.py` with comprehensive coverage of all 6 normalised tables, category mapping, deduplication, vertical_order invariants, accessibility provenance, and centroid fallback (105 passed, 2 skipped, 92.74% line coverage; `ruff` and `pyright` clean; data-QA PASS; judge APPROVE) ([DT-004](docs/plans/DT-004.md))
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
