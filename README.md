# SFU Indoor Wayfinding — Design Workspace

The optional Burnaby overview preview adds a fourth footprint, Applied Sciences
Building (ASB, 038), alongside the three indoor pilot buildings. Launch it with
a verified local Room Finder snapshot. [Preview instructions and coverage](docs/reports/DT-023-ASB-INTAKE.md)

**November 20 wayfinding checkpoint.** The merged pilot includes the client,
ETL, tests, launchers, TLS and recovery configuration verified on top of
`5ca5186`, alongside their decisions and reports. To reproduce the checks,
provide the documented Docker images and the named local datasets or artifacts.

The locally verified client supports building-scoped floors, searchable route
endpoints and explicit Preview. Users can explore another floor and return to
their selected instruction and zoom. The rollout proceeds from the pilot to more
Burnaby buildings and then other SFU campuses. [Journey evidence](docs/reports/DT-024-JOURNEY.md) · [Roadmap](docs/ROADMAP.md)

The [compact navigation follow-up](docs/reports/DT-024-COMPACT.md) adds visible
building/floor buttons, direct room-map entry and a filterable room list, reducing
the need to scroll or use dropdowns for exploration.

Design and analysis workspace for an AI-assisted indoor navigation system over the SFU Burnaby
AQ / Strand Hall / ECC indoor geodatabase.

> **Write boundary:** everything produced by this work lives under `C:\repos\sfudt\ghcp`.
> All geodatabases under local `data/`, and the sibling `dtwin-harness` source,
> are immutable inputs. Source-etl mounts local `data/IndoorWayfinding.gdb` read-only.
> Compose masks `/workspace/data` so the workspace bind cannot bypass source isolation.

`data/` contains the legacy indoor geodatabase, the revised AQ/Strand/ECC geodatabase,
and supplemental entrance, door and ramp survey data. Both indoor datasets contain all
three buildings. The legacy local copy is byte-identical to the previously used sibling
copy. See [local source verification](docs/reports/LOCAL-SOURCE-REVIEW.md) for counts,
hashes and the revised pathways that still need facility/level reconciliation.

## Documents

| Document | Contents |
| --- | --- |
| [docs/01-data-findings.md](docs/01-data-findings.md) | What is actually in the geodatabase — layers, counts, domains, and the nine data gaps that constrain the design |
| [docs/02-system-design.md](docs/02-system-design.md) | Architecture, ETL, routing, accessible mode, turn-by-turn generation, API, AI assistant, delivery phases |
| [docs/03-harness-design.md](docs/03-harness-design.md) | The AI-agent delivery harness this repo is built with — subagents, slash commands, gates |
| [docs/generated/](docs/generated) | Raw tool output backing every number in the docs |
| [docs/HANDOFF.md](docs/HANDOFF.md) | Living project state — read first every session |
| [Project oral history](docs/ORAL-HISTORY.md) | Chronological account of the decisions, failed assumptions, corrections and open questions |
| [docs/DOD.md](docs/DOD.md) | Definition of Done / merge gate contract |
| [docs/SDLC.md](docs/SDLC.md) · [docs/ROADMAP.md](docs/ROADMAP.md) | How a ticket moves end to end; phase status at a glance |
| [docs/adr/](docs/adr) | Architecture decision records |
| [GIS data needed](docs/requests/GIS-DATA-NEEDED.md) | Short, keyed request for missing route connections, floor assignments and verified access data |

## Agent harness

Shared operating instructions live in [AGENTS.md](AGENTS.md); current status lives in
[docs/HANDOFF.md](docs/HANDOFF.md). The shared delivery workflow uses a ticket
plan, failing tests, implementation, Docker gates, documentation and independent review.
Copilot's specialist roles and prompts remain available as optional adapters under
[`.github/`](.github). The historical design is in
[docs/03-harness-design.md](docs/03-harness-design.md).

```
.github/
  copilot-instructions.md   # adapter to shared AGENTS.md
  agents/                   # planner, architect, test-writer, test-runner,
                             # implementer, judge, doc-writer, data-qa, researcher
  prompts/                  # /bootstrap /tdd-feature /data-import /demo /retro /sprint-plan
  instructions/             # container-only-execution, accessibility-claims,
                             # spatial-data-invariants
  hooks/                    # post-tool diagnostic; cannot prevent completed writes
```

`make fast` runs source-independent tests, lint, types and launcher checks.
`make gates` runs full tests with the 85% coverage floor, lint, types and artifact QA.
The PR workflow runs only the fast gate; it does not certify private artifact or LAN acceptance.
Source protection relies on runtime permissions and read-only mounts.

All project code, scripts, tests, builds, data processing and evidence generation
run in Docker. Host use is limited to repository inspection/editing, Git/Docker CLI
and thin Docker launchers. Missing Docker is an execution blocker, not a reason to
use a host runtime. This applies equally to large-model leads and smaller workers.

On Windows without Make, run the fast gate with:

```powershell
docker compose -f infra/docker-compose.yml run --rm artifact sh tools/check-fast.sh
```

For explicitly local-image verification, append `-f infra/docker-compose.local.yml`
before `run`. This does not certify the published image. After checks, run
`./tools/capture-takeover-evidence.ps1` to launch evidence generation in Docker.
Use its `-LocalImage` switch for explicit local-image verification. The host wrapper
forwards Git metadata; file/artifact hashing and JSON output happen inside the container.

The artifact-backed browser gate uses a pinned Chromium image and a fresh demo on
an internal Docker network, without publishing a host port or installing packages:

```powershell
docker compose -f infra/docker-compose.browser.yml up --force-recreate --abort-on-container-exit --exit-code-from browser
docker compose -f infra/docker-compose.browser.yml down
```

`make browser` runs the first command. For local-image investigation, set
`$env:WAYFINDING_BROWSER_BUILD_IMAGE = 'wayfinding-build:local'` before running it.
Results and screenshots are written to `build/takeover-browser/` inside Docker.
Set `WAYFINDING_BROWSER_RUN_LABEL` to a new safe basename to retain a separate
evidence directory for a run. The gate now checks exact selected instruction spans,
transition departure/arrival, floor preview, keyboard controls, the requested AQ
route and its reverse, ECC and the four canonical routes. It also checks 320px layout.
The browser runner uses Chromium's [DevTools protocol](https://chromedevtools.github.io/devtools-protocol/)
through its local pipe. It checks desktop/mobile viewports; a physical second-device
machine-name LAN check remains a separate acceptance requirement.

## Tools

The isolated rebuild preserves accepted `build/` artifacts and writes each new run
under `build/experiments/`. It requires an unused run ID and a locally available
image; the launcher pins execution to the inspected image ID. Source extraction
and final verification run separately from artifact-only graph construction.

```powershell
./tools/rebuild.ps1 -Action Review -RunId source-review-01 -LocalImage
./tools/rebuild.ps1 -RunId legacy-01 -LocalImage
./tools/rebuild.ps1 -RunId legacy-02 -LocalImage
./tools/rebuild.ps1 -Action Compare -RunId legacy-01 -OtherRunId legacy-02 -LocalImage
```

Omit `-LocalImage` to require the published pinned image. On POSIX, use
`sh tools/rebuild.sh build legacy-01 --local-image` (also `review` and `compare`).
Build extraction uses exact shared source vertices by default. To reproduce the
historical endpoint-only graph for comparison, add `--topology endpoint-v1` to the
POSIX command or `-Topology endpoint-v1` to the PowerShell command. Topology
selection is valid only for `Build`; derive and finalize consume the sealed
extraction manifest, while `Review` and `Compare` reject the option. Legacy
manifests without a topology setting retain endpoint-only semantics.

If PowerShell reports `No such image` for the published digest, select the existing
local development image explicitly:

```powershell
.\tools\rebuild.ps1 -RunId 001 -LocalImage
```

Use a new run ID if `build/experiments/001` already exists. The script is
`tools/rebuild.ps1`; supply `-RunId` to avoid the interactive parameter prompt.
The launcher requires its selected image to be present and does not automatically
pull or switch images. If Docker reports a daemon/connection error, resolve that
error first. If the local image is also absent, build it from the repository root
with `docker build -f infra/Dockerfile.build -t wayfinding-build:local .`.

`Build` currently reconstructs **legacy `IndoorWayfinding.gdb`**. `-LocalImage`
selects a container image, not newer GIS data. `-Action Review` inspects the legacy,
revised indoor and supplemental datasets; revised/supplemental routing ingestion
remains tracked separately in DT-017.

Make equivalents are `make etl RUN_ID=legacy-01 REBUILD_OPTIONS=--local-image`,
`make source-review RUN_ID=source-review-01 REBUILD_OPTIONS=--local-image`, and
`make compare-builds RUN_ID=legacy-01 OTHER_RUN_ID=legacy-02 REBUILD_OPTIONS=--local-image`.
Choose an unused run ID for every build. The legacy individual stage targets and
the fixed-output Python stage CLI are retired. Use the isolated rebuild commands
above to create a complete candidate and its verification manifest.

New builds reconstruct unambiguous multipart pathways using exact native 3D
endpoints and retain source part and vertex references. A snapped node can keep
two paths connected while their unequal native endpoints prevent merging their
geometries. The older published demo artifacts retain their original behavior.
See [ADR-0025](docs/adr/0025-exact-multipart-pathways.md).

Compare can read completed, sealed runs made with different code. It verifies
both artifact ledgers before comparing semantic snapshots. A valid comparison
with differences writes its report and exits 1. Inspect the report for changes
in anchors and reachability. Build stages still require matching runtime identity.

Each run retains raw extraction, derived artifacts, `run.json` stage/hash lineage
and `semantic-snapshot.json`. Comparisons under `build/experiments/comparisons/`
separate byte equality from graph, unit, anchor and profile reachability equality.
Completed candidates are unpromoted legacy reconstructions, not source-quality
approval. Review diagnostics include revised missing identities and legacy multipart
ordering issues. See [DT-016](docs/plans/DT-016.md) and [DT-017](docs/plans/DT-017.md).

Every finding in the documentation is reproducible from these scripts.

| Script | Requires | Output |
| --- | --- | --- |
| `tools/dump_gdb_schema.ps1` | Legacy reference; PowerShell Docker runtime required | Existing `docs/generated/gdb-schema.txt` records feature-class schemas from `GDB_Items` XML |
| `tools/dump_gdb_domains.ps1` | Legacy reference; PowerShell Docker runtime required | Existing `docs/generated/gdb-domains.txt` records coded-value domains |
| `tools/profile_gdb.sh` | run via the wrapper | the OGR/SQL profiling queries |
| `tools/run_profile.ps1` | Docker | `docs/generated/gdb-profile.txt` — authoritative schemas, counts, extents, value distributions, null checks |
| `tools/launch-stack.ps1` / `.sh` | Docker Compose | starts an isolated stack on the first free configurable host-port block |
| `tools/teardown-stack.ps1` / `.sh` | Docker Compose | destroys one explicitly selected stack project |

```powershell
cd C:\repos\sfudt\ghcp
.\tools\run_profile.ps1
```

`run_profile.ps1` executes `tools/profile_gdb.sh` inside `ghcr.io/osgeo/gdal:alpine-small-latest`
with the data directory mounted read-only. No GDAL, Python or ArcGIS install is required on the host.

## Start and destroy the developer stack

The normal launcher starts/reuses the developer stack **and** the router-mapped
public candidate at **https://sfuai.ca:8017/**. From the repository root:

```powershell
.\launch-stack.ps1 -LocalImage
```

The router maps public TCP 8017 to `192.168.1.80:18087`; nginx publishes that local
port, while the exact-topology candidate stays private on `127.0.0.1:18107`.
Normal startup includes the TLS overlay and mounts existing
`C:/repos/web/certs/fullchain.pem` and `privkey.pem` read-only. These files stay
outside Git; the existing certificate owner handles renewal. Reload/restart the
proxy after certificate replacement. Plain HTTP redirects to HTTPS on port 8017.
TLS does not repair router loopback; access from the same LAN can still depend
on the router's support for reaching its public address.
Both public containers use `unless-stopped`, so Docker restarts them when its
engine starts after a reboot. Docker Desktop must start when you sign in; the
container policy does not start Desktop. An intentional `stop external` remains
stopped until you run the normal launcher again.

`-NoPublicDemo` / `--no-public-demo` skips public startup for an isolated developer
session without stopping the public service. Dry runs print both startup commands.
Repeat runs reuse this checkout's existing developer project and fixed public
project, and reject unrelated ownership/port conflicts rather than create duplicates.

These checked-in settings explicitly use the cached local build image and existing
`sh-navigation-exact-20260923` artifacts. The developer stack on 18007 is preserved.
To withdraw public access:

```powershell
docker compose -p sfudt-sh-navigation-candidate --env-file infra/wayfinding-public.env -f infra/docker-compose.candidate.yml stop external
```

See [ADR-0020](docs/adr/0020-router-nat-demo-publication.md),
[ADR-0021](docs/adr/0021-integrated-public-startup-and-recovery.md) and
[ADR-0022](docs/adr/0022-public-demo-tls.md).

Docker Desktop must be running. From the repository root, build the local image and start the
Phase 1 developer containers and public candidate. The root PowerShell entrypoint
forwards to `tools/launch-stack.ps1`. Skip the `docker build` command if the local
image already exists:

```powershell
docker build -f infra/Dockerfile.build -t wayfinding-build:local .
.\tools\launch-stack.ps1 -LocalImage
```

```sh
docker build -f infra/Dockerfile.build -t wayfinding-build:local .
./tools/launch-stack.sh --local-image
```

Omit `-LocalImage` / `--local-image` to use the published digest for the developer
stack; registry access is required. Public startup uses the explicit image in
`infra/wayfinding-public.env`. `-Build` / `--build` alone does not build the local image when
the Compose file already specifies a published digest.

The launcher prints the selected Compose project, normally `sfudt-wayfinding-18000`. Keep that exact
name: an existing project from this checkout is reused; for a new stack, occupied
ports advance the launcher in blocks of ten and it may print a name such as
`sfudt-wayfinding-18010`. The launcher starts healthy `artifact`, `source-etl`, and `demo` containers
and prints a machine-name URL such as `http://<machine-name>:18007/`. This is a trusted LAN demo
with no authentication and no TLS. Restrict the selected port to the intended private network or
subnet with the host firewall, and stop the stack after the attended demo.

To roll back to loopback-only access, set `DTWIN_DEMO_BIND_ADDRESS=127.0.0.1` before restarting the
stack; the launcher will then report `http://127.0.0.1:<port>/` and LAN access will be disabled.
Open the reported URL for the real artifact-backed floor explorer and deterministic data assistant.

The demo opens a three-building campus pilot (AQ, ECC and Strand Hall). Search a
building by its source name or code, select its footprint, then choose a recorded
floor. Building selection also updates the Building and Floor dropdowns, retaining
the current global floor order where recorded, or selecting that building's order-0
or first recorded floor. It stays in Building inspection until you choose a floor.
Buildings without indoor floors have an empty, disabled Floor dropdown.
Campus returns to the overview while retaining the room endpoints. Campus
zoom and reset are separate from floor and route framing. The inventory is incomplete;
visible buildings do not imply connected routes or verified outdoor entrances.
`GET /demo/v1/campus` returns the versioned source geometry, coverage and artifact
identity described in [ADR-0016](docs/adr/0016-campus-overview-and-coverage.md).

The demo renders normalized room, detail, and landmark geometry from `build/wayfinding.gpkg` and
supports deterministic indoor routes over `build/graph_contracted.pkl`. Routes connect disclosed
approximate same-level room anchors within measured graph components; room-to-anchor traversal is
not represented or verified. The elevator-only profile excludes stairs but does not verify door
width, path width, slope, powered doors, surface, closures, opening hours, door access, or elevator
status. The demo has no public-map geometry, nearest-place ranking, travel-time estimate, live
status, or LLM dependency.

To show directions, choose a building and floor, click a starting room A, then
click a connected destination B on the map or in the room list. Directions appear
automatically. You can change floors between A and B. Further room clicks keep A
and replace B; **Clear route** lets you choose a new start. The **Room clicks**
selector defaults to **Route A to B**; choose **Inspect only** to browse records
without changing endpoints or directions.

In Directions, open **Search From rooms** or **Search To rooms** and enter a room ID,
building name, acronym or building ID. Use Building and Floor to narrow the list.
Check the floor when two rooms share a label. Select the room and use the button
below the results to set that endpoint. In Inspect only mode, selecting a room
opens its record. Use **Start here** or **Directions here** to set it as an
endpoint. You can also enter an exact directions request in the assistant.
Review the rooms and profile, then choose **Preview route**.

While you edit, the map and instructions name the rooms and profile of the
displayed route. If a replacement fails, the previous route stays visible with
its original label. **Clear** removes the draft and displayed route and keeps
the room, floor and camera you were inspecting.
Once a starting room is selected, destination search shows the connection status
for the chosen profile. The existing destination menu offers mapped choices.
A `same_anchor` result means two eligible rooms share an anchor but have no positive-length
walking path; it is reported separately from a connected route and does not create a segment or imply
door access. Availability describes the directed measured graph only. It does not certify guidance
geometry, door traversal, or physical accessibility.

Directions use readable room/floor labels, an ordered floor journey and explicit
stair/elevator departure and arrival controls. Selecting an instruction highlights
its exact span in blue with an arrow and number; Previous/Next changes the preview.
You can inspect another floor and return to the selected step, or fit the route or
whole floor. Selection does not track your physical position.

The map opens a new route with the visible current-floor route in context, including point-only
departure, arrival and transition steps. Use the accessible zoom and framing controls to widen or
narrow the camera, show the route, or restore the whole-floor view. Changing floors establishes a
valid frame; a manual camera choice is retained while the same floor is redrawn.

The additive `guidance` response preserves the original route evidence. Native
geometry/distance disagreement disables precise walking copy and displays a review
notice; misaligned endpoints make guidance unavailable. This does not repair the
known multipart issue. See [ADR-0012](docs/adr/0012-route-guidance-and-floor-preview.md)
and [DT-018](docs/plans/DT-018.md).

To start the containers and then run the test, lint, type, and artifact data-QA gates, add the test
option:

```powershell
.\tools\launch-stack.ps1 -LocalImage -Test
```

```sh
./tools/launch-stack.sh --local-image --test
```

Destroy the stack by passing the required, exact project name printed during startup. Include the local-image
option because the start commands above use the local Compose override:

```powershell
.\tools\teardown-stack.ps1 -ProjectName sfudt-wayfinding-18000 -LocalImage
```

```sh
./tools/teardown-stack.sh --project-name sfudt-wayfinding-18000 --local-image
```

Teardown preserves volumes by default. Add `-Volumes` or `--volumes` only when stored Compose data
should also be deleted. Use `-DryRun` or `--dry-run` to inspect either operation without changing
container state. `-ComposeFile` or `--compose-file` selects another compatible Compose definition;
custom starts also support `-BasePort` / `--base-port` and `-ProjectName` / `--project-name`.

The current Phase 1 Compose definition publishes only the demo port, on all interfaces by default
for the bounded trusted-LAN demonstration. Reserved PostGIS, Redis, Martin, API, web, and Neo4j
ports remain unpublished until those services are added later.

The legacy schema/domain PowerShell parsers now refuse host execution. They are retained
as reference and require a PowerShell container with explicit container paths; the current
build image does not include PowerShell. Use the supported Docker/GDAL profiling wrapper.
Where historical parser output disagrees with `ogrinfo`, **`ogrinfo` is authoritative** (see the note in
[docs/01-data-findings.md](docs/01-data-findings.md) §4).

## Status

The pilot covers AQ, ECC and Strand Hall. It supports room search, explicit route
preview and floor-by-floor directions over the supplied indoor network. Each
journey visit retains its place even when a route returns to the same floor.
See the [roadmap](docs/ROADMAP.md) and [handoff](docs/HANDOFF.md) for the
verification record and Burnaby expansion sequence.

Connectivity depends on the artifact. The original endpoint graph measured 816
default and 840 elevator-only components. The isolated DT-017 legacy candidate
measured 4 and 13 respectively after exact topology and multipart reconstruction.
Candidate promotion and admission of the 141 revised pathways remain open.
Physical accessibility is unverified. See the [geometry comparison](docs/reports/DT-017.md).
