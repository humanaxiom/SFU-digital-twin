# 12. Structured guidance, floor previews and ordinary-language directions

DT-024 planning scope note (2026-09-17): [ADR-0017](0017-navigation-state-and-journey.md) supersedes the client journey-visit preview semantics and endpoint/profile-edit or failed-replacement clearing rules for the planned navigation overhaul. Its draft/committed route and exploration/return contracts apply to that implementation. Guidance geometry, validation and other requirements below remain applicable. The historical runtime described here has not yet been replaced.

Status: accepted for DT-018 implementation
Date: 2026-09-11

## Context and scope

The user authorized DT-018 after identifying unclear floor changes, GIS terminology
and the absence of selected-step highlighting. The request preserves deterministic
routing, source immutability and fresh Docker end-to-end verification.

ADR-0008 sections 5–6 prescribe technical instruction/title text and prominent
attachment measurements. This decision supersedes those presentation requirements:
primary UI text uses supplied room/floor labels and short ordinary-language wording;
technical IDs, legacy instructions, exact attachment distances and provenance remain
in route details. A visible concise room-to-route limitation and elevator-only
qualification remain required. Plain failures retain their exact codes in details.

Shortest-path selection, graph weights, original response fields, artifact hashes,
reachability, source choice and profiles do not change. DT-017's geometry correction
and production promotion remain separate. The GIS request is recorded in
`docs/requests/GIS-DATA-NEEDED.md`; this implementation does not send it externally.

## Additive guidance contract

Successful routes include `guidance` alongside unchanged legacy `steps`, `edges`
and `geometries`. `guidance.version` is `dt018-guidance-v1`. IDs are unique within
that response; selection also belongs to its route generation, never a later route.

| Field | Meaning |
| --- | --- |
| `status` | `available`, `limited`, or `unavailable`; availability is arithmetic/presentation validation, not physical route certification |
| `warnings` | Visible explanations of limitations relevant to this guidance |
| `distance_m` | Validated authoritative route distance, or null when limited |
| `visits` | Chronological floor visits, including repeated visits |
| `steps` | Ordered departure, walking, transition phase and arrival instructions |
| `geometries` | Exact walking spans; no invented room connectors or projected shafts |
| `markers` | Approximate endpoints and directed stair/elevator landing points |
| `transitions` | One event per traversed stairs/elevator edge occurrence |

Visit: `{visit_id, level_id, label, step_ids}`.

Step: `{step_id, kind, action, instruction, level_id, visit_id, geometry_ids,
marker_ids, spans, distance_m, transition_id, phase}`. Kinds are `depart`, `walk`,
`transition`, `arrive`. Actions are `start`, `continue`, `bear_left`, `bear_right`,
`turn_left`, `turn_right`, `u_turn_left`, `u_turn_right`, `take_stairs`, `take_elevator`,
`exit_transition`, `arrive`. Phase is `departure`, `arrival`, or null.

Span: `{edge_occurrence, start_segment, end_segment}` using directed half-open
segment indices `[start_segment,end_segment)`; its original coordinates are
`coords[start_segment:end_segment+1]`. Across walking steps, spans partition the
route's walking segments without gaps or overlap. Shared boundary vertices are
expected; duplicated or fabricated segments are not.

Geometry: `{geometry_id, level_id, edge_occurrence, start_segment, end_segment,
geometry:{type:"LineString",coordinates:XY[]}}`. A step may reference several
geometries across edges, or a portion of one contracted edge. Neither array
position, spatial proximity nor an edge key alone establishes correspondence.

Marker: `{marker_id, level_id, kind, label, coordinates:XY}`. Kinds are `origin`,
`destination`, `stairs`, `elevator`.

Transition: `{transition_id, edge_occurrence, mode, from_level_id, to_level_id,
from_label, to_label, from_visit_id, to_visit_id, departure_marker_id,
arrival_marker_id, distance_m}`. Its two phase steps have null distance; the event
owns the distance exactly once. Zero-XY elevator movement remains marker-visible.

## Floors and transitions

Labels come from the verified artifact's facility code and level short name, and
room labels from the endpoint catalog. Missing labels use “Floor not recorded” or
“Room not recorded”, not parsed technical IDs. Floor identity must agree with
directed transition endpoints. Ambiguity produces limited guidance, never a
lexicographic guess. Up/down is shown only from validated vertical-order comparison.

Keep one active floor plan. A journey shows ordered visits and intervening
transitions. Do not sort/deduplicate visits or create stops on intermediate floors
of an express elevator. Draw departure/arrival markers at actual directed geometry
endpoints on their respective floors. Preserve full transition geometry in legacy
evidence, but do not draw its shaft projection as a horizontal walking path.

Before assigning landing cues or maneuvers, verify each directed geometry's first
and last XY coordinates against the actual source/target node XY. Allow at most
0.01m Euclidean difference for the 1cm snapping grid; never compare node
`vertical_order` with geometry elevation. Shifted or reversed geometry beyond
this tolerance makes guidance unavailable, with no floor-assigned landing markers.
Keep the original route geometry in diagnostics. This closes an endpoint alignment
gap found by independent implementation review.

## Walking instructions and arithmetic

Use deterministic action templates. Classify significant native XY direction
changes using 15°, 45° and 135° thresholds for continue/bear/turn/U-turn. Direction
segments shorter than 0.5m do not independently introduce a turn; their coordinates
and length remain represented. Compare successive significant legs and reset
heading across a transition. Detect bends inside contracted polylines as well as
between edges; group uninterrupted same-floor continuation spans.

Require finite native XYZ geometry and valid positive edge weights. Compare the
sum of native 3D segment lengths with each edge's authoritative `length_3d` using
tolerance `max(0.05m, 0.005 * length_3d)`. Only within that tolerance may segment
lengths be normalized proportionally to preserve the authoritative edge total.
This is a documented rounding/measurement reconciliation, not permission to scale
across materially inconsistent geometry. Never derive partial walking distances
from the public 2D projection. Human rounding follows aggregation.

If any edge fails this check, the entire route's guidance is `limited`: numeric
guidance distances are null and walking text does not assert turn/straight
certainty. Preserve exact span highlighting and show a visible review warning.
Legacy evidence and its recorded route distance remain available in details.
This explicitly covers the inherited multipart defect without silently repairing
it or certifying its shape. No corridor/door/landmark names, travel times, access
facts or accessibility certification may be invented.

## Client interaction and presentation

One selection operation connects current route generation, step ID, transition
phase and displayed visit. It selects the required floor and exact geometry/marker
references. Same-floor selection need not fetch the scene again. Preserve latest
scene/route request guards; Clear, failure, endpoint/profile change and replacement
remove old highlights. A late response must not restore them or move the user back.

Main route: muted coral. Selected walking span: blue, thicker with a contrasting
halo, direction cue and matching step number. Transition and endpoint steps select
markers. Use `aria-current="step"`, visible focus, keyboard activation and
Previous/Next. Floor preview preserves selected step; show where it belongs and
offer return to that step. Selection never claims actual location or completed travel.

Render SVG in one scene-local coordinate system to avoid stroke precision loss with
large EPSG:26910 values. Expose the scene origin and apply the same subtraction to
floor/room/detail paths, route spans, markers, arrows and the viewBox. Keep native
API geometry untouched; adding the origin back must reconstruct every native XY
coordinate exactly. Do not round, simplify or bridge gaps as a rendering repair.

Compact desktop header and route-focused panels leave map and directions visible
together. Mobile puts current instruction and floor controls next to the map, with
the full list expandable. Fit controls distinguish selected span, route on this
floor and whole floor. Avoid forced animated panning and nested scroll traps.

Bound guidance expansion to 50,000 directed segments and 2,000 instructions. Beyond
either cap, return `unavailable`, empty presentation collections, null distance and
an explicit capacity warning; retain the original route evidence. Never truncate
a presented route while claiming complete coverage or silently substitute legacy
GIS instructions into the main UI.

## Verification

Demonstrate RED before implementation. Synthetic tests cover span partition,
within-edge maneuvers, parallel/repeated occurrences, reversed/express transitions,
zero-edge routes, native-distance mismatch, missing metadata and race conditions.
Preserve canonical legacy route evidence while independently asserting new guidance.

Before declaring green, run full Docker tests/coverage, lint, types, artifact QA,
and fresh browser/API E2E. Assert exact selected coordinates and current floor,
not merely changed CSS. Include the screenshot route and reverse, four canonical
fixtures, both profiles, ECC browsing/routing evidence, pointer/keyboard controls,
320px/mobile/desktop, stale responses and failed routes. Inspect screenshots.
Any changed artifact additionally requires source-to-candidate and candidate-backed
browser verification. A local-image pass does not certify GHCR, CI or physical LAN.
