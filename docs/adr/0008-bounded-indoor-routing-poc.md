# 8. Bounded indoor routing proof of concept

Status: accepted
Date: 2026-09-10

## Context

The stakeholder demo now needs to answer a real question: how to get from one known indoor room to
another. DT-013 deliberately refuses routing because no endpoint attachment, routing service, or
instruction generator exists ([ADR-0007](0007-dt-013-artifact-backed-demo-vertical-slice.md)). The
target architecture already requires deterministic graph routing and forbids the assistant from
computing geometry, distance, directions, or accessibility claims
([system design sections 2 and 8](../02-system-design.md)).

The repository has a measured legacy artifact set suitable for a bounded proof of concept:

- `build/wayfinding.gpkg` contains 1,017 normalized searchable units and the floor-plan layers used
  by DT-013;
- `build/graph_contracted.pkl` contains 7,450 nodes and 19,884 directed arcs, including 84 stairs
  arcs and 42 elevator arcs; and
- `build/graph_contracted_stats.json` records 816 default-profile components, 840 elevator-only
  components, exact immediate-input/output SHA-256 values, and exact shortest-path preservation for
  its 20 seeded checks.

This graph is severely fragmented. ADR-0005 therefore permits routing only within a connected
component and requires an explicit no-route result for disconnected endpoints. The final DT-009
source-to-route build report is not present, so the PoC can identify and verify the exact local
artifacts it used but must not claim that their lineage represents either newly discovered source.

Three immutable local geodatabases now exist: the legacy `IndoorWayfinding.gdb`,
`IndoorWayfinding_AQ_SH_ECC_Revised.gdb` with revised pathways, and
`AdditionalData_Testing.gdb` with entrance, main-door, and ramp survey features. The revised graph
has not been profiled, rebuilt, reconciled, or measured. The supplemental features do not establish
indoor or outdoor traversability and lack the provenance needed to strengthen an accessibility
claim. Selecting either source for an urgent demo would replace known limitations with unknown
ones.

The system design says to add zero-cost unit connector edges from each centroid to the nearest
same-level pathway node. With no authoritative doorway-to-path relationship, rendering or
narrating such an edge as walkable could imply travel through a wall. A route can still use the
nearest same-level node as a disclosed endpoint anchor without making that segment part of the
routing graph or directions.

## Decision

### 1. Route the accepted legacy artifact set first

The first X-to-Y PoC uses `build/wayfinding.gpkg`, `build/graph_contracted.pkl`, and
`build/graph_contracted_stats.json` together. Startup fails closed unless all three exist and the
GeoPackage and graph byte hashes equal the immediate lineage hashes recorded in the contraction
sidecar. Every route response repeats those exact hashes and describes the source as the accepted
legacy snapshot with final source-directory lineage pending DT-009.

The revised and supplemental geodatabases remain read-only and do not enter the PoC graph. Their
profiling, rebuild, comparison, and promotion remain a follow-up evidence ticket. Promotion of the
revised source requires deterministic rebuild evidence, unit-pair reachability measurements, a new
accepted connectivity baseline, and an updated artifact-lineage report; it is not a runtime switch.
`AdditionalData_Testing.gdb` remains profile-only until a later ADR defines entrance, door, ramp,
and outdoor-network semantics. No public map geometry, public tiles, or outdoor edges are ingested.

### 2. Resolve rooms to non-traversal endpoint anchors

At startup, build an immutable endpoint catalog from normalized searchable units and contracted
graph nodes. For each unit:

1. read its stored EPSG:26910 centroid and `level_id`;
2. consider only graph nodes whose `level_ids` contains that exact `level_id`;
3. select the nearest node by planar EPSG:26910 distance, breaking equal-distance ties by the
   lexicographically sorted node tuple; and
4. mark the unit routable only when the attachment distance is at most 10 m.

The 10 m bound is an eligibility and data-QA limit inherited from the planned DT-008 contract, not
evidence that the intervening segment is traversable. Units with missing centroids, no same-level
candidate, or an attachment over 10 m are explicit endpoint failures and are never silently bound
to another level.

The catalog stores `unit_id`, `level_id`, anchor node, attachment distance, algorithm version, and
the GeoPackage/graph hashes. It does not mutate the graph, add `UC_*` edges, or publish a connector
geometry. Route distance, geometry, and steps cover only the pathway/transition graph between the
two anchors. The response and UI call both endpoint locations **approximate room anchors** and state
that the path between a room centroid or doorway and its anchor is not represented or verified.

For this PoC, this decision supersedes system design section 3.3 step 5 and the DT-008 requirement
to make centroid connectors traversable graph edges. A future door-aware attachment model may add
real traversable connectors after Facilities supplies or validates doorway relationships.

### 3. Use two explicit deterministic profiles

The PoC supports exactly:

| Profile | Allowed graph modes | Route objective |
| --- | --- | --- |
| `default` | `pathway`, `stairs`, `elevator` | shortest `length_3d` |
| `elevator_only` | `pathway`, `elevator` | shortest `length_3d`, stairs excluded |

The HTTP request requires the profile; the UI initially selects `default`. The deterministic
assistant uses `default` for ordinary direction requests and forces `elevator_only` for any
mobility phrasing. It never silently falls back from `elevator_only` to `default`.

`elevator_only` is the user-facing name for the PoC. It is not labelled “accessible route” or
“step-free verified.” Every successful or failed elevator-only response includes:

```json
{
  "basis": "TRANSITION_TYPE=4 (elevator) only; stairs excluded",
  "not_verified": ["door_width", "path_width", "slope", "powered_doors", "surface"]
}
```

No profile consumes the supplemental ramp or entrance data. Closures, opening hours, door access,
elevator status, and the unrepresented room-to-anchor segment remain unverified.

### 4. Precheck components before shortest-path computation

On startup, derive deterministic weak-component labels separately for the two filtered profile
graphs. Stable component IDs are the SHA-256 prefix of the sorted node representations in each
component, not NetworkX enumeration order. Each endpoint catalog record stores both profile IDs.

For every request, validate endpoint eligibility and compare the two profile-specific component
IDs before invoking shortest path. Different components return an explicit `409 disconnected`; the
engine does not search, bridge gaps, snap farther away, switch profiles, or infer missing topology.
An ineligible endpoint returns `422 endpoint_unavailable`. Unknown or ambiguous unit identifiers
return `404` or `409 ambiguous_endpoint` respectively.

The route itself is a deterministic shortest path over `length_3d`, with edge iteration and
equal-cost tie-breaking stabilized by node tuple and edge key. The service rejects any returned
edge whose mode is outside the selected profile. This PoC returns network distance only; it does
not estimate travel time because the target time-cost penalties have not been calibrated.

### 5. Extend only the local demo boundary

Add `POST /demo/v1/route`; do not publish the future production `/v1/route` contract. The request is:

```json
{
  "origin": {"unit_id": "..."},
  "destination": {"unit_id": "..."},
  "profile": "default"
}
```

A `200` response contains resolved endpoints and approximate-anchor distances, selected profile and
allowed modes, graph-only network distance, per-level route LineStrings in EPSG:26910, deterministic
steps, warnings, accessibility disclosure when applicable, and complete artifact provenance.
Steps are limited to `depart`, `continue`, `turn`, `enter_transition`, `exit_transition`, and
`arrive`; they are generated only from traversed edge geometry and transition attributes using the
thresholds in system design section 5. `depart` and `arrive` name the approximate anchors and do not
describe an unverified door or centroid connector.

Failures use the same JSON envelope and provenance:

- `404 unknown_endpoint` for an unknown exact unit identifier;
- `409 ambiguous_endpoint` when a room label resolves to more than one unit;
- `409 disconnected` with profile and endpoint component IDs;
- `409 no_elevator_only_route` for an elevator-only component mismatch, including the full
  accessibility disclosure;
- `422 endpoint_unavailable` with the attachment reason and measured distance when available; and
- `503 artifact_mismatch` when startup lineage checks fail.

The deterministic assistant may add one closed intent, exact “directions from X to Y,” which
resolves exact room IDs and calls this same route service. It returns the service result without
inventing coordinates, distance, steps, or accessibility language. Ambiguity and route failures are
surfaced verbatim.

### 6. Keep the UI to a stakeholder-ready indoor route slice

Reuse the DT-013 local SVG explorer. Add exact origin and destination selectors, a two-option
profile control, a route command, a per-level route overlay, deterministic step list, and visible
failure state. The floor picker follows the active step. The UI must always show:

- “Indoor pathway route between approximate room anchors”;
- both attachment distances;
- the legacy artifact provenance and limitations; and
- for `elevator_only`, “Elevators only; stairs excluded” plus all unverified properties.

Do not add MapLibre, PMTiles, FTS5, nearest-place search, outdoor routing, live location, public map
geometry, travel-time estimates, or LLM integration. The service remains loopback-only and
artifact-only under ADR-0007's security boundary.

## Consequences

### Positive

- The demo can show real deterministic X-to-Y indoor routes today without waiting for an
  unmeasured source promotion or the full production stack.
- Profile-specific component prechecks turn known fragmentation into fast, explicit, explainable
  failures rather than fabricated routes.
- Non-traversal anchors avoid drawing a false path through walls while still letting known rooms
  participate in graph routing.
- Exact artifact hashes and limitations accompany every result.

### Negative

- Coverage is limited by 816/840 components, and some or many room pairs will fail.
- The first and last room-to-pathway segments are not directions; users must visually locate the
  nearby corridor or doorway.
- The PoC optimizes distance only and does not provide calibrated travel time.
- The legacy source may have poorer connectivity than the revised pathways; that tradeoff is
  accepted temporarily because its behavior is measured.

### Supersedes and refines

This ADR refines ADR-0007 by authorizing routing inside the existing `/demo/v1` boundary and
replacing only its route-refusal requirement after all contracts above pass. All other DT-013
security, deployment, provenance, and deterministic-assistant constraints remain accepted.

For the PoC only, it supersedes the traversable zero-cost unit-connector design in system design
section 3.3 step 5 and the corresponding DT-008 plan text. The production `/v1` API, time-based
cost model, FastAPI service, MapLibre client, and door-aware destination guidance remain future
work. It does not supersede ADR-0004 graph identity, ADR-0005 connectivity limits, or ADR-0006
container and lineage boundaries.

### Required implementation work

1. `planner`: treat revised-source promotion as a follow-up evidence ticket; DT-014 implements this
   bounded PoC from the accepted artifact set.
2. `test-writer`: first add failing containerized tests for hash validation, deterministic endpoint
   catalogs, the 10 m bound, profile filtering, component prechecks, shortest-path determinism,
   instruction derivation, error envelopes, assistant delegation, and UI disclosures.
3. `implementer`: extend the artifact-only demo without mounting any geodatabase or adding runtime
   dependencies; do not modify the approved artifacts.
4. `data-qa`: publish representative successful and disconnected room pairs for both profiles and
   verify every reported edge mode, distance, level, artifact hash, and disclosure.
5. `judge`: reject any route containing inferred gap edges, any room-anchor geometry presented as
   walkable, silent profile fallback, outdoor/public geometry, or unsupported accessibility claims.

## Independent follow-up

Profile and rebuild `IndoorWayfinding_AQ_SH_ECC_Revised.gdb` in an isolated output root, profile
`AdditionalData_Testing.gdb` without graph ingestion, reconcile the legacy/revised pathways, and
measure profile-specific unit-pair reachability. A later source-promotion ADR may supersede this
PoC's artifact selection after that evidence exists.