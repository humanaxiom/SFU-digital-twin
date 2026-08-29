# Handoff — Living Project State

Read this first every session. Update it when the user asks, and whenever a ticket closes or a
decision is made that would leave this file materially stale — it should stay current enough that a
fresh session can resume cold from it alone.

## Current phase

**Phase 0 — complete.** Data profiled and documented
([docs/01-data-findings.md](01-data-findings.md)), system designed
([docs/02-system-design.md](02-system-design.md)), and the delivery harness scaffolded
([docs/03-harness-design.md](03-harness-design.md)): `.github/agents/`, `.github/prompts/`,
`.github/instructions/`, `.github/copilot-instructions.md`, `docs/DOD.md`, this file.

**Phase 1 foundation — complete.** The container execution model and package skeleton are in place:
`packages/wayfinding/`, `infra/docker-compose.yml`, `Makefile` gates (`test`/`lint`/`type`). All
gates pass. ADR-0002 documents the package layout and container-only execution rule.

Phase 1 ETL work can now start. Use `/sprint-plan` to decompose the ETL deliverable into tickets,
then `/tdd-feature` per ticket.

## What changed most recently

- DT-001 (harness bootstrap) closed: `packages/wayfinding/` skeleton created,
  `infra/docker-compose.yml` test service added, `Makefile` with `test`/`lint`/`type` gates
  implemented (all green, verified via Docker). ADR-0002 written. Coverage floor (85% line) set in
  `docs/DOD.md`. The gate is now real — all future work must pass `make test lint type` before
  merge.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps

1. `/sprint-plan` Phase 1 ETL deliverable (GeoPackage + contracted graph + build report) into
   tickets.
2. `/tdd-feature` per ticket thereafter — all tests and implementation now run via the Docker-based
   gate established in DT-001.
