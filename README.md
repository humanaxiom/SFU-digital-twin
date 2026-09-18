# SFU Indoor Wayfinding — Design Workspace

Current client work: [DT-024](docs/plans/DT-024.md) is being delivered in phases under [ADR-0017](docs/adr/0017-navigation-state-and-journey.md). The first increment implements building-scoped floors, explicit floor entry and protection against stale navigation responses. Searchable endpoint drafts and synchronized journeys remain pending. See the [phase A/B report](docs/reports/DT-024-PHASE-AB.md) for verification and delivery limits.

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
| [docs/DOD.md](docs/DOD.md) | Definition of Done / merge gate contract |
| [docs/SDLC.md](docs/SDLC.md) · [docs/ROADMAP.md](docs/ROADMAP.md) | How a ticket moves end to end; phase status at a glance |
| [docs/adr/](docs/adr) | Architecture decision records |
| [GIS data needed](docs/requests/GIS-DATA-NEEDED.md) | Short, keyed request for missing route connections, floor assignments and verified access data |

## Agent harness

Shared operating instructions live in [AGENTS.md](AGENTS.md); current status lives in
[docs/HANDOFF.md](docs/HANDOFF.md). Codex is taking over the inherited DT-015 work using
plan → failing tests → implementation → gates → documentation → final review.
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
Build extraction uses the endpoint topology by default. To select the exact shared-vertices
topology for a new build, add `--topology exact-shared-vertices-v1` to the POSIX command or
`-Topology exact-shared-vertices-v1` to the PowerShell command. Topology selection is valid only
for `Build`; derive and finalize consume the sealed extraction manifest, while `Review` and
`Compare` reject the option.

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
`make etl` now runs the complete isolated build; individual `etl-*` stage targets
retain their existing accepted-output behavior.

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

Docker Desktop must be running. From the repository root, build the local image and start the
Phase 1 developer containers:

```powershell
.\tools\launch-stack.ps1 -Build
```

```sh
./tools/launch-stack.sh --build
```

The launcher prints the selected Compose project, normally `sfudt-wayfinding-18000`. Keep that exact
name: if port 18000 is occupied, the launcher advances in blocks of ten and may print a name such as
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

The route form first offers destinations connected to the selected origin under the chosen routing
profile, with a count and a clear graph-based availability explanation. The full room catalog remains
available, so an intentionally selected unsupported destination still produces its explicit failure
message. A `same_anchor` result means two eligible rooms share an anchor but have no positive-length
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
.\tools\launch-stack.ps1 -Build -Test
```

```sh
./tools/launch-stack.sh --build --test
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

Phase 0 complete: data profiled, findings documented, system designed, and the delivery harness
scaffolded (`.github/`, `docs/DOD.md`, `docs/HANDOFF.md`). **Phase 1 ETL in progress:** DT-001
through DT-007 are complete, and DT-013/DT-014 provide the local artifact-backed explorer and
bounded routing proof of concept. The `packages/wayfinding/` package now
contains working ETL code producing `build/wayfinding.gpkg` (26 layers: 14 raw + 12 normalised
dual-CRS) and graph artifacts `build/graph_with_transitions.pkl` (15,587 nodes, 44,952 arcs: 44,826
pathway + 84 stairs + 42 elevator), `build/node_map.pkl` (44,978 endpoints), and
`build/graph_with_transitions_stats.json`. Graph exhibits 816 connected components (default) and 840
(elevator-only, stairs-excluded) due to fragmentation documented in ADR-0005; routing is limited to
connected regions. This is not wheelchair certification; door width, path width, slope, powered
doors, and surface remain unverified. Initial local-source inventory and pathway comparison
are recorded in [local source verification](docs/reports/LOCAL-SOURCE-REVIEW.md);
revised rebuild and promotion remain deferred. See
[delivery phases](docs/02-system-design.md#11-delivery-phases) and
[docs/HANDOFF.md](docs/HANDOFF.md) for current state and next steps.
