---
description: "Append a retro note after a ticket or delivery phase closes — what worked, what didn't, what to change in the harness or design"
argument-hint: "<ticket-id or phase that just closed>"
agent: agent
---
Write a retro for: ${input:scope:Ticket id or phase that just closed}

1. Read the relevant `docs/plans/<ticket-id>.md`, the `judge` verdict history, and
   `docs/HANDOFF.md`.
2. Write `docs/retros/<date>-<slug>.md` covering: what shipped vs. planned, any deviation and why,
   gate/process friction (e.g. a subagent looping, a gate that was too strict/loose), and one or two
   concrete changes to propose — to the plan template, the gate contract in `docs/DOD.md`, or an
   agent's instructions.
3. If a proposed change affects `.github/agents/`, `.github/prompts/`, or `docs/DOD.md`, say so
   explicitly rather than silently editing them from this command — those are harness changes and
   should go through their own small plan.
