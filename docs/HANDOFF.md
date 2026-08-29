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

**Nothing under `packages/` or `infra/` exists yet.** Phase 1 (ETL) is the next deliverable — start
it with `/sprint-plan` to decompose the phase, then `/tdd-feature` per ticket.

## What changed most recently

- Harness scaffolding added: subagent roles mirroring the reference implementations
  (`.claude/` in `C:\repos\sfudt\claude\dtwin-harness`, `humanaxiom/jd-assistant`), adapted to
  GitHub Copilot's `.agent.md` / `.prompt.md` / `.instructions.md` primitives. See
  [docs/03-harness-design.md](03-harness-design.md) for the full mapping and rationale.

## Open questions blocking Phase 1

See [docs/02-system-design.md §12](02-system-design.md#12-open-questions-for-stakeholders) —
closures feed, accessibility survey feasibility, elevator-outage notifications, future building
extracts, room-alias source, elevator-wait/walking-speed constants. None of these block *starting*
Phase 1 ETL, but the accessibility-survey question should be raised with stakeholders before the
accessible-routing UI copy is finalized.

## Next steps

1. `/sprint-plan` Phase 1 (ETL → GeoPackage + contracted graph + build report).
2. First ADR once `packages/` is introduced: package layout, coverage floors, container/test
   execution model (mirrors `dtwin-harness` ADR-0003, adapted to this repo's tooling).
3. `/tdd-feature` per ticket thereafter.
