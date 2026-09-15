# 16. Three-building campus overview and measured coverage

Status: accepted for the bounded DT-023 Stage 0/1 implementation, 2026-09-11.

## Context and delivery boundary

DT-023 requests a Burnaby campus overview and routes between buildings. The trusted
local indoor artifacts describe only AQ, ECC and Strand Hall. The authoritative
complete facility inventory, classified outdoor pathways and authored indoor/outdoor
entrance joins are absent. A useful first increment can expose these three source
facilities without representing them as the entire campus or inventing routes.

This decision authorizes an artifact-only overview and separate directed room-pair
coverage audit. It does not complete all DT-023 Stage 0 exit conditions. The nine
exact endpoint candidates, AQ–Strand source component, multipart reconciliation and
GIS gates remain separate review work. Stage 2 verified interbuilding navigation,
Stage 3 outdoor journey guidance and Stage 4 campus expansion remain blocked by their
required source and contract decisions.

## Runtime overview contract

Add `GET /demo/v1/campus`, accepting no query parameters, with the following response:

```text
version: "campus-overview-v1"
crs: "EPSG:26910"
scope: "three-building-pilot"
campus_inventory_complete: false
bounds: [min_x, min_y, max_x, max_y] | null
facilities: [
  {
    facility_id, code, name,
    geometry: source Polygon/MultiPolygon | null,
    geometry_status: "available" | "unavailable",
    bounds: [min_x, min_y, max_x, max_y] | null,
    levels: [{level_id, facility_id, short_name, vertical_order}],
    coverage: "partial_indoor" | "overview_only",
    known_entrances: [],
    verified_building_destination: false,
    outdoor_routing: "unavailable"
  }
]
provenance: ArtifactRepository.provenance("facility_26910")
limitations: [explicit pilot and routing limitations]
```

Read only normalized `facility_26910` geometry/identity and `level_26910` metadata
from the same loaded GeoPackage. Use the existing artifact availability and hash
verification boundary, including routing-side lineage checks when routing is enabled.
The existing source-artifact SHA-256 identifies this derived view. Do not introduce
a new persisted build artifact, GeoPackage schema or ETL stage. Geometry is serialized
in its native metric CRS without simplification, inferred footprints or merged floor
plans; rendering uses its XY coordinates. Bounds use finite XY extrema, without
camera padding. Unusable, empty, nonpolygon or invalid geometry produces null geometry
and bounds and `geometry_status: "unavailable"`; retain the facility for discovery.
Global bounds cover only available geometries and are null if none are available.

Facility and level ordering is deterministic, following the existing repository
ordering. Include only each facility's real levels. `partial_indoor` means at least
one recorded level exists; it is a coverage description, not evidence of a usable
room endpoint or a connected path. Otherwise use `overview_only`. An empty entrance
array means no verified entrances are admitted, not that the building has no doors.
Both the payload and UI explicitly say the pilot contains three buildings and is
an incomplete campus inventory, with no verified outdoor routing or building
destinations. Preserve source names/codes; do not silently resolve ECC/EDB identity
disagreement. The provenance's facility-layer label names the principal view;
level metadata comes from the same identified artifact.

Overview availability is independent of routing capability and coverage. It never
performs a route search, reads raw GDBs, mutates artifacts or exposes graph objects.
Existing unknown-route, method, query-validation and artifact-failure conventions
remain applicable. Existing facilities, levels, scenes, room search, route options,
routes and assistant APIs remain unchanged.

## Separate measured coverage audit

Generate a versioned audit in Docker using checked-in tooling and the exact trusted
artifact set being evaluated. Record GeoPackage, contracted graph and stats hashes,
snapshot identity and whether that snapshot is accepted or an unpromoted candidate.
Do not mix accepted geometry with candidate reachability or import historical counts
as fresh evidence. This audit is not computed on overview requests.

Measure every ordered facility pair, including the diagonal, for both `default`
and `elevator_only`. Map endpoint facilities through exact recorded level IDs.
Enumerate ordered pairs of distinct catalog units: for distinct buildings the total
is `n_origin * n_destination`; on the diagonal it is `n * (n - 1)`. Classify each pair
exactly once:

- `endpoint_unavailable`: either endpoint is ineligible under the existing anchor
  contract, before applying any connectivity classification;
- `same_anchor`: two eligible units share the same anchor, including a profile
  isolated anchor; this represents no walking edge;
- `connected`: eligible distinct anchors have an exact directed path using the
  profile's allowed modes; and
- `disconnected`: eligible distinct anchors have no such directed path.

The four counts must sum to the ordered pair total. Directed traversal may be
cached per distinct anchor/profile; weak component equality alone is insufficient.
Never double unordered historical totals to stand in for a directed measurement.
Represent unavailable graph evidence explicitly rather than manufacturing zero
connectivity; a facility with no endpoint catalog has zero possible room pairs,
not a measured failed journey. Preserve directed asymmetry and profile differences.

If the audit supplies DT-023's summary labels, `mapped_route` means at least one
`connected` pair in the existing indoor graph only; `disconnected` means measured
eligible distinct-anchor pairs exist but none connect; `partial_source_coverage`
describes source coverage with only unavailable/same-anchor pairs; `unavailable`
means no endpoint catalog or no trusted graph measurement. Always retain counts
and the explicit graph-only meaning alongside a label. No label claims a verified
outdoor connection, portal, accessible route or success for every room pair.

## Client context

Selection-control clarification, 2026-09-14: footprint, search/list and keyboard
building selection synchronously select the exact facility and a recorded floor in
the top controls. Retain the current global `vertical_order` if that facility has
it; otherwise select its recorded order-0 level, then its first level in the existing
deterministic artifact ordering. This fallback does not identify a public entrance.
Keep the existing global-order floor options and aligned-building navigation for
indoor selections. An overview-only selection retains its facility in Building,
empties/disables Floor and displays the no-indoor-coverage message. Restore the
normal floor options when selecting an indoor building or an explicit route floor.
Control synchronization remains Building inspection: it neither requests a scene
or route nor changes room endpoints/profile. Explicit floor/step navigation opens
the exact recorded floor. Clearing or starting a route while inspecting a building
does not restore the controls from a hidden prior floor; successful guidance can
then explicitly select its floor. Newer building selections invalidate pending scene/route
responses before those responses can restore older controls or context.

Start in Campus context with the three source footprints and clear pilot disclosure.
Search and select buildings by source name/code alongside existing room discovery.
A building selection reveals its real floor choices and a Building context; floor
selection opens one exact floor scene. Buildings without levels stay discoverable
with an explicit lack-of-indoor-coverage message. Missing footprint geometry cannot
be replaced with a centroid, inferred outline or arbitrary campus location.

Campus, Building and Floor controls state which context is visible. Campus reset
frames all available buildings; building reset frames its footprint; floor/route
reset retains ADR-0014 semantics. Preserve deliberate camera state on redraw within
the same context. Keep zoom/reset usable on desktop, mobile and 320 px. Selecting
a footprint is inspection, never an origin/destination attachment. Existing room
route actions, profile behavior and guidance remain available and switch to their
actual floor context; returning to Campus must not paint floor paths as outdoor
routes. Invalidate stale scene/route/availability results across context changes.

## Preserved invariants and future decisions

ADR-0007's artifact-only security boundary and ADR-0008/0009's approximate anchors,
profile limitations and measured connectivity remain in force. ADR-0012/0013/0014
continue to govern indoor guidance, directed availability and route framing.
ADR-0015 remains opt-in and unpromoted. Accepted artifacts and running-demo artifact
selection remain frozen until a separately reviewed promotion decision.

Do not admit the 141 unassigned revised pathways, supplemental entrances/doors/ramps,
public map geometry, inferred crossings or nearby endpoints. Outdoor grade/node
identity, stable verified portals, explicit building/entrance endpoint kinds and a
versioned indoor/outdoor journey contract require later decisions backed by GIS
evidence. `elevator_only` continues to exclude stairs without claiming verified
accessibility. Geometry visibility never authorizes traversal.

## Verification

Require relevant RED evidence before implementation. Docker tests cover exact source
geometry/provenance, deterministic bounds and ordering, absent/invalid geometry,
overview-only buildings, endpoint/method/query behavior and directed audit arithmetic
including asymmetric, same-anchor and unavailable fixtures. Browser/API E2E on the
final assembled stack covers initial overview, name/code search, building/floor
selection, context/camera transitions, stale responses, canonical room routes and
desktop/mobile/320 px containment. Exercise the separately identified candidate
without promotion and record its artifact hashes; accepted-artifact checks alone
cannot certify candidate behavior. Full required gates and independent integration
review precede any scoped delivery judgment. Record unresolved full-campus and
outdoor scenarios as blocked rather than passing them by omission.
