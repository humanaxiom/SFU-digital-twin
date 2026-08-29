---
description: "Run the full TDD pipeline for a ticket: plan → (ADR if needed) → red → green → judge → docs → commit"
argument-hint: "<ticket-id and short description>"
agent: agent
---
Execute the standard feature workflow from
[.github/copilot-instructions.md](../copilot-instructions.md) for: ${input:ticket:Ticket id and short description}

1. Invoke `planner` for the implementation plan; save it under `docs/plans/<ticket-id>.md`.
2. If the plan touches schema, API surface, or component boundaries, invoke `architect` for an ADR
   before proceeding.
3. Invoke `test-writer` to write the failing tests from the plan's test list.
4. Invoke `test-runner` for a RED check. If any test fails for the wrong reason, return to
   `test-writer`.
5. Invoke `implementer` to reach GREEN with minimal code.
6. Invoke `test-runner` for the full gate (test, lint, type, data-QA — see
   [docs/DOD.md](../../docs/DOD.md)).
7. Invoke `judge`. On `REVISE`, route findings to `implementer` (or `test-writer` if the tests are
   the problem) and repeat steps 5–7.
8. On `APPROVE`, invoke `doc-writer`, then create a Conventional Commit on a
   `feat/<ticket-id>` branch. Do not push without explicit confirmation.

Report a compact summary at each stage transition; keep full subagent output out of the main
thread unless something needs a decision.
