# 17. Navigation state, route drafts and synchronized journeys

Status: accepted for DT-024 implementation planning; runtime not implemented.
Date: 2026-09-17.

## Scope and supersession

The user authorized the navigation plan and architecture update following the
[review](../reports/NAVIGATION-REVIEW.md). This decision defines the implementation
contract for [DT-024](../plans/DT-024.md). Acceptance of this document does not claim
that the deployed application implements it or has passed its acceptance gates.

For DT-024, this decision supersedes only these client interaction choices:

- ADR-0016's global-order Floor picker and aligned-building filtering, with a
  stable Building picker and floors scoped to the selected exact facility; its retained global-order building-selection fallback is replaced by the per-building remembered-level/order-0/first-level fallback below.
- ADR-0012's route-visit floor preview retaining a different selected instruction,
  with visit selection that selects its first instruction. Independent browsing
  remains possible through the exploration controls described below.
- ADR-0012's removal of the old route on every endpoint/profile change or failed
  replacement, with separately identified draft and committed route state.
- ADR-0013's native destination catalog presentation, with searchable destination
  discovery preserving its full outcome semantics and unsupported selections. Its connected-destination direction actions (including the DT-022 clarification) now edit the draft and require Preview route, rather than immediately requesting a route.

The earlier documents remain historical descriptions of the current runtime until
DT-024 is implemented. Their other requirements remain applicable. In particular,
ADR-0012 guidance geometry, chronological visits, validation and limitations;
ADR-0013 directed availability; ADR-0014 camera semantics; and ADR-0016 artifact-only
campus coverage remain authoritative. No HTTP API, guidance schema, source,
artifact, graph topology, route algorithm or promotion change is authorized here.

## Building and floor identity

Keep every recorded building discoverable in the Building picker regardless of
the displayed floor. Populate Floor using only the selected facility's levels,
keyed by exact `level_id`, with its recorded local label. A floor choice must not
silently select another building. `vertical_order` remains an internal alignment
identity; it must not serve as the user's cross-building floor-selection value.

On explicit building selection, retain the last inspected exact level for that
building when valid; otherwise use its recorded order-0 level, then its first
level in deterministic artifact order. Label the selected floor. This fallback
neither asserts an entrance nor implies a physical connection to another building.
An overview-only building retains its identity with an empty disabled Floor
control and explicit coverage text. Building inspection does not edit endpoints.

Provide an Open floor action that works for the already-selected floor. Native
select change events cannot be the sole way to enter a floor from Building context.
Opening a route step uses that step's exact facility/level identity and synchronizes
the visible controls without hiding other recorded buildings from discovery.

## Authoritative state and effects

Use one explicit navigation state model, updated through named user actions and
request-completion actions. Render controls from state; do not recover authoritative
identity by reading mutable DOM select values. Represent at least:

- context: campus, building inspection, floor exploration, or route following;
- inspected facility, requested floor, displayed floor and scene load/error status;
- inspected room and its independent detail-request status;
- draft origin/destination/profile and edit revision;
- submitted route-request snapshot/key, pending/error status, and committed route;
- committed route identity, selected visit/step and exploration/return target;
- artifact-scoped scene cache and camera state for each exact floor/context.

Keep requested and displayed floors separate during loading. The map label must
identify the actually displayed floor; the loading message names the requested
floor. On failure, retain and label the last good scene and offer Retry. With no
previous scene, show an explicit empty/error state. Never present an old scene as
belonging to the requested level. Instruction selection, selected geometry and
navigation controls must likewise distinguish a pending target from the displayed
scene; do not expose a new instruction as successfully mapped before its scene is
ready. Disable advancing the pending selection or otherwise serialize advancement
through the same explicit transition contract.

Use separate resource/request identities and user-navigation intent revisions.
Request completion must match the applicable resource key and request revision
before updating state. Abort obsolete work when possible, but still validate every
completion; abort alone is not a stale-response guard. Route acceptance and map
navigation are separate effects. A valid response to the latest submitted route
may be retained while the user explores a newer floor, but must not force the map
back to the route. Show an explicit Return to route action instead. Replaced or
cleared route requests cannot restore a route. A late room response cannot replace
a newer room selection, write another floor's status, or move focus to a stale room.

Availability belongs to the draft origin and profile, independently of the displayed
committed route. Associate responses with that exact draft request key. Scene,
route, availability and room completion guards must work across all input paths,
including pointer, keyboard, assistant, Swap, Clear and campus navigation.

## Draft editing and committed route identity

From and To are accessible searchable comboboxes over the existing room catalog.
Search recorded codes/names and offer building/floor filtering; preserve exact unit
IDs independently of query text or filtered results. Do not invent aliases or infer
new room identities. Results identify the room, building and floor.

Endpoint, profile, explicit map endpoint actions and Swap edit the draft; they do
not submit routes automatically. One primary Preview route action submits an
immutable snapshot of the draft. Assistant directions must use the same state and
explicit request contract, presenting resolved draft endpoints for preview rather
than silently bypassing confirmation of the selected identities.

Retain the last committed route during editing and while a replacement is pending.
Show Route changes not applied when draft and committed values differ. Label the
map and directions with the committed From, To and profile, distinct from the draft
controls and pending request. In particular, an old stairs-capable route must never
appear to be the result of a newly drafted Elevator only selection. Display the
stairs-excluded/unverified-accessibility qualification for the committed elevator
profile; draft profile help must not relabel the committed route.

A successful current request commits its exact submitted snapshot, even if later
draft edits differ; retain those newer edits and their unapplied status. A failed
replacement leaves the previous labeled committed route intact and explicitly
identifies the failed request's endpoints/profile and reason. It must not imply
that the displayed prior route failed or that the failed draft is displayed.
Success here means an authoritative successful route response; limited or
unavailable guidance remains explicitly qualified and must not borrow instructions
from the old committed route. Old highlights disappear upon actual replacement.

Clear route cancels pending route work and clears committed route, instructions,
endpoint draft and availability state. Preserve inspected facility/floor, selected
room and deliberate camera. Late responses cannot undo Clear.

## Destination outcomes

Connected destinations are rooms reachable in the draft origin/profile graph,
not alternative paths or promises of validated guidance. Prioritize connected
matches without silently substituting a selected destination or profile. Preserve
discoverability of unsupported rooms and allow explicit requests with explanations.
Use distinct labels and state for:

| Outcome | Presentation meaning |
| --- | --- |
| `connected` | Connected destination; actual route and guidance still require validation |
| `same_anchor` | Same route point; no walking path is represented |
| `disconnected` | No mapped connection |
| `endpoint_unavailable` | No mapped route point |
| availability pending | Connection check in progress; outcome not yet known |
| availability error | Connection check unavailable; outcome unknown, manual request remains possible |

Preserve route-level available, limited and unavailable guidance separately from
these availability outcomes. Limited distances/turns cannot be restored by UI
copy, smoothing or inferred geometry. Elevator only excludes stairs; it does not
claim verified wheelchair access.

## Journey selection and independent exploration

Keep chronological visit IDs, including repeated visits to the same exact floor.
Selecting a journey floor entry selects its first instruction, enters route-following
mode, requests its exact floor, and synchronizes the visit, selected span/markers,
current instruction and Next/Previous. A visit without an eligible instruction is
explicitly unavailable for this action; do not select an instruction from another
visit as a substitute. Transition departure/arrival actions select the matching
phase instruction in the same committed route occurrence.

Next and Previous advance one instruction in committed route order, changing floor
when required. Express elevators have no fabricated stop or walking path on skipped
floors. Route/visit/step identities always belong to the current committed route;
identically named step IDs from an old response cannot select a new route's step.

Manual floor/building browsing enters exploration mode and preserves the committed
step as a return target. Show Exploring <displayed floor> and Return to route beside
the map. Replace route Next/Previous with Return to route while exploring, so no
hidden old instruction controls the next floor change. Return to route restores
the selected step's exact floor and instruction; selecting a journey entry instead
returns at that visit's first instruction. Campus exploration must expose a clear
return action when a committed route exists. Exploration does not claim movement,
completion or live location.

A map room click inspects that room, with explicit Start here and Directions here
actions that edit the draft. Inspection alone must not clear or replace route
endpoints, select the next endpoint implicitly, or recalculate a route.

## Camera, performance and accessible presentation

Retain ADR-0014's explicit zoom and route/floor fits, exact scene-local coordinates
and meaningful route context for point-only steps. Store deliberate camera state
by exact floor/context, independently of draft editing and committed instruction.
A newly selected route instruction may explicitly establish its appropriate frame.
Keep marker sizes readable in screen space without changing native geometry.

Key scene caches by loaded artifact SHA-256 and exact `level_id`; clear or namespace
them on artifact change. Deduplicate concurrent scene requests, bound cache size,
and lazily prefetch adjacent route visits after the current scene settles. A
prefetch completion updates only the cache, never navigation or loading status.
If availability or route results are cached, include exact endpoint/profile and
all applicable loaded artifact identities; scene identity alone is insufficient
for graph-dependent results. Measure transfer, parse and SVG-render time separately
before deciding on compression or precomputation. Do not simplify authoritative
routing geometry or admit raw-source reads as performance shortcuts.

Keep current instruction, displayed route identity and exploration/return state
adjacent to the map on desktop and persistently reachable on mobile. Expand the
full chronological list on demand. Require keyboard operation, visible focus,
proper combobox selection semantics, loading/error announcements, usable touch
sizes and reduced-motion support. A layout fitting the viewport is insufficient
if recovery actions or the current context are undiscoverable.

## Implementation and acceptance boundary

Follow DT-024's plan, RED evidence, implementation and fresh Docker validation.
Capture regressions for delayed route versus newer floor, building-scoped floor
selection, journey entry versus Next, and stale room details. Assert displayed
facility/floor, route identity and step together. Include every recorded floor,
already-selected Open floor, draft/committed profile disagreement, failed replacement,
Clear, same-anchor/unavailable/disconnected outcomes, limited guidance, repeated
visits, express transitions, exploration/return and out-of-order requests.

Exercise the actual pointer and keyboard workflows at desktop, mobile and 320px;
programmatically setting all endpoint fields and submitting once is not a substitute
for testing draft editing and search. Preserve exact API/geometry fixtures. Full
Docker gates, fresh browser/API E2E and independent review are required before
claiming the implementation delivered. Documentation acceptance does not certify
an implemented UI, source correctness, candidate promotion or physical LAN access.
