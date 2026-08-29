# SFU Indoor Wayfinding — Project Guidelines

Design-and-build workspace for an AI-assisted indoor navigation digital twin over the SFU Burnaby
AQ / Strand Hall / ECC geodatabase. See [docs/02-system-design.md](../docs/02-system-design.md) for
the product design and [docs/03-harness-design.md](../docs/03-harness-design.md) for how this repo
is built (subagents, slash commands, gates).

## Prime directives

1. **Write boundary.** Everything this harness produces lives under this repo. The source
   geodatabase (`C:\repos\sfudt\claude\dtwin-harness\data\IndoorWayfinding.gdb`) and the sibling
   `dtwin-harness` repo are **read-only** — never edit, move, or delete anything there.
2. **No local Python, no local GDAL, ever.** Every data or test operation runs inside a container.
   `tools/run_profile.ps1` is the existing pattern: it shells out to
   `ghcr.io/osgeo/gdal:alpine-small-latest`, never installs GDAL/Python on the host. Extend this
   pattern for ETL, tests, and services — do not add a step that requires host Python.
3. **The LLM never computes geometry, routes, or accessibility claims.** Those are deterministic
   code paths (routing, ETL, instruction generation). AI components orchestrate and narrate; they do
   not calculate.
4. **TDD once product code starts.** No production code without a failing test first
   (red → green → refactor). Use `/tdd-feature` (see below) rather than writing code ad hoc.
5. **Every state-changing action is a checked-in script.** Never a one-off command typed into a
   session and discarded — data imports, migrations, fixture/golden captures must be reproducible by
   a fresh checkout with no agent present.
6. **Accessibility claims carry provenance.** The dataset has no path-level accessibility attributes
   (see [docs/01-data-findings.md gaps G1–G3](../docs/01-data-findings.md#8-data-gaps-that-constrain-the-design)).
   The accessible routing profile is *elevator-only*, stated as such — never imply a stronger
   guarantee than the data supports.

## Architecture

- Source: Esri AIIM File Geodatabase (`Facilities`/`Levels`/`Units`/`Pathways`/`Transitions`/`Landmarks`), EPSG:26910.
- Pipeline (once Phase 1 starts): containerised ETL → PostGIS/GeoPackage + contracted NetworkX graph
  → FastAPI routing/search → MapLibre web client → tool-calling assistant. Full detail:
  [docs/02-system-design.md](../docs/02-system-design.md).
- Delivery is phased (§11 of the system design); phase status lives in
  [docs/HANDOFF.md](../docs/HANDOFF.md).

## Build and test

- Reproduce data findings: `tools/dump_gdb_schema.ps1`, `tools/dump_gdb_domains.ps1` (no Docker),
  `tools/run_profile.ps1` (Docker).
- No product `Makefile`/gates exist yet — they are a Phase 1 deliverable, added by `architect` +
  `implementer` against the contract in [docs/DOD.md](../docs/DOD.md).

## Working with the agent harness

- Use `/tdd-feature` for any feature or bugfix once product code exists; use `/sprint-plan` for
  backlog decomposition; use `/data-import` for any ETL change; use `/bootstrap` to bring the stack
  up from a clean checkout; use `/demo` for a stakeholder walkthrough; use `/retro` after closing a
  ticket or phase.
- Prefer delegating to the narrow subagents in `.github/agents/` (`planner`, `architect`,
  `test-writer`, `test-runner`, `implementer`, `judge`, `doc-writer`, `data-qa`, `researcher`) over
  doing planning, testing, and implementation all in one pass — see
  [docs/03-harness-design.md §3](../docs/03-harness-design.md#3-subagent-pipeline).
- A ticket is not done until `judge` records `APPROVE` against [docs/DOD.md](../docs/DOD.md).

## Conventions

- Numbered docs (`docs/01-...`, `docs/02-...`) are the durable design record; keep them in sync with
  reality rather than adding parallel notes elsewhere.
- ADRs (`docs/adr/`) are required for schema, API, or component-boundary changes.
- Every plan lives in `docs/plans/<ticket-id>.md` before any code is written.
