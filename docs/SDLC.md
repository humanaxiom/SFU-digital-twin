# Software Development Lifecycle

How a change moves from idea to merged, in this repo.

## Current collaboration policy

The accountable lead defaults to delegating multiple bounded tasks concurrently when they are independent.
Examples include separate modules, documentation files, or read-only reviews. Before delegation,
the lead records each task's scope, owned files, expected evidence, and dependencies. Each worker
must stay within that ownership and return the commands run, exit codes, relevant findings, and
any skips or limitations. Workers use smaller models for simple mechanical edits, routine
documentation, and established gate execution; a large-model lead owns planning, orchestration,
architecture decisions, and integration.

Dependent TDD stages remain sequential: write the planned failing test, confirm RED, implement,
run the relevant gates, and then review. Concurrent workers must not edit the same file or any
dependent output at the same time. The lead integrates the independent results, reviews the
combined diff, and obtains a large-model judge review of that final diff and its evidence. All
project code, scripts, tests, builds, data processing, and evidence generation run in Docker;
the host is limited to repository inspection/editing, Git and Docker CLI operations, and launcher
glue. A required Docker check that cannot run leaves the change incomplete.

## 1. Ticket intake

A ticket is a short id + description (e.g. `DT-101 contract degree-2 pathway chains`). Backlog
decomposition happens via `/sprint-plan` against the phases in
[docs/02-system-design.md §11](02-system-design.md#11-delivery-phases).

## 2. The pipeline

Shared workflow: plan -> RED evidence -> implementation -> gates -> documentation -> final review.
Use [AGENTS.md](../AGENTS.md) with one accountable lead and appropriate specialist review.
Copilot's optional `/tdd-feature` adapter provides these roles:

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
