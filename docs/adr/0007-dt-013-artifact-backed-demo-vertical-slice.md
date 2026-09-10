# 7. DT-013 artifact-backed demo vertical slice

Status: accepted
Date: 2026-09-09

## Context

DT-013 must provide Facilities, CIO, and AI-policy stakeholders with a visual, clickable UI and a
conversational interaction backed by real SFU indoor data. A static mockup or fabricated response
would not demonstrate the Phase 1 artifact and is not acceptable.

The repository currently contains only Phase 1 capabilities. The available runtime input is
`build/wayfinding.gpkg`, produced from the read-only source geodatabase. It contains the normalized
dual-CRS facility, level, unit, landmark, detail, and door layers selected by ADR-0003. There is no
implemented routing service, unit-to-network connector catalog, FTS search index, tile service,
FastAPI application, MapLibre client, assistant orchestrator, or LLM integration. The target
architecture and delivery order remain those in [the system design](../02-system-design.md),
especially sections 2, 7, 8, 9, and 11.

The existing build image already contains Python, GDAL, and the `osgeo` bindings. ADR-0006 requires
normal execution to use that prebuilt image without runtime installation and separates the
artifact-only capability from the source-capable ETL service. The current Compose image digest is
still a publication placeholder, so DT-013 may use a locally built image from the checked-in
`infra/Dockerfile.build` only through the existing explicit local-image launcher path; it must not
weaken digest pinning for normal execution or install dependencies at startup.

The data imposes several honesty constraints:

- `VERTICAL_ORDER`, not `LEVEL_NUMBER`, is the cross-facility floor alignment key
  ([data findings section 3](../01-data-findings.md#3-facilities-and-levels)).
- The normalized `unit` layers contain only the 1,017 source records marked `SEARCHABLE='Y'`; the
  demo must not recover or expose the 193 excluded units from raw layers
  ([data findings section 4](../01-data-findings.md#4-units-the-destination-catalogue)).
- Unit accessibility metadata describes a destination and carries source provenance. It says
  nothing about whether a person can reach that destination.
- No route may be claimed without deterministic routing over the contracted graph. The dataset has
  no path width, slope, surface, powered-door, or door-width data, and no runtime routing component
  exists ([data findings gaps G1-G3](../01-data-findings.md#8-data-gaps-that-constrain-the-design)).
- The LLM may not compute geometry, routes, distances, or accessibility claims. DT-013 has no LLM
  at all, so presenting its conversational panel as AI-generated would also misrepresent the demo.

The decision must therefore provide a thin real vertical slice without presenting partial Phase 1
capabilities as the completed Phase 4-6 product.

## Decision

### 1. Add an artifact-only demo component

DT-013 will add one containerized `demo` component based on the same checked-in build image as the
Phase 1 artifact service. It will:

- run a Python standard-library HTTP server using the already installed `osgeo.ogr` bindings;
- mount `build/wayfinding.gpkg` read-only and receive no source-GDB mount;
- serve checked-in static HTML, CSS, and JavaScript from an explicit static-file allowlist; and
- bind to loopback by default, with a launcher-selected host port.

The component installs nothing when it starts, makes no network requests, uses no host Python or
GDAL, and writes neither the GeoPackage nor the source geodatabase. Startup opens the GeoPackage in
read-only mode, verifies all required normalized layers, computes the artifact SHA-256, and fails
closed if the artifact or schema is missing. Each request uses read-only OGR access. Derived scene
responses may be cached in process memory but are never written back to the artifact.

This is a local stakeholder demonstration service, not a production deployment. It has no database,
background worker, server-side session state, package manager, or external asset host.

### 2. Define a separate, intentionally narrow demo API

The JSON boundary is namespaced under `/demo/v1`; it is not the future `/v1` contract from system
design section 7 and carries no forward-compatibility guarantee.

| Method and path | Contract |
| --- | --- |
| `GET /demo/v1/health` | Service state, artifact SHA-256, required-layer validation, and build limitations |
| `GET /demo/v1/facilities` | The three normalized facilities and their identifiers/names |
| `GET /demo/v1/levels?facility_id=` | Levels ordered by `vertical_order`, then facility and label |
| `GET /demo/v1/levels/{level_id}/scene` | Level outline, public units, detail linework, and landmarks for one real level |
| `GET /demo/v1/units/{unit_id}` | One normalized public unit and its source-derived attributes/provenance |
| `POST /demo/v1/assistant` | One bounded deterministic query and structured evidence; no session or model call |

Unknown routes and unsupported methods return JSON `404` and `405` responses. Validation failures
return `400`; oversized requests return `413`; an unavailable or invalid artifact returns `503`.
All JSON responses identify the artifact hash and normalized source layer, either directly or in a
common `provenance` object. They also carry a stable limitations identifier that the client can
expand into the disclosures in section 5.

The service does not expose `/search`, `/route`, `/nearest`, `/assistant` under the future `/v1`
namespace, tiles, graph objects, raw layers, arbitrary SQL, filesystem paths, or a general-purpose
feature-query endpoint. This keeps the demo from accidentally becoming an undocumented production
API.

### 3. Perform only deterministic display transformations

OGR reads these normalized EPSG:26910 layers:

- `facility_26910` and `level_26910` for navigation and floor outlines;
- `unit_26910` for clickable public room polygons and unit facts;
- `detail_26910` for floor linework; and
- `landmark_26910` for real amenity points.

The scene endpoint filters records by exact `level_id`, selects an explicit field allowlist, and
serializes geometry as GeoJSON-like coordinate arrays in EPSG:26910. The browser derives a level
view box from the returned level extent and applies only an SVG Y-axis inversion. No distance,
bearing, topology, route, proximity, or accessibility computation occurs. Geometry remains in the
native metric CRS; the demo does not perform calculations in EPSG:4326.

The API uses source-stable identifiers unchanged. Levels are grouped across facilities by
`vertical_order`, while facility-specific labels remain visible. Unit details expose only fields
already present in the normalized public unit layer. `accessible=null` is rendered as unknown, and
`accessible=true` is rendered only as source-tagged destination metadata together with
`verified_by` and `verified_date`; it is never used to claim route accessibility.

### 4. Use a static, clickable SVG floor explorer

The first screen is the working explorer, not a landing page. Checked-in HTML, CSS, and JavaScript
render:

- a facility selector and a floor control ordered by `vertical_order`;
- an SVG floor view containing real level, unit, detail, and landmark geometry;
- keyboard- and pointer-selectable unit polygons and landmarks;
- a details region populated from `GET /demo/v1/units/{unit_id}`; and
- the deterministic conversational panel defined below.

The client uses no framework, CDN, web font, remote icon, analytics script, map tile, or network
dependency. It uses semantic controls, visible focus, sufficient contrast, a persistent text
alternative for the selected feature, status announcements for asynchronous updates, and keyboard
operation that does not require manipulating the SVG. These are implementation requirements, not
a claim of WCAG certification; keyboard, semantics, and contrast must be tested, and residual
limitations disclosed.

The floor explorer is intentionally SVG rather than MapLibre. MapLibre and PMTiles are target
Phase 5 components, but neither dependency nor the PMTiles artifact exists. Canvas was considered
and rejected for this slice because SVG provides direct focus and accessible naming for the small
set of interactive unit and landmark features.

### 5. Make the conversational panel a disclosed deterministic data assistant

The panel is labelled **Deterministic data assistant** and states that it is not an LLM or a
general-purpose chatbot. `POST /demo/v1/assistant` accepts a UTF-8 message of at most 500 characters
plus optional current `facility_id` and `level_id` context. It returns deterministic text,
structured entity references that the UI can select, and an `evidence` array naming the artifact
hash, layer, feature identifier, and fields used.

The initial intent grammar is closed and testable. It supports:

- listing facilities and levels;
- resolving an exact normalized room identifier, with conservative case and whitespace
  normalization;
- bounded literal matching of public room names/identifiers and use types, with an explicit result
  cap and deterministic ordering;
- listing landmark categories or landmarks on the selected level; and
- explaining the artifact provenance and known demo limitations.

This bounded lookup is local OGR attribute matching, not the FTS5 search and ranking service from
system design section 6. It performs no fuzzy, semantic, vector, proximity, nearest-place, or
network-distance ranking. Ambiguous matches are returned as choices instead of guessed.

The assistant refuses requests for routes, directions, closest/nearest places, travel distance or
time, live occupancy, opening status, accessibility of a path, and facts outside the artifact. A
routing refusal states: "Routing is not available in this demo because no routing service or unit
connectors have been implemented." Mobility-related requests additionally state that no path can
be certified from this demo and list the unverified path properties: `door_width`, `path_width`,
`slope`, `powered_doors`, and `surface`. It must not silently answer such requests with straight-line
geometry or a plausible-sounding sequence of rooms.

Assistant responses are functions of only the request, optional map context, and current artifact.
There is no prompt, model, token stream, outbound call, transcript persistence, user profiling, or
server-side conversation memory. The UI discloses these facts for AI-policy review.

### 6. Apply a localhost, read-only security boundary

The demo's trust boundary is one local browser talking to a loopback-only container port. Within
that boundary:

- request targets are parsed, normalized, and matched against exact API routes or an exact static
  allowlist; directory traversal and symlink escape are rejected;
- request bodies, query values, and result counts have fixed limits; JSON types and identifiers are
  validated before use;
- user input is never interpolated into SQL or OGR attribute-filter expressions;
- displayed data and assistant text are inserted with DOM text APIs, never `innerHTML`;
- responses set a restrictive self-only Content Security Policy, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, and deny framing;
- no permissive CORS header is emitted, and state-changing HTTP methods are unsupported; and
- errors do not reveal host paths, stack traces, environment variables, or raw queries.

There is no authentication or TLS because the service is not remotely exposed. Any shared-host,
campus-network, or internet deployment requires a separate deployment ADR covering authentication,
authorization, TLS, reverse-proxy behavior, rate limiting, logging/retention, patching, and threat
monitoring. Changing the bind address alone is not an approved deployment path.

### 7. Make limitations and provenance part of the product surface

The explorer keeps an always-available **Data and limitations** disclosure containing:

- the SHA-256 of `build/wayfinding.gpkg` used for the current process;
- that content is read from normalized Phase 1 layers derived from the read-only AIIM source;
- that only source records marked searchable are shown;
- that there is no route, connector, search-index, live-status, or LLM capability;
- that unit accessibility tags describe destinations, not paths; and
- that path width, slope, surface, powered doors, door width, closures, and current elevator status
  are not verified.

The UI must not display a route action, accessible-route toggle, nearest-place action, distance,
travel time, animated location, or AI/model branding. Disabled controls are not sufficient; absent
capabilities are omitted and requests for them are refused in the assistant.

### 8. Test through the container boundary

DT-013 follows red-green-refactor development and adds tests before production code. All tests run
inside the prebuilt container; none invoke host Python, GDAL, a package installer, or a database
client. The test strategy includes:

1. API contract tests for methods, status codes, content types, size limits, deterministic ordering,
   provenance, required-layer startup failure, and absence of future `/v1` endpoints.
2. Artifact integration tests asserting the current normalized counts (3 facilities, 11 levels,
   1,017 public units, and 40 landmarks), exact level filtering, stable identifiers, valid geometry,
   and no leakage from raw or non-searchable unit layers.
3. Assistant table tests covering every supported intent, ambiguity, unknown data, route/nearest/
   distance refusals, mobility phrasing, deterministic repeated responses, evidence, and injection
   strings.
4. Static-client tests for local-only assets, semantic controls, keyboard-selectable alternatives,
   focus visibility, status announcements, safe text insertion, limitations text, and the absence of
   route, LLM, CDN, analytics, and external-network features.
5. End-to-end HTTP tests that load the explorer, select a facility and level, retrieve a real scene,
   select a real unit, and submit a deterministic assistant query against the mounted artifact.
6. Security tests for traversal, unsupported methods, malformed JSON, oversized input, hostile text,
   response headers, loopback binding, no CORS, read-only artifact mounting, no source-GDB mount,
   and no runtime install or outbound network dependency.

The checked-in launcher is the only state-changing entry point for starting the demo. Its dry-run
mode and container contract are tested. Manual stakeholder walkthroughs supplement but do not
replace executable tests.

### 9. Preserve a direct migration path to the target architecture

The demo is disposable at its outer boundaries and reusable only where contracts genuinely match:

- FastAPI may replace the standard-library HTTP adapter while retaining artifact-reader tests and
  response DTO concepts; the future API is published under `/v1`, not by silently promoting
  `/demo/v1`.
- PMTiles and MapLibre replace per-level JSON geometry and SVG rendering after the basemap pipeline
  exists. Facility selection, `vertical_order` floor semantics, and selected-entity state carry
  forward.
- SQLite FTS5 replaces bounded literal matching. The demo matcher is not extended into a second
  search engine.
- The contracted graph, unit connectors, routing profiles, and deterministic instruction generator
  must exist before route, nearest, distance, time, or path-accessibility responses are added.
- A future LLM is introduced only behind the tool-calling orchestrator in system design section 8.
  It consumes deterministic search/routing results, cannot compute geometry or accessibility, and
  is clearly distinguished from this deterministic assistant.

DT-013 code and tests must keep artifact access, deterministic intent handling, HTTP adaptation,
and static presentation as separate modules so each outer component can be replaced without
embedding OGR calls in UI or conversational response formatting.

## Consequences

### Positive

- Stakeholders can inspect and click real SFU facility, level, room, detail, and landmark data now,
  without waiting for Phases 2-6 or accepting a mockup.
- The conversational interaction is reproducible, inspectable, offline, and accurately disclosed
  for AI-policy review.
- Loopback-only serving, an artifact-only read-only mount, no runtime installation, and no external
  assets keep the slice hermetic and narrow.
- Explicit refusals prevent the visual demo from implying that route, proximity, live-status, or
  accessibility-path capabilities exist.
- The `/demo/v1` namespace and replaceable boundaries avoid freezing the temporary HTTP and SVG
  choices into the production API.

### Negative

- A standard-library server, per-level JSON geometry, literal matching, and SVG rendering will not
  scale to the target production experience and are intentionally short-lived.
- Detail linework may produce large level responses; bounded in-memory caching improves repeat
  interaction but does not replace tiles.
- The local demo has no authentication, TLS, multi-user isolation, persistence, observability, or
  production availability guarantees and cannot be exposed remotely.
- The panel may look less conversational than an LLM because it asks for clarification and refuses
  unsupported language instead of guessing. That limitation is the required behavior.
- Browser accessibility requirements are testable only in part with the current image; stakeholder
  and assistive-technology review remains necessary before making a conformance claim.

### Supersedes and refines

This ADR does not supersede the target FastAPI, FTS5, routing, MapLibre, or tool-calling LLM
architecture in system design sections 2 and 4-9. It refines the phase ordering in section 11 only
by authorizing a temporary artifact-backed stakeholder demo before Phases 2-6 are complete. The
demo is not evidence that those phases have shipped.

This ADR also does not relax ADR-0006's immutable-image requirement. Its explicit local-image path
is a development fallback while the publication digest remains unresolved, not permission for
runtime installation or mutable normal execution.

### Independent of

ADR-0003's normalized schema and dual-CRS storage remain authoritative. ADR-0004's graph identity,
ADR-0005's measured connectivity and elevator-only profile gates, and ADR-0006's artifact lineage
remain unchanged. DT-013 reads no graph and makes no connectivity or routing claim.

### Required implementation work

1. `planner`: create the DT-013 implementation plan from this ADR and keep all production work out
   of the ADR ticket.
2. `test-writer`: add failing containerized API, artifact, assistant, client, security, and launcher
   tests described in section 8.
3. `implementer`: add the artifact-only demo service, static explorer, deterministic assistant, and
   reproducible launch/teardown scripts only after the failing tests exist.
4. `data-qa`: verify displayed feature counts, level membership, identifiers, unit provenance, and
   representative geometry against `build/wayfinding.gpkg`.
5. `judge`: reject the slice if it exposes the source GDB, raw/non-searchable units, external
   dependencies, runtime installs, route-like output, unsupported accessibility claims, or LLM/AI
   branding for the deterministic assistant.