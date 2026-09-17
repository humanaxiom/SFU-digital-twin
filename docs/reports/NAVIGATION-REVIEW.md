# Navigation review and overhaul proposal

Status: review complete; the resulting implementation plan is accepted in [DT-024](../plans/DT-024.md) and [ADR-0017](../adr/0017-navigation-state-and-journey.md). Runtime overhaul is not implemented. Review of main
`b7ec7b6` and the locally deployed accepted artifacts at http://127.0.0.1:18007/.
Live audit evidence is under `build/navigation-review/`; source and artifacts were
not changed. Existing dirty deployment notes were preserved.

## Recommendation

Replace the navigation interaction model and state management as one coordinated
increment. Another dropdown synchronization patch will leave the underlying
conflicts between browsing a floor, selecting a room and following a route intact.
Retain the deterministic routing/guidance API and exact source level identities.
Handle graph/source improvements as a separate data increment.

## Findings and evidence

| Priority | Finding | Evidence and effect |
| --- | --- | --- |
| P1 | A route response overrides a newer floor choice | Docker Chromium held an AQ elevator route response, displayed ECC 3000 completely, then released it. The map jumped to AQ 2000 with no JS error. `race-results.json` and before/after screenshots reproduce this. |
| P1 | Floor selection silently changes buildings | From ECC 3000, choosing the global dropdown entry containing AQ 5000 changes the selected building to AQ. Floor options combine labels such as `ECC 3000 · AQ 3000 · SH 1000`. ECC disappears from the Building list on floors it does not share. `review.json`, states 03/04. |
| P1 | Route floor tabs and Next operate on different positions | On AQ2035.2 → AQ5046, click route floor AQ 5000: map displays AQ 5000, but instruction remains `Start near AQ2035.2` on AQ 2000. Next returns to AQ 2000, step 2. This is current preview behavior, but conflicts with the journey-tab affordance. `review.json`, states 09/11. |
| P2 | Destination discovery is a catalog dump | Both endpoint selects contain 1,017 rooms plus placeholder. AQ2035.2 creates destination groups of 237 mapped routes and 779 disconnected rooms under default. No search or building/floor narrowing. A group named Mapped routes actually lists destination rooms, not alternative paths. |
| P2 | Route editing has competing submit contracts | Every endpoint/profile change submits automatically, while Show directions remains an explicit submit button. Async availability replaces destination options twice, making the list unstable during editing. Existing tests frequently set all fields then submit directly. |
| P2 | Inspecting rooms can erase the route | `activateRouteEndpoint` clears a completed/failed route and its endpoints when another map room is clicked. A browse action is treated as starting a new route. Code-path finding; not separately pointer-reproduced in this audit. |
| P2 | Room-detail fetches can write stale state | `selectUnit` applies fetched details/status without checking current room/floor/request intent. Delayed old responses can overwrite newer context. Code-path finding; not dynamically reproduced here. |
| P2 | Map, floor and instruction controls lack a shared context | Browser screenshots show the old instruction retained while another journey floor is highlighted. On 390px mobile, current instruction and directions are below a large map; the explanation and recovery action are outside the initial viewport. |
| P2 | Floor changes are slow enough to amplify confusion | All 11 scene APIs succeed, but sequential internal-Docker samples took 553–1170ms before browser rendering. AQ5000 was 4,360,281 bytes; AQ6000 was 4,635,852 bytes. These are a single-run timing sample, not an SLA or controlled benchmark. |
| P2 | Connected is not the same as usable guidance | AQ stairs fixture returns a route but limited guidance because geometry and recorded lengths disagree. Destination availability tests graph connectivity, while guidance validates a computed path later. The UI must distinguish these outcomes. |

Primary code references (line positions at b7ec7b6):
- `packages/wayfinding/src/wayfinding/demo/static/app.js:486–522`: global-order
  Floor choices and aligned Building options; `1173–1178`: change handlers.
- `app.js:533–546,648–654`: floor selection/preview; `817–818,900,937`:
  route acceptance resets preview and selects the first step.
- `app.js:261–282,326–351`: room metadata and route endpoint coupling.
- `app.js:979–1067,1100–1117`: option rebuilding and implicit submission.
- `routing.py:342–459`: graph-based availability and route outcomes;
  `guidance.py:184–253,255–380`: validation and chronological visit/step contract.

The global-order dropdown is an explicitly retained ADR-0016 design, not simply a
regression against its specification. The proposed building-scoped floor picker
and journey-tab semantics require a new ADR superseding those interaction choices
and the relevant ADR-0012 preview behavior, including the old endpoint/profile-change-clears-route rule.

## What works, and what remains a data problem

All 11 floor scene endpoints and all four canonical route fixtures returned 200.
Direct ECC3000 and AQ3000 floor buttons worked in the audited sequence. The AQ5000
route-visit button also loaded the correct floor. Thus not every click fails;
context changes, races and conflicting interaction semantics explain concrete
ways floor navigation becomes unreliable or appears broken.

AQ2035.2 → AQ5046 has available elevator guidance with visits
AQ2000 → AQ3000 → AQ5000. The express transition legitimately skips AQ4000.
AQ1010 → AQ2103 has limited guidance, withholding unreliable distance/turn copy.
AQ6071 reaches only AQ6067; 1,015 destinations are disconnected under both profiles.
For AQ2035.2, counts are 237 connected/779 disconnected under default, and
221 connected/795 disconnected under elevator-only.

These are accepted legacy artifacts. Experimental topology improvements remain
unpromoted. A better interface cannot create missing floor/building connections,
verify door access, or certify wheelchair access. Elevator-only remains explicitly
stairs-excluded with unverified accessibility. Same-anchor is not a walking route.

## Proposed user experience

### 1. A stable building and floor hierarchy

Keep all recorded buildings available in the Building picker. Floor choices contain
only floors belonging to that building and display short labels such as `Floor 3000`.
Use exact `level_id` for state; use `vertical_order` only internally.
Changing a floor never changes the building. Building change selects a valid floor
with explicit labeling, without assuming aligned levels are physically connected.
A building card offers one obvious Open floor action, including for its already
selected floor; reselecting a native select value must not be the only entry path.

### 2. Searchable From and To, with a deliberate route request

Replace giant native room dropdowns with accessible searchable comboboxes.
Result: primary room code/name, secondary building and floor. Match room code and
available room labels; do not invent aliases or location data. Offer building/floor
filters when needed. Preserve exact selected room identities while results change.

Endpoint changes edit a draft. One primary Preview route button commits it; editing
shows `Route changes not applied` and retains the previous route until replacement
succeeds. Label the displayed map with its committed From/To/profile so an old stairs route cannot be mistaken for a newly drafted Elevator only route. A failed replacement retains that labeled route and explicitly identifies the failed draft. Keep Swap as a draft operation. Profile labels: `Stairs or elevators` and
`Elevator only`, with the existing qualification. Never label the latter accessible.

For destination results, prefer connected matches and show `No mapped connection`
only for disconnected outcomes. Same-anchor, endpoint-unavailable, availability-pending and availability-error each retain distinct labels; unknown availability is not disconnected. Keep disconnected results discoverable and
explain why a request cannot succeed. Replace Mapped routes with Connected
destinations: this is destination discovery, not a list of alternate paths.
Do not promise good guidance before a route is computed and validated.

### 3. One route journey, synchronized with its map

A successful route opens a chronological journey with explicit floor and transition
entries. For the tested fixture:

`AQ 2000 → elevator → AQ 3000 → elevator → AQ 5000`

Clicking a route floor entry selects the first instruction of that visit, updates
the map, highlights that visit and updates Next/Previous together. Repeated visits
to the same floor keep distinct visit IDs. Departure/arrival are explicit, e.g.
`Elevator: AQ 3000 → AQ 5000` and `View arrival on AQ 5000`.
Next advances exactly one instruction and automatically changes floor when needed.
Do not invent a walking segment on an express elevator's skipped level.

Manual map browsing uses the building-scoped floor control. While browsing away
from the active route step, display a persistent `Exploring AQ 4000 · Return to
route` strip beside the map. Route Next/Previous are replaced by Return to route
in this mode; there is no hidden old step that Next unexpectedly follows.

A floor load visibly names both requested and displayed floors until it completes.
Failure retains and labels the last good map, with Retry; the control must not imply
that an old scene belongs to the requested floor.

### 4. Room inspection is separate from endpoint editing

A map room click opens a small room summary with Start here and Directions here.
It does not replace endpoints or clear an existing route. Those explicit actions
edit the route draft. Clear route clears route/steps but preserves the inspected
building, floor and camera.

### 5. Map-first display with instructions always reachable

Desktop: compact endpoint search and journey panel beside a map; persistent current
instruction and transition action beside the map rather than beneath a long list.
Mobile: compact endpoint summary, map, and a persistent bottom instruction panel;
expand to the full chronological journey. Keep controls above the fold, with touch
sizes, visible focus, loading announcements and reduced-motion support.

Draw current-floor route as the main line, selected step as an accent, and named
origin/destination/transition markers. Use screen-consistent marker sizes so close
zoom does not create oversized landmarks. Retain exact source geometry; display
limited/unavailable guidance honestly instead of visually smoothing bad geometry.

## State and request architecture

Use one navigation state model as the authority, not DOM select values:
- context: campus, building, floor exploration, or route;
- inspected building; requested and displayed exact floor IDs; scene load status;
- selected room independently from draft From/To/profile;
- committed route and its request key;
- selected visit/step and route-following versus exploration mode;
- per-floor camera, scene cache and explicit error state.

All user actions enter a small transition/reducer layer. Derived views render the
same state. Request completion must match both its resource key and current user
intent. Abort obsolete requests and still validate results on receipt. A late
route can be stored without navigating away from a newer floor choice. A room
response cannot change another floor's status or an unrelated selection.

Cache scene responses by artifact hash plus exact level ID, deduplicate concurrent
loads and lazily preload adjacent route visits after the current scene settles.
Measure JSON transfer, parsing and SVG render separately. Consider static-scene
precomputation/compression only after measurement; do not simplify authoritative
routing geometry as a performance shortcut.

## Delivery order and acceptance

1. Capture regression tests for the reproduced race, silent building change and
   floor-tab/Next mismatch. Agree the new interaction ADR and state transitions.
2. Replace floor/context state and request ownership; implement stable building-
   scoped floors and atomic map/loading/error behavior.
3. Introduce searchable endpoints and draft/commit flow, separating room inspection.
4. Implement synchronized journey/transition controls and responsive instruction
   layout. Add scene caching and measure its effect.
5. Run fresh Docker gates and task-based browser/API review on the assembled app.
   Review topology/source promotion independently; it is not hidden inside this UI work.

Required acceptance scenarios:
- Every building and all 11 recorded floors by pointer and keyboard; no building
  disappears and no floor selection silently changes building.
- Open the already-selected floor from Campus/Building; return to campus and back.
- Search exact room and partial code, filter results, select both endpoints, Swap,
  edit profile, commit once, clear, inspect rooms without losing a route.
- Available multi-floor elevator route, stairs with limited guidance, disconnected,
  same-anchor and unavailable endpoint outcomes, with clear recovery.
- Every visit and transition phase; express skip; repeated-floor visit; next/back
  remain consistent with visible instruction/map; explore and return to route.
- Slow/out-of-order scene, route, availability and room responses; newest deliberate
  user context wins. Scene failure/retry preserves a correctly labeled old map.
- Desktop, 390px mobile and 320px; keyboard-only and focus/announcement checks;
  no manually opening hidden panels or setting all route fields as a test shortcut.
- Browser actions assert displayed building/floor/step/route identity together.
  Existing geometry/API fixtures remain useful but are not usability acceptance.

## Verification scope and reproducibility

Fresh Docker read-only application/browser runs exercised the deployed demo during
this review. Audit scripts are reproducible local evidence, not production tests.
`audit.cjs` uses actual CDP mouse clicks for building, floor-visit and Next buttons;
select changes use real application change handlers via DOM dispatch. Screenshots
were visually inspected. This is not an exhaustive OS-native dropdown/accessibility
or physical LAN test. No full test suite was rerun and no fix is claimed delivered.

- `build/navigation-review/audit.cjs`, `review.json`, numbered PNGs: sequential
  endpoint selection, floor/context behavior, desktop/mobile and Next reproduction.
- `build/navigation-review/race-audit.cjs`, `race-results.json`, race PNGs:
  deliberately delayed route response after a completed manual floor change.
- `build/navigation-review/backend-audit.py`, `backend-audit.json`: 11 scenes,
  four routes, option counts, timing, response sizes and artifact identities.

Browser runner: repository-pinned Playwright digest
`sha256:7dbbf924428aad5c87a5a3a5bc38f23e110cb1f5427fbbc7dbc3231014a4b0db`,
sharing `sfudt-wayfinding-18000-demo-1` network namespace, target localhost:8080.
Backend helper uses the local image recorded in HANDOFF; no raw sources accessed.
Local evidence is intentionally ignored by Git; preserve it with the review if shared.
