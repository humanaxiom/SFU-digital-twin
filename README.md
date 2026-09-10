# SFU Indoor Wayfinding — Design Workspace

Design and analysis workspace for an AI-assisted indoor navigation system over the SFU Burnaby
AQ / Strand Hall / ECC indoor geodatabase.

> **Write boundary:** everything produced by this work lives under `C:\repos\sfudt\ghcp`.
> The source geodatabase at `C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb` is
> treated as strictly read-only and is always mounted `:ro` in containers.

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

## Agent harness

This repo is built with an AI-agent delivery pipeline (planner → architect → test-writer →
test-runner → implementer → judge → doc-writer, plus data-qa and researcher), ported from two
reference Claude Code harnesses onto GitHub Copilot's native `.agent.md` / `.prompt.md` /
`.instructions.md` primitives. See [docs/03-harness-design.md](docs/03-harness-design.md) for the
full design; the working files live under [`.github/`](.github):

```
.github/
  copilot-instructions.md   # always-on project rules
  agents/                   # planner, architect, test-writer, test-runner,
                             # implementer, judge, doc-writer, data-qa, researcher
  prompts/                  # /bootstrap /tdd-feature /data-import /demo /retro /sprint-plan
  instructions/             # container-only-execution, accessibility-claims,
                             # spatial-data-invariants
  hooks/                    # enforce-read-only-source.json (blocks writes to the
                             # read-only source GDB / sibling dtwin-harness repo)
```

## Tools

Every finding in the documentation is reproducible from these scripts.

| Script | Requires | Output |
| --- | --- | --- |
| `tools/dump_gdb_schema.ps1` | PowerShell only | `docs/generated/gdb-schema.txt` — feature-class schemas read directly from the `GDB_Items` XML |
| `tools/dump_gdb_domains.ps1` | PowerShell only | `docs/generated/gdb-domains.txt` — coded-value domains |
| `tools/profile_gdb.sh` | run via the wrapper | the OGR/SQL profiling queries |
| `tools/run_profile.ps1` | Docker | `docs/generated/gdb-profile.txt` — authoritative schemas, counts, extents, value distributions, null checks |
| `tools/launch-stack.ps1` / `.sh` | Docker Compose | starts an isolated stack on the first free configurable host-port block |
| `tools/teardown-stack.ps1` / `.sh` | Docker Compose | destroys one explicitly selected stack project |

```powershell
cd C:\repos\sfudt\ghcp
.\tools\dump_gdb_schema.ps1
.\tools\dump_gdb_domains.ps1
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
`sfudt-wayfinding-18010`. Both `artifact` and `source-etl` remain running and healthy for interactive
`docker compose exec` use.

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

The current Phase 1 Compose definition contains build and ETL jobs only. It does not publish the
reserved PostGIS, Redis, Martin, API, web, or Neo4j ports until runtime services are added later.

The two PowerShell scripts parse the FileGDB binary directly and exist as a no-Docker fallback; where
they disagree with `ogrinfo`, **`ogrinfo` is authoritative** (see the note in
[docs/01-data-findings.md](docs/01-data-findings.md) §4).

## Status

Phase 0 complete: data profiled, findings documented, system designed, and the delivery harness
scaffolded (`.github/`, `docs/DOD.md`, `docs/HANDOFF.md`). **Phase 1 ETL in progress:** DT-001
through DT-006 complete (package skeleton, ETL infrastructure, extraction, normalisation, raw
pathway-graph construction, and transition-edge integration). The `packages/wayfinding/` package now
contains working ETL code producing `build/wayfinding.gpkg` (26 layers: 14 raw + 12 normalised
dual-CRS) and graph artifacts `build/graph_with_transitions.pkl` (15,587 nodes, 44,952 arcs: 44,826
pathway + 84 stairs + 42 elevator), `build/node_map.pkl` (44,978 endpoints), and
`build/graph_with_transitions_stats.json`. Graph exhibits 816 connected components (default) and 840
(elevator-only, stairs-excluded) due to fragmentation documented in ADR-0005; routing is limited to
connected regions. This is not wheelchair certification; door width, path width, slope, powered
doors, and surface remain unverified. Next: DT-007 (Contract Degree-2 Chains). See
[delivery phases](docs/02-system-design.md#11-delivery-phases) and
[docs/HANDOFF.md](docs/HANDOFF.md) for current state and next steps.
