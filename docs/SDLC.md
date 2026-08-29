# Software Development Lifecycle

How a change moves from idea to merged, in this repo.

## 1. Ticket intake

A ticket is a short id + description (e.g. `DT-101 contract degree-2 pathway chains`). Backlog
decomposition happens via `/sprint-plan` against the phases in
[docs/02-system-design.md §11](02-system-design.md#11-delivery-phases).

## 2. The pipeline

Every ticket with product-code impact goes through `/tdd-feature`, which runs:

`planner` → (`architect` if schema/API/boundary changes) → `test-writer` → `test-runner` (RED) →
`implementer` → `test-runner` (full gate) → `judge` → `doc-writer` → commit.

Full detail and the subagent-to-file mapping: [docs/03-harness-design.md §3](03-harness-design.md#3-subagent-pipeline).

## 3. Branching and commits

- Branch per ticket: `feat/<ticket-id>-<slug>` (or `fix/`, `chore/` where a ticket isn't a feature).
- Conventional Commits; commit story mirrors the pipeline stage: `red:` → `green:` → `refactor:` →
  `docs:`.
- No push without explicit user confirmation (operational-safety rule — pushing is a shared-system
  action).

## 4. Gates

Defined once and only once in [docs/DOD.md](DOD.md). `test-runner` runs them; `judge` checks they
were run and passed; neither invents new criteria beyond that file.

## 5. Data-touching tickets

Any ticket touching the ETL, routing graph, or accessibility logic also routes through `data-qa`
before `judge` — see [docs/03-harness-design.md §3](03-harness-design.md#3-subagent-pipeline) and
[.github/instructions/spatial-data-invariants.instructions.md](../.github/instructions/spatial-data-invariants.instructions.md).

## 6. Schema/API/boundary changes

Require an ADR (`architect`, `docs/adr/`) before `test-writer` starts. See
[docs/adr/0001-record-architecture-decisions.md](adr/0001-record-architecture-decisions.md) for the
convention.

## 7. Closing a ticket

`/retro` after `judge` APPROVEs, to capture process friction and any proposed change to the harness
itself (which then needs its own small ticket — harness files are not edited as a side effect of a
retro).
