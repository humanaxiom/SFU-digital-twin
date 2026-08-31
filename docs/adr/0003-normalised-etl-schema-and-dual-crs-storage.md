# 3. Normalised ETL schema and dual-CRS storage

Status: Accepted  
Date: 2026-08-30

## Context

DT-004 (Normalise Tables) transforms the 14 raw extracted layers from DT-003 into a normalised
schema that serves as the authoritative spatial foundation for routing (DT-005), search (DT-010),
and basemap rendering (DT-011). The plan surfaces six unresolved design decisions that cross package
and component boundaries:

### 1. Table count: six normalised tables vs five in phase summary

[docs/plans/PHASE-1-ETL.md DT-004](../plans/PHASE-1-ETL.md#dt-004-normalise-tables) states:

> Output: 5 normalised tables written to `build/wayfinding.gpkg`: `facility`, `level`, `unit`,
> `landmark`, `detail`

But [docs/plans/DT-004.md §2.2](../plans/DT-004.md#22-outputs) lists **six** tables, adding `door`
(6,865 rows split from `Details` where `USE_TYPE='ADO'`). The door split is justified by
[docs/02-system-design.md §3.2](../02-system-design.md#32-normalise):

> split ADO (doors) into its own table for instruction hints

and further detailed in §5 (turn-by-turn instruction generation), which references intersecting
door-line geometry. PHASE-1-ETL.md AC6 does mention the door split ("split into its own table
`door`") but does not count it in the "5 normalised tables" output statement — an inconsistency.

### 2. Normalised tables must coexist with DT-003 raw layers

DT-004.md §2.2 states the six tables **"replace the 14 raw layers"** from DT-003. However,
[docs/plans/PHASE-1-ETL.md DT-005](../plans/PHASE-1-ETL.md#dt-005-graph-node-snapping-and-raw-graph-construction)
explicitly requires:

> Input: DT-004 (normalised `level` table for `vertical_order` lookup), raw `Pathways_26910` and
> `Transitions_26910` layers from DT-003.

The graph-construction pipeline (DT-005 through DT-007) consumes the raw, over-noded `Pathways_26910`
and `Transitions_26910` layers (22,426 + 63 features) and then contracts them. If DT-004 deleted the
raw layers, DT-005 would fail. The normalised tables are **derived products for search and
rendering**, not the routing network itself; the routing network is built from the raw pathway
geometry and then contracted.

**Conclusion:** "replacing" is incorrect; normalised tables must be **added alongside** the raw layers.

### 3. GeoPackage cannot naturally store dual registered geometries per table

Every normalised table schema in
[packages/wayfinding/src/wayfinding/etl/schema.py](../../packages/wayfinding/src/wayfinding/etl/schema.py)
defines two geometry fields:

```python
geom_26910: str = Field(..., description="Geometry in EPSG:26910 (WKT or binary)")
geom_wgs84: str = Field(..., description="Geometry in EPSG:4326 (WKT or binary)")
```

This design is driven by dual-CRS requirements
([docs/02-system-design.md §3.1](../02-system-design.md#31-extract)):

> Keep native **EPSG:26910** for all metric computation (lengths, bearings, snapping); reproject a
> display copy to **EPSG:4326** for the web client. Never compute distance in 4326.

GeoPackage (and OGR/GDAL layer model) supports only **one registered geometry column per layer**.
Storing two CRS representations as separate geometry fields in a single feature table is possible via
unregistered WKB BLOB columns, but those are invisible to QGIS/OGR spatial indexing and violate the
principle that geometry should be queryable without raw binary decoding.

**Options considered:**

1. **Paired layers** (e.g., `unit_26910` and `unit_wgs84` as separate feature tables): Doubles layer
   count (12 total), duplicates all non-geometry attributes, and complicates foreign-key
   references — does `landmark.level_id` reference `level_26910.level_id` or
   `level_wgs84.level_id`? Both are identical, but the duplication is conceptual noise.

2. **One registered geometry + one WKB BLOB field**: E.g., `geom` (registered EPSG:26910) +
   `geom_wgs84` (BLOB). Simple, compact, but the BLOB column is not spatially indexed and invisible
   to QGIS, breaking the "open in QGIS to inspect" QA workflow documented in DT-009.

3. **Views over paired tables**: Store `unit_26910` and `unit_wgs84` as physical tables, then create
   `unit` view joining on `unit_id` with both geometries. Preserves spatial indexing, queryable in
   QGIS, but adds SQL view complexity and is not portable to systems that don't support views (e.g.,
   Shapefile export, though Shapefile is not a target).

4. **Single-CRS per layer + reproject on read**: Store only EPSG:26910 geometry in normalised
   tables; web client reprojects via `ST_Transform()` at query time or via PMTiles tile generation
   (which already reprojects). Simplest, no duplication, but adds runtime cost and makes the
   EPSG:4326 copy (which is expensive to compute for 56k+ records) non-persistent.

The DT-003 ETL already extracts 14 layers (7 dual pairs) to amortise the reprojection cost — if we
chose option 4, DT-003's dual extraction would be wasted. The reference `dtwin-harness` repository
uses **option 1 (paired layers)** for exactly this reason: EPSG:26910 is the computational CRS,
EPSG:4326 is the rendering CRS, and both are persisted to avoid repeated reprojection. The layer
duplication is acceptable because:

- The normalised schema has only 6 tables → 12 layers is manageable.
- Foreign keys reference the CRS-agnostic `_id` fields (e.g., `unit_id`), which are identical across
  both CRS layers.
- The routing graph (DT-005–DT-007) and search index (DT-010) consume only EPSG:26910 layers; the
  EPSG:4326 layers are strictly for the web client and PMTiles generation (DT-011).

**Conclusion:** Use paired layers. The Pydantic schemas in `schema.py` are documentation-only
(validation models, not OGR create specs); the actual GeoPackage will have 12 feature tables:
`facility_26910`, `facility_wgs84`, `level_26910`, `level_wgs84`, etc.

### 4. Unit accessibility metadata must include provenance and conservative defaults

`UnitSchema` in schema.py defines:

```python
accessible: bool | None = Field(None, description="Accessibility flag from category mapping")
```

But [.github/instructions/accessibility-claims.instructions.md](../../.github/instructions/accessibility-claims.instructions.md)
mandates:

> Any field that drives an accessibility decision must carry `verified_by` and `verified_date`.
> Unknown must never default to accessible.

The `accessible` field is **destination** metadata (e.g., "this washroom is accessible") derived from
[packages/wayfinding/src/wayfinding/etl/category_mapping.yaml](../../packages/wayfinding/src/wayfinding/etl/category_mapping.yaml),
**not** route accessibility. It answers "can a wheelchair user use this room?" not "can a wheelchair
user reach this room?" The latter is a routing-profile question (DT-005+) and is subject to the
elevator-only honesty rule documented in
[docs/02-system-design.md §4.2](../02-system-design.md#42-accessible-mode--exactly-what-it-does-and-does-not-claim).

The source geodatabase has 38 units explicitly tagged as accessible via free-text `USE_TYPE` values:
- "Washroom, single-stall, accessible" (15)
- "Washroom, men's, accessible" (12)
- "Washroom, women's, accessible" (11)

These are the **only** explicit accessibility signals in the data
([docs/01-data-findings.md §4](../01-data-findings.md#4-units-the-destination-catalogue)). The
category mapping YAML codifies these into `accessible: true` rules; all other units default to
`accessible: null` (unknown), never `true`.

**Missing:** The schema has no `verified_by` or `verified_date` fields. DT-004 must add:

```python
accessible: bool | None = Field(None, description="Destination is accessible (not route)")
verified_by: str | None = Field(None, description="Provenance: who verified accessibility")
verified_date: str | None = Field(None, description="ISO 8601 date of verification")
```

For the initial dataset, where accessibility is derived from the source GDB's `USE_TYPE` field
(which is unverified), populate `verified_by = "source_gdb_use_type"` and `verified_date =
<GDB_modification_date or ETL_run_date>`. This satisfies the provenance rule without fabricating a
false audit trail.

**Semantic clarity:** The field must be documented as destination accessibility, not route
accessibility. A unit with `accessible=true` means "the room itself is accessible" (e.g., wide door,
grab bars in a washroom); it does **not** mean "you can reach this room step-free" — that is the
routing profile's responsibility. The API must never conflate the two.

### 5. PK derivation for Details/Landmarks and deterministic clustering

`DetailSchema`, `DoorSchema`, and `LandmarkSchema` define opaque string PKs (`detail_id`, `door_id`,
`landmark_id`) but do not specify how they are derived.

For `detail_id` and `door_id`: Preserve the source `DETAIL_ID` string field directly from
Details_AQ_SH_ECC layer (verified in build/wayfinding.gpkg Details_26910 layer; no GlobalID field
exists). Do NOT fabricate prefixes or use OBJECTID. The DETAIL_ID field is a string, already unique,
and traceable to source.

**For landmarks specifically**, deduplication via spatial clustering (0.5 m threshold) means the
output landmark count (40) is less than input count (41), so output `landmark_id` cannot simply be
a pass-through of source OBJECTID or DETAIL_ID (which doesn't exist). Landmarks_AQ_SH_ECC has no
GlobalID or DETAIL_ID field (verified in build/wayfinding.gpkg Landmarks_26910 layer; fields are
DESCRIPTION, LEVEL_ID, VERTICAL_ORDER, FID only). Options:

1. Use the source FID of the **representative point** in each cluster (the one kept after
   deduplication), prefixed with `LMK_` → stable if clustering is deterministic.
2. Hash the cluster centroid + category + level_id → fully deterministic even if representative point
   selection varies, but opaque and harder to debug.

**Clustering algorithm specification:** DT-004.md §2.3 states:

> group by `(category, level_id)`, cluster within 0.5 m

But "cluster within 0.5 m" is ambiguous — does this mean:

- **DBSCAN** with `eps=0.5, min_samples=1`? Produces deterministic clusters but depends on point-order
  for representative selection unless explicitly sorted.
- **Manual spatial join** (for each point, find all others within 0.5 m, group into clusters)? Same
  determinism issue.
- **Greedy first-point-wins** (sort points by OBJECTID or coordinates, for each point, mark all
  others within 0.5 m as duplicates)? Fully deterministic if sort is stable.

**Decision:** Use greedy first-point-wins with sort by `(category, level_id, X, Y)` to ensure
determinism across platforms (GCC/MSVC/etc. may sort differently without an explicit key). The
representative point is the first point in sort order for each cluster; its `landmark_id` is derived
from its source FID, prefixed with `LMK_`.

### 6. normalise_details function signature: dual return vs split functions

DT-004.md §5.1 (test signatures) shows:

```python
normalise_details(gpkg_path) -> dict[str, int]  # returns detail + door counts
```

But §6 (implementation steps) treats door extraction as part of `normalise_details()`, and the test
list (§5.6, tests 18–21) covers both detail and door tables. The signature implies a single function
handling both tables.

However, the acceptance criteria (AC6, AC7) distinguish `detail` table and `door` table as separate
outputs, and the table counts (48,728 vs 6,865) suggest they are independently testable. A cleaner
API would be:

```python
normalise_details(gpkg_path) -> int  # returns detail row count
normalise_doors(gpkg_path) -> int    # returns door row count
```

But this duplicates the Details layer read operation (55,593 features read twice, filtered
differently). The combined function is more efficient:

```python
normalise_details(gpkg_path) -> dict[str, int]
# Returns {"detail": 48728, "door": 6865}
# Reads Details layer once, splits by USE_TYPE='ADO'
```

**Tradeoff:** Single-responsibility principle (one function per table) vs DRY principle (don't read
the same 55k features twice). Given that Details and Doors share a source layer and are split by a
single predicate (`USE_TYPE='ADO'`), the combined function is justified. The function name
`normalise_details` is slightly misleading (it also produces doors), but renaming to
`normalise_details_and_doors` is verbose. Accept the slight semantic overload; document the dual
output clearly in the docstring.

**Conclusion:** Keep `normalise_details(gpkg_path) -> dict[str, int]` returning both counts. Update
DT-004.md §5.1 test signature list to clarify this is intentional.

## Decision

### 1. Six normalised tables, update PHASE-1-ETL.md

The door table is table #6. Update
[docs/plans/PHASE-1-ETL.md DT-004 Output](../plans/PHASE-1-ETL.md#dt-004-normalise-tables) from "5
normalised tables" to "6 normalised tables: `facility`, `level`, `unit`, `landmark`, `detail`,
`door`". The door split is not a schema addition (it is derived from the existing Details layer); it
is a table-organization refinement justified by turn-by-turn instruction requirements.

### 2. Normalised tables coexist with raw layers, do not replace them

DT-004 **adds** 6 normalised tables (12 layers with dual CRS) to `build/wayfinding.gpkg` alongside
the 14 raw extracted layers from DT-003. The raw `Pathways_26910` and `Transitions_26910` layers
remain intact for DT-005 graph construction. Update DT-004.md §2.2 from "replacing the 14 raw layers"
to "written to `build/wayfinding.gpkg` alongside the 14 raw layers from DT-003".

Final GeoPackage layer count after DT-004: 14 (raw) + 12 (normalised dual-CRS) = **26 layers**.

### 3. Paired layers for dual-CRS storage

Each normalised table is persisted as two GeoPackage feature layers: `<table>_26910` (EPSG:26910, 3D
where source is 3D) and `<table>_wgs84` (EPSG:4326, 2D). Non-geometry attributes (PKs, FKs, metadata)
are duplicated across both layers. Foreign keys reference CRS-agnostic `_id` fields (e.g.,
`unit.level_id` references `level.level_id`, which is identical in both `level_26910` and
`level_wgs84`).

The Pydantic schemas in `schema.py` remain as documentation/validation models; they do not drive OGR
layer creation directly. The schemas document logical dual geometry fields (`geom_26910` and
`geom_wgs84`), but physical GeoPackage layers have only ONE registered geometry column named `geom`
in the target CRS (EPSG:26910 for `_26910` layers, EPSG:4326 for `_wgs84` layers). Add a comment to
`schema.py` clarifying:

```python
# Note: These schemas define the logical table structure. In the GeoPackage,
# each table is stored as two layers (<table>_26910 and <table>_wgs84) due to
# GeoPackage's single-geometry-per-layer constraint. Each physical layer has
# ONE registered geometry column named 'geom' in the target CRS, not
# separate geom_26910+geom_wgs84 columns in one layer. See ADR-0003.
```

**Consequence:** Routing and search code must explicitly query `_26910` layers; web-client code
queries `_wgs84` layers. No code should query the schema-named table directly (e.g., `unit` does not
exist as a layer; only `unit_26910` and `unit_wgs84` exist).

### 4. Add accessibility provenance fields to UnitSchema

Extend `UnitSchema` in schema.py:

```python
accessible: bool | None = Field(
    None,
    description="Destination is accessible (e.g., accessible washroom). "
                "This is NOT route accessibility; see routing profile."
)
verified_by: str | None = Field(
    None,
    description="Provenance of accessibility claim (e.g., 'source_gdb_use_type', 'facilities_audit_2026')"
)
verified_date: str | None = Field(
    None,
    description="ISO 8601 date source was verified (e.g., '2026-08-29'). "
                "Records source provenance, not ETL run date."
)
```

For units where `accessible` is non-null (true OR false) and derived from `category_mapping.yaml`,
populate:
- `verified_by = "source_gdb_use_type"`
- `verified_date = "2026-08-29"` (stable source GDB directory mtime 2026-08-29T01:44:22Z, preserves
  idempotency; NOT ETL run date. This records source provenance, not a facilities audit.)

For units where `accessible=null` (unknown), leave `verified_by` and `verified_date` as `null` — do
not fabricate a verification record for unverified data. Both true and false drive accessibility
decisions (e.g., stairs are explicitly inaccessible), so both require provenance.

**Unknown defaults to null, never true.** The 38 explicitly accessible units (washrooms) are the
only ones with `accessible=true`; all other 979 searchable units default to `accessible=null`.

**Add to DT-004 acceptance criteria:** AC4 must assert `verified_by` and `verified_date` are
populated for all rows where `accessible` is non-null (true OR false), and AC11 (accessibility
provenance test) must verify `verified_by` and `verified_date` are never null when `accessible` is
non-null. Both true and false values drive routing decisions.

### 5. PK derivation: preserve DETAIL_ID for details/doors, use LMK_<FID> for landmarks

For `detail_id` and `door_id`: Preserve the source `DETAIL_ID` string field directly from
Details_AQ_SH_ECC layer (verified in build/wayfinding.gpkg Details_26910 layer; no GlobalID field
exists). Do NOT fabricate prefixes or use OBJECTID. The DETAIL_ID field is a string, already unique,
and traceable to source.

For `landmark_id`: Landmarks_AQ_SH_ECC has no GlobalID or DETAIL_ID field (verified in
build/wayfinding.gpkg Landmarks_26910 layer; fields are DESCRIPTION, LEVEL_ID, VERTICAL_ORDER, FID
only). Derive from source FID (OBJECTID in source GDB, mapped to `fid` in GeoPackage) of the
representative point after deduplication, prefixed with `LMK_` for type clarity.

**Clustering algorithm:** Greedy first-point-wins, sorted by `(category, level_id, X, Y)` ascending.
For each point, mark all others within 0.5 m (Euclidean in EPSG:26910) as duplicates; keep the first
point. This is fully deterministic across platforms. Containerized GDAL pairwise query found exactly
one same-category/same-level landmark pair ≤0.5 m apart (FIDs 28 and 41 at 0.250728 m), yielding
exactly 40 output landmarks (41 source features - 1 duplicate).

**Test:** DT-004 AC10 (idempotent execution) must assert landmark IDs are identical across two
independent ETL runs.

### 6. normalise_details returns dict with both table counts

Signature:

```python
def normalise_details(gpkg_path: Path) -> dict[str, int]:
    """
    Normalise Details layer into detail and door tables.

    Reads Details_26910 and Details_wgs84 once, splits by USE_TYPE:
    - USE_TYPE='ADO' → door table (6865 rows)
    - All other USE_TYPE → detail table (48728 rows)

    Returns:
        {"detail": <row_count>, "door": <row_count>}
    """
```

Update DT-004.md §5.1 test list to clarify this is intentional (add a note: "normalise_details
handles both detail and door tables in one pass for efficiency").

### 7. Schema change is internal, no ADR for DoorSchema itself

Adding `DoorSchema` to schema.py is an ETL-internal change (no API surface, no downstream impact
beyond test expectations). This ADR covers the **storage model and table organization**, not the
schema addition itself. DoorSchema follows the same pattern as DetailSchema; it is a data-split
refinement, not a new spatial operation.

## Consequences

### Positive

- **Table count is explicit and traceable.** PHASE-1-ETL.md and DT-004.md are now consistent:
  6 normalised tables → 12 GeoPackage layers (dual CRS).

- **Raw layers preserved for graph construction.** DT-005 can consume `Pathways_26910` and
  `Transitions_26910` without dependency on normalised schema; graph construction is decoupled from
  search/rendering schema.

- **Dual-CRS storage is simple and inspectable.** Paired layers are queryable in QGIS, spatially
  indexed, and avoid WKB BLOB hacks. The 12-layer GeoPackage is manageable for a 6-table schema.

- **Accessibility claims are provenance-tracked.** Every `accessible=true` value traces to
  `verified_by` and `verified_date`, satisfying
  [.github/instructions/accessibility-claims.instructions.md](../../.github/instructions/accessibility-claims.instructions.md).
  Unknown defaults to null, not true.

- **Destination vs route accessibility is semantically clear.** The `accessible` field is documented
  as destination metadata; route accessibility is a separate concern (routing profile + elevator-only
  rule).

- **Landmark deduplication is deterministic.** Greedy first-point-wins with stable sort ensures
  identical output across platforms and reruns, satisfying AC10 (idempotency).

- **normalise_details API is efficient.** Reading Details layer once (55,593 features) and splitting
  in-memory is faster than two separate reads. The dict return clearly signals dual output.

### Negative

- **12 GeoPackage layers is verbose.** A developer inspecting `build/wayfinding.gpkg` in QGIS sees
  24 layers total (14 raw + 12 normalised). Naming convention (`_26910` / `_wgs84` suffixes) is
  critical for clarity; a layer-list README in the GeoPackage user_data table is recommended.

- **Foreign key references are CRS-agnostic but not enforced.** `unit_26910.level_id` and
  `unit_wgs84.level_id` both reference a `level_id` that exists in both `level_26910` and
  `level_wgs84`. GeoPackage FK constraints can only point to one table; choosing `level_26910` as
  the FK target would be arbitrary. Solution: do not use GeoPackage FK constraints; enforce
  referential integrity in ETL validation (DT-004 AC8, AC22–24).

- **Clustering algorithm is greedy, not optimal.** DBSCAN would find true 0.5 m clusters, but greedy
  first-point-wins can produce suboptimal clusters if points are collinear. Example: points A, B, C
  in a line, where `dist(A,B)=0.4 m`, `dist(B,C)=0.4 m`, `dist(A,C)=0.8 m`. Greedy keeps A and C
  (both >0.5 m from each other), while DBSCAN would keep only one. Mitigation: 0.5 m threshold is
  conservative for landmark deduplication (vending machines are ~1 m wide); suboptimal clustering is
  acceptable.

- **Accessibility provenance is GDB-derived, not audit-verified.** `verified_by="source_gdb_use_type"`
  is honest but weak — the source GDB has no audit trail for who verified the "accessible" tag in
  `USE_TYPE`. A future Facilities accessibility survey (per
  [docs/02-system-design.md §12 open question 2](../02-system-design.md#12-open-questions-for-stakeholders))
  would override this with `verified_by="facilities_survey_2027"` and a real audit date.

### Affected components

- **DT-004 plan:** Update §2.2 from "5 normalised tables" to "6 normalised tables", clarify
  "coexist with raw layers, do not replace". Add `verified_by` and `verified_date` to AC4 and AC11.
  Clarify clustering algorithm and `normalise_details` return dict in §5.

- **PHASE-1-ETL.md:** Update DT-004 output from "5 normalised tables" to "6 normalised tables:
  `facility`, `level`, `unit`, `landmark`, `detail`, `door`". Add note: "stored as 12 GeoPackage
  layers (dual CRS pairs)."

- **schema.py:** Add `verified_by` and `verified_date` fields to `UnitSchema`. Add comment
  clarifying Pydantic schemas are logical models; physical storage is dual CRS layers. Add
  `DoorSchema` (already planned in DT-004 Step 1).

- **category_mapping.yaml:** No change required (already has `accessible: true/false` flags for 38
  units).

- **DT-005 plan:** No change required (already consumes raw `Pathways_26910` and
  `Transitions_26910`, plus normalised `level_26910` for vertical_order lookup).

- **Test suite:** DT-004 tests must query `<table>_26910` layers, not bare `<table>` names. AC4 and
  AC11 must assert `verified_by` and `verified_date` are populated correctly.

### Supersedes

No prior ADRs. This is the first ADR defining ETL output schema.

### Independent of

- **ADR-0001** (record architecture decisions): process-only ADR, no technical conflict.
- **ADR-0002** (package layout and container execution): ETL runs in the container service defined
  there; this ADR defines what the ETL produces, not how it runs.
