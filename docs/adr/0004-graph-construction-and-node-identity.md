# 4. Graph construction and node identity

Status: Accepted  
Date: 2026-08-31

## Context

DT-005 (Graph Node Snapping and Raw Graph Construction) transforms the over-noded pathway geometry
(22,426 segments, mean length 0.94 m) into a routable graph by snapping all endpoints to a 1 cm
grid and building a NetworkX graph with bidirectional edges. The plan
([docs/plans/DT-005.md](../plans/DT-005.md)) surfaces fourteen unresolved architectural decisions
that cross component boundaries and affect downstream tickets (DT-006 through DT-010):

### 1. Graph representation: MultiDiGraph vs undirected or simple directed graph

The plan proposes `NetworkX MultiDiGraph` with bidirectional edges (every pathway creates two
directed arcs, u→v and v→u). The alternative is an undirected `MultiGraph`, which would be simpler
for the all-bidirectional pathway network (100% of features have `TRAVEL_DIRECTION=1` per
[docs/01-data-findings.md §5](../01-data-findings.md#5-routing-network)).

However, DT-006 will add transition edges (stairs, elevators), which are also bidirectional but
semantically directed: `vertical_order_from → vertical_order_to`. Using `MultiDiGraph` uniformly
allows future one-way features (e.g., escalators, one-way doors, emergency exits) without
graph-model migration. The memory cost is acceptable: 45k directed arcs vs 22.5k undirected edges
is a 2× increase, but the full graph with geometries is estimated at <1 GB.

**Multi** (vs simple DiGraph) is required because grid snapping will produce parallel edges: two
distinct pathway features that share snapped start and end nodes are both valid until contraction
(DT-007). A simple DiGraph would silently overwrite one edge with the other.

### 2. Node identity and coordinate snapping precision

The plan specifies node identity as `(round(x, 2), round(y, 2), vertical_order)`, where x and y are
EPSG:26910 metres rounded to 2 decimal places (1 cm precision). Two ambiguities exist:

**2a. Rounding semantics.** Python's built-in `round(x, 2)` uses **banker's rounding** (round half
to even): 0.125 rounds to 0.12, 0.135 rounds to 0.14. For spatial grid quantization, round-half-up
is more intuitive and aligns with cartographic conventions. The difference is negligible at 1 cm
precision (affects only coordinates with exactly 0.5 cm fractional parts), but explicit
quantization is clearer:

```python
def snap_to_cm(coord: float) -> float:
    """Round coordinate to nearest centimetre (round half up)."""
    return floor(coord * 100 + 0.5) / 100
```

**2b. Node ID representation.** The plan mentions "UUID or sequential int" as node IDs, mapping
from snapped coordinates. Both are problematic:

- **UUID**: Non-deterministic (violates AC6 reproducibility), meaningless (can't infer location
  from ID), and wastes 16 bytes per node (~240 KB overhead for 15k nodes).
- **Sequential int**: Deterministic only if feature iteration order is deterministic, which requires
  explicit FID-sorting (already planned) — but the mapping is opaque and complicates debugging
  ("node 7243" conveys no spatial information).

**Proposal:** Use the snapped coordinate tuple itself as the node ID: `(x_snapped, y_snapped,
vertical_order)`. This is:
- **Deterministic**: same coordinates always produce same ID.
- **Stable**: IDs don't change between runs (no iteration-order dependency).
- **Meaningful**: you can see where the node is from its ID (critical for data-QA and debugging).
- **Space-efficient**: a 3-tuple of `(float, float, int)` is 24 bytes vs 16 for UUID, but eliminates
  the separate `node_map` dictionary (saves ~15k × 24 bytes = 360 KB).

NetworkX accepts any hashable object as a node ID; tuples are hashable. The graph serialization
(pickle) preserves tuples natively.

### 3. Isolated nodes and the node-map vs graph-membership distinction

DT-005 AC5 mandates **zero isolated nodes** (degree 0). However, §2.3 of the plan resolves that
DT-005 snaps **all** endpoints (pathways + transitions) but adds **only pathway edges**. This
creates a contradiction: transition endpoints will have no edges in the DT-005 output, making them
isolated nodes.

**Root cause:** Conflating the *node-space definition* (the universe of all possible nodes) with
*graph membership* (which nodes actually appear in the NetworkX graph). DT-005's responsibility is
to establish the **unified node space** so DT-006 doesn't re-snap transition endpoints
(re-snapping could produce different coordinates due to floating-point variance, breaking edge
connectivity). But not all snapped nodes need to be added to the graph.

**Resolution:**
1. `snap_nodes()` returns a `node_map: dict[tuple[str, str], tuple[float, float, int]]` mapping
   `(feature_id, endpoint_role)` → snapped coordinate tuple. This map contains **all** snapped
   endpoints (pathways + transitions) — roughly 45k pathway endpoints + 126 transition endpoints.
2. `build_raw_graph()` adds a node to the NetworkX graph **only when adding an edge that references
   it**. Nodes are created on-demand by `G.add_edge(u, v, ...)` — NetworkX automatically adds `u`
   and `v` if they don't exist.
3. `node_map` is serialized alongside `graph_raw.pkl` as `node_map.pkl` for DT-006 to consume
   without re-snapping.

This way:
- The node space is unified and complete in DT-005 (AC1 satisfied: "every pathway and transition
  endpoint maps to exactly one snapped node").
- No isolated nodes in the graph output (AC5 satisfied: only pathway endpoints have edges in
  DT-005, so only those nodes are added).
- DT-006 adds transition edges by looking up their endpoints in `node_map.pkl`, ensuring exact
  coordinate match with the already-graphed pathway nodes.

### 4. Parallel-edge keys and reverse-edge pairing

The plan specifies edge keys `f"PW_{feature_id}"` for forward arcs and `f"PW_{feature_id}_R"` for
reverse arcs. Two issues:

**4a. Key uniqueness.** If a pathway feature has identical start and end after snapping (a
self-loop, detected and excluded by AC4), the key is still unique because the edge is never added.
If two distinct pathway features happen to share the same FID (impossible — FIDs are unique within
a layer), the second would overwrite the first. But GeoPackage FIDs are guaranteed unique by OGR,
so this is not a concern.

**4b. Reverse-edge detection.** Given an edge with key `k`, how does code (especially in DT-007
contraction) determine if another edge is its reverse pair? The `_R` suffix works, but is fragile:
if DT-006 adds transition edges with keys `f"TR_{feature_id}"` and `f"TR_{feature_id}_R"`, then
generic graph code can identify reverse pairs by suffix alone. Formalise this:

- **Forward edge key**: `<prefix>_{feature_id}` where prefix is `PW` (pathway), `TR` (transition),
  `UC` (unit connector, DT-008).
- **Reverse edge key**: `<prefix>_{feature_id}_R`.
- **Reverse pair test**: `key_reverse = key + "_R" if not key.endswith("_R") else key[:-2]`.

This convention must be documented in `graph.py` and enforced by test
`test_raw_graph_bidirectional`.

### 5. Endpoint extraction from MultiLineString Z with multipart handling

All pathway and transition geometries are `MultiLineString Z`. Most are single-part (one
LineString), but the AIIM spec allows multipart. The plan does not specify how to extract endpoints
from multipart geometries.

**Proposal:** For a `MultiLineString` with N parts:
- **Start endpoint**: first coordinate of the first part.
- **End endpoint**: last coordinate of the last part.

If the parts are disjoint (not end-to-end connected), this may create incorrect edges. However,
data findings §5 report no evidence of disjoint multipart pathways; all features appear to be
simple single-part LineStrings topologically (the Multi prefix is a schema artifact). If multipart
features exist, they will be flagged by DT-009 validation (connectivity check will fail if a
feature's parts are disjoint but its snapped edge implies continuity).

Shapely API: `geom.geoms[0].coords[0]` (start of first part), `geom.geoms[-1].coords[-1]` (end of
last part).

### 6. Source LENGTH_3D vs computed 3D length validation

The plan specifies using the source `LENGTH_3D` field directly as edge weight, noting it is 100%
populated ([docs/01-data-findings.md §5](../01-data-findings.md#5-routing-network)). An alternative
is to compute 3D length from the geometry and validate against `LENGTH_3D`, flagging discrepancies
>1%.

**Decision:** Use `LENGTH_3D` directly, no validation. Rationale:
- `LENGTH_3D` is the authoritative value used by the data publisher; recomputing it implies we
  trust our calculation more than theirs.
- 3D length depends on the Z interpolation model (linear between vertices vs draped on a surface);
  the source system's calculation is unknowable, so any discrepancy is not necessarily an error.
- If geometries are corrupted (e.g., a pathway with a 50 m `LENGTH_3D` but a 0.5 m 2D length), the
  DT-009 connectivity validation will fail when routes compute nonsensical costs — this is a better
  detection point than a per-feature validation in DT-005.

If future data-QA requires a `LENGTH_3D` audit, add it as a separate non-blocking check in DT-009.

### 7. Reverse-edge geometry representation

The plan specifies reverse-arc geometry as `LineString(reversed(forward_geom.coords))` — i.e.,
coordinates in reverse order to match arc direction. Two alternatives:

1. **Store the same geometry object on both arcs** (u→v and v→u both carry the u→v geometry), and
   let routing code reverse it when generating instructions.
2. **Store None and derive geometry on-demand** from the forward arc when needed.

**Decision:** Reverse the coordinates as specified. Rationale:
- DT-007 contraction merges geometries from multi-edge chains; having pre-reversed geometries
  simplifies the merge logic (always concat coordinates in traversal order).
- Turn-by-turn instruction generation (DT-010) computes bearings along the route geometry; reversing
  at query time adds runtime cost and complexity.
- Memory cost is negligible: a LineString is a list of coordinate tuples, and Python's `reversed()`
  creates a new list (not a deep copy of floats).

Test `test_raw_graph_reverse_arc_geometry` must validate that for every bidirectional pair
`(u, v, k)` and `(v, u, k+"_R")`, the reverse arc's coordinates are exactly
`list(reversed(forward_arc.coords))`.

### 8. Graph serialization: Shapely pickle vs WKB/WKT or node-link JSON

The plan proposes storing Shapely `LineString` objects directly in edge attributes and serializing
the graph via `pickle`. This couples the artifact to:
- **Shapely version** (Shapely 2.x geometries are GEOS 3.11+ backed; pickle format may break across
  major versions).
- **Python version** (pickle protocol 4 is Python 3.4+, compatible with 3.12, but not guaranteed
  forward).
- **Security** (unpickling untrusted data can execute arbitrary code — not a concern here, but
  worth noting).

Alternatives:
1. **WKB (Well-Known Binary)**: Store `geom.wkb` (bytes) and deserialize with `shapely.wkb.loads()`.
   Portable across Shapely versions, but adds serialize/deserialize cost at every graph load.
2. **WKT (Well-Known Text)**: Human-readable, but slower than WKB and bloats file size (~3× larger).
3. **Node-link JSON** (`nx.node_link_data()`): Portable, interoperable, but requires converting
   geometries to WKT/WKB, and is ~10× slower to read/write than pickle for large graphs.

**Decision:** Use standard-library `pickle.dump(..., protocol=5)` with Shapely objects as specified.
NetworkX 3 removed `nx.write_gpickle()`, so graph serialization must not depend on that legacy API.
Rationale:
- `graph_raw.pkl` is an **internal ETL intermediate**, not an interop format. All consuming code
  (DT-006 through DT-010) runs in the same container with the same Python + Shapely versions,
  enforced by `infra/docker-compose.yml` pinning `python:3.12-slim`.
- Pickle is 10–50× faster than JSON for graphs with heavy attributes, and DT-007 contraction loads
  the graph, modifies it heavily, and saves it — performance matters.
- If a future external consumer needs the graph, add a separate export function
  (`export_graph_geojson()`, `export_graph_gpkg()`) rather than penalising the ETL pipeline.

Document in `graph.py`: "Graph artifacts are serialized with standard-library pickle protocol 5.
Do not unpickle graphs from untrusted sources. If Shapely or NetworkX versions change, rebuild
artifacts from DT-003 source data."

### 9. Deterministic artifact expectations and timestamp handling

The plan mandates deterministic graph construction (AC6) but includes a `timestamp` field in
`graph_raw_stats.json`. Timestamps are inherently non-deterministic (unless mocked for tests), so
what does "deterministic" mean?

**Clarification:**
- **Graph structure determinism**: Given the same GeoPackage input, the graph (nodes, edges,
  attributes) must be identical across runs. This is testable: run `build_raw_graph()` twice,
  assert node and edge sets are equal (pickle bytes may differ due to dict iteration order in
  Python <3.7, but NetworkX graph equality is well-defined).
- **Artifact determinism**: The pickle and JSON files may differ in binary representation (due to
  dict ordering or timestamp metadata), but the **semantically relevant content** is stable.

**Timestamp handling:**
- `graph_raw_stats.json` includes `"timestamp": "<ISO 8601 UTC>"` for audit and debugging (e.g., "I
  ran DT-005 at 2026-08-31T14:23:00Z, why does DT-006 fail?").
- Tests mock `datetime.now(timezone.utc)` to a fixed value (`2026-08-31T00:00:00Z`) when validating
  JSON schema, so the test is deterministic.
- The timestamp does **not** affect graph semantics or routing behaviour; it's metadata only.

### 10. graph_raw_stats.json schema

The plan lists stats fields scattered across multiple sections. Consolidate into a complete schema:

```json
{
  "etl_version": "0.1.0",
  "timestamp": "2026-08-31T14:23:00Z",
  "node_count": 15234,
  "edge_count": 44852,
  "mean_degree": 5.88,
  "self_loops_removed": 3,
  "self_loop_fids": ["12345", "67890", "11223"],
  "isolated_nodes": 0,
  "levels_processed": ["AQ 1000", "AQ 2000", ..., "SH 3000"],
  "connectivity_by_level": {
    "SFU_BURNABY_QUAD_L_3000": {
      "component_count": 1,
      "largest_component_size": 3421,
      "total_nodes": 3421
    },
    ...
  },
  "z_range_by_level": {
    "SFU_BURNABY_QUAD_L_3000": {
      "min": 154.32,
      "max": 156.89,
      "mean": 155.61,
      "stddev": 0.43
    },
    ...
  },
  "warnings": [
    "Level SFU_BURNABY_STRAND_L_100 has Z range 8.7 m (expected <5 m) — possible data issue"
  ]
}
```

All fields required except `warnings` (empty list if none). `level_id` keys in nested dicts are the
raw GDB `LEVEL_ID` values (e.g., `SFU_BURNABY_QUAD_L_3000`), not `vertical_order` integers — this
matches the source data and aids manual cross-reference.

### 11. Source GeoPackage read-only behaviour and artifact isolation

The plan states `build/wayfinding.gpkg` is read-only during graph construction, but NetworkX graph
construction has no filesystem writes (it's an in-memory operation until artifact serialization).
Clarify the boundary:

- **Read-only source GDB**: `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb` is
  mounted `:ro` in Docker (ADR-0002), enforced by
  `tests/gate/test_gdb_readonly.sh` (the original gate) and extended by DT-005 to include
  `build/wayfinding.gpkg` as a read-only input (it was written by DT-003/DT-004, now consumed by
  DT-005). Concretely:
  - `ogrinfo`, `ogr2ogr`, and `ogr.Open(gpkg_path, 0)` (read-only mode) are the only filesystem
    operations.
  - No `ogr.Open(gpkg_path, 1)` (write mode), no SQL `INSERT`, `UPDATE`, or `DELETE`.
- **Output artifacts**: `build/graph_raw.pkl`, `build/node_map.pkl`, `build/graph_raw_stats.json`
  are new files created by DT-005. They do **not** live inside the GeoPackage; they are separate
  files in `build/`.

Test `test_gpkg_read_only` (AC7) captures the GeoPackage `mtime` before running `build_raw_graph()`,
then asserts `mtime` is unchanged after.

### 12. Connectivity gate timing: within-level (DT-005) vs cross-level (DT-006)

The plan proposes **within-level connectivity** for DT-005 (each level filtered by `level_id`,
expect 1–3 components) and defers **cross-level connectivity** (the full walking/accessible profile
checks) to DT-006. This is correct because DT-005 has no transition edges yet — cross-level
connectivity is impossible.

However, "within-level connectivity" is **informational only, not a hard gate** (AC5 clarification).
A level with 5 components (e.g., multiple detached wings or isolated rooms) is logged as a warning,
not a build failure — it may be legitimate topology (e.g., rooms connected only via stairs, which
are DT-006 edges). The hard gate is **zero isolated nodes** (any node with degree 0 is a snapping
bug or data corruption).

DT-006 will add the cross-level connectivity gate: after adding transition edges, the graph
filtered to `mode in ['pathway', 'stairs', 'elevator']` must have exactly 1 connected component
(PHASE-1-ETL AC4). The accessible-profile gate (`mode in ['pathway', 'elevator']`, stairs excluded)
allows >1 component but must report the reachability matrix (gap G2 acknowledgment).

### 13. Dependency additions to pyproject.toml

DT-005 requires `networkx>=3.0` (for `MultiDiGraph` API stability) and `shapely>=2.0` (for GEOS
3.11+ backed geometries and performance). Add to `packages/wayfinding/pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.0.0",
    "networkx>=3.0",
    "shapely>=2.0",
]
```

Shapely is a transitive dependency of GDAL (which is in the Docker image, not in `pyproject.toml`
— see ADR-0002), but explicitly pinning it ensures version consistency. NetworkX is pure-Python and
has no binary dependencies, so it installs cleanly in the container.

## Decision

Adopt all thirteen proposals above:

1. **Graph model:** `NetworkX MultiDiGraph` with bidirectional edges (2 arcs per feature).
2. **Node identity:** Snapped coordinate tuple `(round_half_up(x, 2), round_half_up(y, 2),
   vertical_order)` used directly as node ID (no separate ID allocation).
3. **Node-map vs graph membership:** `snap_nodes()` produces a map of all endpoints (pathways +
   transitions); `build_raw_graph()` adds nodes to NetworkX graph only when adding edges
   (on-demand). Serialize `node_map.pkl` for DT-006.
4. **Edge key convention:** `<prefix>_{feature_id}` (forward), `<prefix>_{feature_id}_R` (reverse);
   prefix = `PW` (pathway), `TR` (transition), `UC` (unit connector).
5. **Multipart geometry endpoints:** Start = first coord of first part, end = last coord of last
   part.
6. **Edge weight source:** Use `LENGTH_3D` field directly, no validation against computed length.
7. **Reverse-edge geometry:** Store `LineString(reversed(forward_coords))` on reverse arc.
8. **Serialization format:** NetworkX pickle with Shapely objects (internal intermediate; portability
   not required).
9. **Determinism:** Graph structure is deterministic; timestamp in JSON is metadata (mocked in
   tests).
10. **Stats schema:** Full JSON schema as specified in §10, all fields required except `warnings`.
11. **Read-only enforcement:** GeoPackage `mtime` unchanged after graph construction; new artifacts
    written only to `build/*.pkl` and `build/*.json`.
12. **Connectivity gate:** Within-level connectivity is informational (warning if >5 components);
    zero isolated nodes is a hard failure. Cross-level connectivity deferred to DT-006.
13. **Dependencies:** Add `networkx>=3.0` and `shapely>=2.0` to `pyproject.toml`.

## Consequences

### Positive

- **Node IDs are self-documenting**: A graph with node `(505123.46, 5458789.12, 0)` is immediately
  interpretable without a separate lookup table (contrast with "node 7243" or UUID).
- **No isolated-node contradiction**: Transition endpoints are snapped but not graphed until DT-006,
  satisfying both AC1 (unified node space) and AC5 (zero isolated nodes).
- **Future-proof graph model**: `MultiDiGraph` supports one-way features without migration; parallel
  edges before contraction are natural.
- **Fast serialization**: Pickle is 10–50× faster than JSON; critical for DT-007 contraction (which
  loads, modifies heavily, and saves).
- **Explicit grid quantization**: Round-half-up semantics avoid banker's rounding surprises; 1 cm
  precision is well-documented.
- **Testable edge-key convention**: The `_R` suffix makes reverse-pair detection mechanical,
  simplifying DT-007 and DT-010 logic.

### Negative

- **Pickle version coupling**: If Shapely or NetworkX major version changes, artifacts must be
  rebuilt from DT-003. Mitigated by container pinning (`python:3.12-slim` with explicit
  `requirements.txt`) and documented in `graph.py`.
- **Node ID float precision**: Using `(float, float, int)` tuples means node IDs are subject to
  floating-point equality semantics. Mitigated by explicit 1 cm rounding (2 decimal places) — no
  floating-point comparisons on raw coordinates.
- **Multipart geometry assumption**: If a pathway has truly disjoint parts (not end-to-end), the
  start-of-first / end-of-last heuristic produces a wrong edge. Detection deferred to DT-009
  validation; no evidence of such features in the data findings.
- **No LENGTH_3D validation**: If source geometries are corrupted, we trust a potentially wrong
  weight. Acceptable because DT-009 routing validation will fail if costs are nonsensical; earlier
  detection is not critical.

### Superseded decisions

None. This ADR is independent of ADR-0002 (container model) and ADR-0003 (normalised schema);
it complements them by defining the graph-construction layer above the normalised GeoPackage output.

### Downstream impacts

- **DT-006 (add transitions):** Must load `node_map.pkl` to look up transition endpoints; must
  follow the `TR_{feature_id}` / `TR_{feature_id}_R` key convention.
- **DT-007 (contraction):** Can rely on reverse arcs having pre-reversed geometry for chain merging;
  can detect reverse pairs via `_R` suffix.
- **DT-008 (unit connectors):** Must use `UC_{unit_id}` / `UC_{unit_id}_R` edge key prefix.
- **DT-009 (validation):** Must load `graph_raw_stats.json` schema; must parse `warnings` list.
- **DT-010 (instructions):** Can access `edge['geometry']` directly for bearing calculations; no
  runtime reversal needed.

### Data-QA implications

- Isolated nodes (degree 0) now fail the build immediately, forcing investigation. Expected: zero
  failures after DT-003/DT-004 data-QA passes.
- Z range warnings (>5 m within a level) are logged but non-blocking; facilities staff can triage.
- `graph_raw_stats.json` becomes the authoritative audit log for graph construction; version it with
  the GeoPackage hash for reproducibility.

### Documentation requirements

- Update `packages/wayfinding/src/wayfinding/etl/graph.py` module docstring: explain node ID format,
  edge key convention, and pickle portability caveat.
- Update [docs/02-system-design.md §3.3](../02-system-design.md#33-graph-construction): replace
  "undirected graph" with "`MultiDiGraph` with bidirectional edges" and cite this ADR.
- Add `build/node_map.pkl` to `.gitignore` (it's an artifact, not source).
- Update [docs/plans/DT-005.md](../plans/DT-005.md) §2.2 Outputs: replace "UUID or sequential int"
  node IDs with "snapped coordinate tuple", add `node_map.pkl` to artifact list.
