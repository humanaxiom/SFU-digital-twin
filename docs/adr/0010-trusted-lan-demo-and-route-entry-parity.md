# 10. Trusted-LAN demo publication and route-entry parity

Status: Accepted
Date: 2026-09-10

## Context

DT-015 must make the bounded stakeholder demo reachable from a second device by the demo host's
machine name and reduce route entry to two room activations. The current container process already
binds its HTTP server to `0.0.0.0`, but Compose publishes the selected host port only on
`127.0.0.1` (`infra/docker-compose.yml`). Both checked-in launchers reserve the demo port after
checking the full host port block, then print only a loopback URL (`tools/launch-stack.ps1` and
`tools/launch-stack.sh`). Changing only the Compose publication would contradict ADR-0007's
explicit localhost trust boundary.

The demo remains a temporary, offline, artifact-backed slice. Its workspace and three accepted
route artifacts are mounted read-only, its static files are allowlisted, request bodies and
identifiers are bounded, responses carry restrictive browser security headers, CORS is absent, and
unsupported methods are rejected. It has no user accounts, secrets, durable application state,
external assets, outbound service dependency, raw filesystem endpoint, or state-changing product
operation. `POST /demo/v1/route` computes a response but does not mutate artifacts or server-side
product state. LAN publication nevertheless adds untrusted request sources and DNS-rebinding and
resource-exhaustion risks that the localhost decision did not need to address.

ADR-0008 authorizes one deterministic `POST /demo/v1/route` contract over non-traversal approximate
room anchors. The current direct route form already sends that contract and uses one `renderRoute`
path. Room pointer and keyboard activation only inspect records, while exact deterministic assistant
directions return a route envelope through a separate client branch. Adding routing logic to the
browser or an LLM, or constructing room-to-anchor overlay segments, would violate the deterministic
core and ADR-0008's graph-only geometry boundary.

The source data still has no path-level evidence for door width, path width, slope, powered doors,
or surface. `elevator_only` therefore means elevators only and stairs excluded; it is not a
wheelchair-certified or verified step-free claim. This remains true on success and failure.

## Decision

### 1. Publish a bounded demo to a trusted LAN

The demo process continues to bind `0.0.0.0:8080` inside its container. Compose publishes the
launcher-selected host port on a configurable host address whose DT-015 default is `0.0.0.0`.
The checked-in configuration uses one explicit variable, `DTWIN_DEMO_BIND_ADDRESS`, so an operator
can set `127.0.0.1` without editing Compose. No other service publication is widened by DT-015.

This is approval only for an attended, time-bounded demonstration on a trusted private LAN whose
participants may read the public floor-plan artifact. It is not approval for the public internet,
an untrusted guest network, open Wi-Fi, general campus publication, port forwarding, or a persistent
service. Startup output and user documentation must say that the demo is visible to the LAN, has no
authentication or TLS, and must be stopped after use. The host firewall must restrict the selected
port to the intended private network profile or subnet; the launcher cannot infer or modify that
policy.

Authentication and authorization are intentionally absent because the bounded demo exposes only
the same public, read-only artifact views and deterministic computations to trusted participants and
has no user-specific or mutating operation. TLS and a reverse proxy are also intentionally absent:
the promised machine-name URL is plain HTTP on the local segment, with no credentials or secrets to
protect in transit. If any non-public data, mutation, account, secret, untrusted network, persistent
availability, or internet exposure is introduced, this exception expires and a production
deployment ADR must define authentication, authorization, TLS termination, proxy trust, and
operations before publication.

### 2. Enforce the LAN HTTP boundary

LAN exposure retains all ADR-0007 request validation, exact route/static allowlists, body and result
limits, DOM-safe rendering, restrictive Content Security Policy, framing denial, no permissive CORS,
and sanitized errors. It adds these testable controls:

- The server accepts `Host` only for the launcher-provided machine name, its validated fully
  qualified form when explicitly configured, `localhost`, and loopback literals, each with the
  selected port when present. Missing, malformed, IP-literal LAN, wildcard, and unlisted hosts are
  rejected before dispatch. This bounds DNS rebinding without claiming arbitrary-IP access.
- Request concurrency is capped. Per-client in-memory limits separately bound API reads and POST
  computations, return `429` with `Retry-After`, expire old entries, and cap limiter memory. These
  counters are ephemeral operational state, not product or artifact mutation.
- API responses are not stored by shared caches. Existing CSP, `nosniff`, no-referrer, and framing
  denial remain mandatory. No `Access-Control-Allow-Origin` header is added; browser requests stay
  same-origin.
- Access logs go only to container stdout and contain timestamp, client address, method, normalized
  route template, status, and duration. They omit query strings, bodies, assistant text, room
  selections, headers, artifact paths, and stack traces. Compose applies bounded log rotation; no
  application log or transcript is written into the repository or mounted artifacts.
- Monitoring is limited to the existing local healthcheck and operator-visible container status.
  There is no production availability or incident-response claim. The digest-pinned image or the
  checked-in explicit local-build path is used without startup installation or automatic update;
  operators rebuild deliberately for patches and tear the demo down when unattended.

The service remains offline and artifact-only. Static HTML, CSS, and JavaScript are checked in; no
CDN, font, analytics, tile, model, telemetry, or other external browser/server asset is permitted.
The source geodatabases, Docker socket, writable build directory, and arbitrary filesystem/data
routes remain outside the demo container boundary.

### 3. Print one reliable machine-name URL without network calls

The PowerShell launcher obtains the short machine name from the local operating-system environment
API (`[Environment]::MachineName`). The POSIX launcher obtains it from the local `hostname` command.
Neither launcher performs DNS lookup, interface enumeration, HTTP probing, or any external network
call to discover the name or address. Each validates the result as a non-empty DNS-compatible host
label and fails closed with a useful error if it cannot produce one; it must not silently advertise
`localhost` as the LAN URL.

Port selection continues to check bind availability on all IPv4 interfaces, not only loopback,
before Compose starts. Both launchers pass the validated name to the server's Host allowlist and
print `http://<machine-name>:<selected-demo-port>/` together with the trusted-LAN warning and the
effective bind address. Dry-run performs the same local validation and reporting but starts no
container and makes no network request. The printed name is the reproducible URL contract; actual
name resolution from a second device remains an environment prerequisite verified by the required
LAN smoke test, not something the launcher can guarantee or repair.

### 4. Use one two-endpoint selection state machine

Pointer room shapes, keyboard room activation, room-list buttons, and the existing origin and
destination selects feed one client-owned endpoint-selection state machine:

1. `empty`: one valid room activation becomes the origin and sends no route request.
2. `origin_selected`: a different valid room becomes the destination and starts exactly one route
   request; activating the origin again leaves the state unchanged and sends no request.
3. `request_pending`: endpoint identity and request generation are fixed. A newer clear, swap,
   correction, or selection supersedes the generation, and a late response cannot update the map.
4. `complete` or `failed`: the response is rendered through the common route renderer. The next room
   activation clears the prior pair and becomes the next origin.

Origin and destination persist across floor rendering and have text labels and non-color-only map
and list states. Clear removes the appropriate endpoint and stale route. Swap exchanges a complete
pair and submits once. Manual selector correction updates the same state and submits only when two
distinct valid endpoints exist. Pointer and Enter/Space activation are behaviorally identical and
status changes are announced. This state is browser presentation state only; it creates no
server-side session or durable history.

### 5. Route every entry path through one HTTP command and renderer

The direct form, completed two-room pair, and exact chat direction grammar call one client
`requestRoute(origin, destination, profile, generation)` command. That command makes exactly one
`POST /demo/v1/route` using ADR-0008's unchanged request contract, then passes the success or error
envelope to the existing common `renderRoute` path. Ordinary exact directions select `default`;
mobility wording selects `elevator_only`. Other bounded artifact-assistant intents continue to use
`POST /demo/v1/assistant`.

For exact chat directions, deterministic client parsing may recognize only the existing closed
`directions from <exact-id> to <exact-id>` grammar and its existing mobility prefixes. It performs
no fuzzy resolution, search, routing, reachability, distance, geometry, instruction, or
accessibility computation. There is no LLM in this demo. Moving this closed dispatch decision to the
shared client command prevents the assistant endpoint and route endpoint from computing the same
route twice; the server-side assistant may retain equivalent delegation for non-browser contract
compatibility, but the browser does not issue both requests.

Equal origin ID, destination ID, and profile therefore produce the same HTTP status, endpoint and
reachability fields, ordered edge IDs and modes, distance, per-level geometries, steps, warnings,
provenance, and elevator-only disclosure regardless of entry path. Failures also use the same route
envelope and clear stale overlay geometry.

### 6. Keep the overlay graph-only

The renderer draws only `response.geometries` entries whose `level_id` equals the active level. It
does not derive a polyline from room polygons, centroids, approximate anchors, node IDs, edges, or
steps and does not join missing geometry. Origin and destination room highlighting is selection
state, not route geometry. Attachment distances remain disclosed as measurements to approximate
anchors, and the unrepresented room-to-anchor segments are never shown or described as walkable.

Every `elevator_only` success and failure visibly states “Elevators only; stairs excluded” and lists
`door_width`, `path_width`, `slope`, `powered_doors`, and `surface` as unverified. There is no stairs
fallback. These requirements preserve ADR-0008 and ADR-0009; DT-015 adds no graph edge, connector,
route algorithm, geometry computation, reachability rule, accessibility inference, or API schema.

## Consequences

### Positive

- A second trusted-LAN device can open the demo by a stable machine-name URL while loopback rollback
  remains a configuration change.
- Host validation, bounded resource use, minimal rotated logs, explicit warnings, and offline
  read-only operation narrow the added attack surface without pretending this is production.
- Manual, click, keyboard, and exact chat routes have one HTTP route contract and one rendering
  path, making parity directly testable and preventing duplicate route computation.
- Route overlays continue to represent only measured pathway and transition graph geometry.

### Negative

- There is no confidentiality against other trusted-LAN participants and no authentication, TLS,
  production monitoring, or availability guarantee.
- Machine-name resolution depends on the LAN's DNS, mDNS, NetBIOS, or equivalent host configuration;
  the launcher can report the local name but cannot make another device resolve it without network
  discovery or system changes.
- Host allowlisting and rate limiting add small amounts of ephemeral process state and deployment
  configuration to the temporary standard-library server.
- Exact chat directions remain intentionally narrow; conversational, ambiguous, or fuzzy endpoint
  resolution is still future assistant/search work.

### Supersedes and refines

This ADR supersedes only ADR-0007 section 6's loopback-only publication and its conclusion that no
remote exposure is approved. It replaces that boundary with the trusted-LAN exception and controls
above. ADR-0007's read-only artifact boundary, static allowlist, no external assets, no runtime
installation, bounded deterministic assistant, provenance, and temporary `/demo/v1` namespace
remain authoritative.

This ADR refines ADR-0008's UI and deterministic-assistant dispatch for DT-015 by requiring all
browser route entry paths to use the unchanged `POST /demo/v1/route` command and common renderer.
It does not supersede ADR-0008's accepted artifacts, approximate non-traversal anchors, profiles,
shortest-path behavior, disclosures, or graph-only response geometry. ADR-0009's edge-induced
component and reachability semantics remain unchanged.

This ADR is independent of ADR-0003's normalized schema, ADR-0004's graph identity, ADR-0005's
measured connectivity baseline, and ADR-0006's source, container, image, and artifact-lineage
boundaries. It does not supersede the future production FastAPI, MapLibre, search, or tool-calling
assistant architecture in system design sections 2 and 4-9.

### Rollback

Set `DTWIN_DEMO_BIND_ADDRESS=127.0.0.1` and restart, or run the checked-in teardown launcher. The
launcher then prints the loopback URL and states that LAN access is disabled. Rollback changes no
artifact, graph, route contract, endpoint catalog, or client-computed route result. Reverting the
DT-015 selection and shared-dispatch UI leaves DT-014's manual route form intact.

### Required implementation work

1. `planner`: bind DT-015 acceptance criteria to ADR-0010 and preserve the trusted-LAN limits and
   one-command rollback.
2. `test-writer`: add failing containerized tests for publication, Host validation, limits, headers,
   logging policy, launcher name/port output, the endpoint state machine, stale responses, route
   parity, graph-only overlays, and accessibility disclosures.
3. `implementer`: change only the demo publication/security adapter, checked-in launchers, and
   static client after those tests fail; do not modify routing computation or accepted artifacts.
4. `data-qa`: publish and replay the three measured DT-015 route fixtures without fabricating an
   endpoint, connector, edge, or geometry.
5. `test-runner`: run the focused and full container gates plus a real second-device machine-name
   smoke test on the intended trusted LAN.
6. `judge`: reject internet/untrusted-network exposure, absent startup warning, arbitrary Host
   acceptance, unbounded logs or requests, duplicate chat routing, stale response rendering, or any
   geometry/accessibility claim not returned by the deterministic route service.